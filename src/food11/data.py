"""
Food-11 data preparation script.

Reads the raw Food-11 dataset (flat files, category encoded in filename
prefix as "<category_index>_<...>.jpg") from:
    ./data/food11_raw/{training,evaluation,validation}

and produces two processed versions, with images resized to 128x128 and
organized into per-category subfolders:
    ./data/food11_processed/{training,evaluation,validation}/<category_name>/*
    ./data/food11_processed_mini/{training,evaluation,validation}/<category_name>/*

The "mini" version caps each category to at most MINI_LIMIT images per
split, for fast local development/testing.
"""

from pathlib import Path

from PIL import Image

# Category index -> name, per the lab spec (index is the filename prefix).
CATEGORIES = {
    0: "Bread",
    1: "Dairy product",
    2: "Dessert",
    3: "Egg",
    4: "Fried food",
    5: "Meat",
    6: "Noodles-Pasta",
    7: "Rice",
    8: "Seafood",
    9: "Soup",
    10: "Vegetable-Fruit",
}

SPLITS = ["training", "evaluation", "validation"]

TARGET_SIZE = (128, 128)
MINI_LIMIT = 100

RAW_ROOT = Path("data/food11_raw")
PROCESSED_ROOT = Path("data/food11_processed")
PROCESSED_MINI_ROOT = Path("data/food11_processed_mini")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def category_index_from_filename(filename: str) -> int:
    """Extract the leading category index from a filename like '3_45.jpg'."""
    prefix = filename.split("_", 1)[0]
    return int(prefix)


def process_split(split: str) -> None:
    """Process one split (training/evaluation/validation)."""
    raw_split_dir = RAW_ROOT / split
    if not raw_split_dir.is_dir():
        print(f"  [skip] {raw_split_dir} does not exist")
        return

    # Track how many images have been written to the mini set per category.
    mini_counts = {index: 0 for index in CATEGORIES}

    image_paths = sorted(
        p for p in raw_split_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    print(f"  {split}: {len(image_paths)} images found")

    for image_path in image_paths:
        try:
            category_index = category_index_from_filename(image_path.name)
            category_name = CATEGORIES[category_index]
        except (ValueError, KeyError):
            print(f"    [warn] could not determine category for {image_path.name}, skipping")
            continue

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            resized = img.resize(TARGET_SIZE)

            # Full processed dataset.
            out_dir = PROCESSED_ROOT / split / category_name
            out_dir.mkdir(parents=True, exist_ok=True)
            resized.save(out_dir / image_path.name)

            # Mini processed dataset (capped per category).
            if mini_counts[category_index] < MINI_LIMIT:
                mini_out_dir = PROCESSED_MINI_ROOT / split / category_name
                mini_out_dir.mkdir(parents=True, exist_ok=True)
                resized.save(mini_out_dir / image_path.name)
                mini_counts[category_index] += 1


def main() -> None:
    print("Preparing Food-11 processed datasets...")
    for split in SPLITS:
        process_split(split)
    print("Done.")
    print(f"  Full processed dataset:  {PROCESSED_ROOT}")
    print(f"  Mini processed dataset:  {PROCESSED_MINI_ROOT}")


if __name__ == "__main__":
    main()