"""
Food-11 training script with MLflow experiment tracking.

Fine-tunes a pretrained ResNet-18 on the processed Food-11 dataset
(images already resized to 128x128, one subfolder per class) and logs
params, per-epoch metrics, the final test accuracy and the trained model
to an MLflow tracking server.

Usage (from the repo root, with the mlflow server running):
    uv run python ./src/food11/train.py --dataset mini --epochs 5 --lr 0.001 --batch-size 32
"""

import argparse
from pathlib import Path

import mlflow
import mlflow.pytorch
import torch
from torch import nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

TRACKING_URI = "http://127.0.0.1:5000"
EXPERIMENT_NAME = "food11"

DATASETS = {
    "processed": Path("data/food11_processed"),
    "mini": Path("data/food11_processed_mini"),
}

NUM_CLASSES = 11

# ImageNet statistics, since the ResNet-18 weights were pretrained on ImageNet.
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ResNet-18 on Food-11")
    parser.add_argument("--dataset", choices=DATASETS.keys(), default="mini")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-workers", type=int, default=0)
    return parser.parse_args()


def build_dataloaders(root: Path, batch_size: int, num_workers: int):
    train_tf = transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    eval_tf = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])

    train_ds = datasets.ImageFolder(root / "training", transform=train_tf)
    val_ds = datasets.ImageFolder(root / "validation", transform=eval_tf)
    test_ds = datasets.ImageFolder(root / "evaluation", transform=eval_tf)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    return train_loader, val_loader, test_loader


def build_model() -> nn.Module:
    # Pretrained ResNet-18, final layer replaced: 1000 ImageNet classes -> 11 Food-11 classes.
    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, NUM_CLASSES)
    return model


def train_one_epoch(model, loader, criterion, optimizer, device) -> float:
    model.train()
    total_loss, total_samples = 0.0, 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * images.size(0)
        total_samples += images.size(0)
    return total_loss / total_samples


@torch.no_grad()
def evaluate(model, loader, criterion, device) -> tuple[float, float]:
    model.eval()
    total_loss, correct, total_samples = 0.0, 0, 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        outputs = model(images)
        total_loss += criterion(outputs, labels).item() * images.size(0)
        correct += (outputs.argmax(dim=1) == labels).sum().item()
        total_samples += images.size(0)
    return total_loss / total_samples, correct / total_samples


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_loader, val_loader, test_loader = build_dataloaders(
        DATASETS[args.dataset], args.batch_size, args.num_workers
    )
    model = build_model().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run():
        # Params: fixed before training, logged once.
        mlflow.log_params({
            "dataset": args.dataset,
            "epochs": args.epochs,
            "lr": args.lr,
            "batch_size": args.batch_size,
            "seed": args.seed,
            "model": "resnet18",
            "optimizer": "Adam",
            "device": device.type,
        })

        # Metrics: logged at the end of every epoch, with step=epoch.
        for epoch in range(1, args.epochs + 1):
            train_loss = train_one_epoch(model, train_loader, criterion, optimizer, device)
            val_loss, val_accuracy = evaluate(model, val_loader, criterion, device)

            mlflow.log_metric("train_loss", train_loss, step=epoch)
            mlflow.log_metric("val_loss", val_loss, step=epoch)
            mlflow.log_metric("val_accuracy", val_accuracy, step=epoch)

            print(f"Epoch {epoch}/{args.epochs} | train_loss={train_loss:.4f} "
                  f"| val_loss={val_loss:.4f} | val_accuracy={val_accuracy:.4f}")

        # Final test accuracy on the held-out evaluation split.
        _, test_accuracy = evaluate(model, test_loader, criterion, device)
        mlflow.log_metric("test_accuracy", test_accuracy)
        print(f"Test accuracy: {test_accuracy:.4f}")

        # Move to CPU before saving so the logged model can be loaded on machines without a GPU.
        model.to("cpu")
        model.eval()
        # MLflow 3.x saves PyTorch models in "pt2" format by default, which traces
        # the model on an example input. A batch of 2 keeps the batch size dynamic.
        input_example = next(iter(test_loader))[0][:2].numpy()
        mlflow.pytorch.log_model(model, name="model", input_example=input_example)


if __name__ == "__main__":
    main()