"""
Food-11 model serving API.

Loads the registered model `food11@champion` from the MLflow Model Registry
once at startup and exposes:
    GET  /health   -> {"status": "ok"}
    POST /predict  -> predicted category + confidence for an uploaded image

Run locally (from the repo root, with the mlflow server running):
    uv run uvicorn src.food11.serve:app --host 0.0.0.0 --port 8000
"""

import io
import os
import tempfile
from contextlib import asynccontextmanager

import mlflow
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

# Overridable from the environment (e.g. inside a container).
TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
MODEL_URI = os.getenv("MODEL_URI", "models:/food11@champion")

# Must match the label order used in training: torchvision's ImageFolder
# assigns indices to the class folders in alphabetical order.
CLASS_NAMES = [
    "Bread",
    "Dairy product",
    "Dessert",
    "Egg",
    "Fried food",
    "Meat",
    "Noodles-Pasta",
    "Rice",
    "Seafood",
    "Soup",
    "Vegetable-Fruit",
]

# Same preprocessing as the evaluation transform in train.py.
IMAGE_SIZE = (128, 128)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the model once at startup, not on every request.
    global model
    mlflow.set_tracking_uri(TRACKING_URI)
    # The model was saved on CPU in "pt2" format, which must be loaded on the
    # same device type. Without this, MLflow picks CUDA when a GPU is present.
    # dst_path: always copy the model files into a fresh local directory. Without
    # it, a model stored in a local folder is used in place, and MLflow writes a
    # metadata file into that folder, which fails on a read-only mount.
    model = mlflow.pyfunc.load_model(
        MODEL_URI, dst_path=tempfile.mkdtemp(), model_config={"device": "cpu"}
    )
    print(f"Loaded model {MODEL_URI} from {TRACKING_URI}")
    yield


app = FastAPI(title="Food-11 classifier", lifespan=lifespan)


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Image bytes -> float32 array of shape (1, 3, 128, 128), normalized like in training."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize(IMAGE_SIZE)
    array = np.asarray(image, dtype=np.float32) / 255.0  # (H, W, C) in [0, 1]
    array = (array - IMAGENET_MEAN) / IMAGENET_STD
    array = array.transpose(2, 0, 1)  # (C, H, W), as expected by PyTorch
    return np.expand_dims(array, axis=0).astype(np.float32)  # add batch dimension


def softmax(logits: np.ndarray) -> np.ndarray:
    exp = np.exp(logits - logits.max())
    return exp / exp.sum()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    try:
        batch = preprocess(await file.read())
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid image.")

    logits = np.asarray(model.predict(batch))[0]  # the model outputs raw scores (logits)
    probabilities = softmax(logits)
    best = int(probabilities.argmax())

    return {
        "category": CLASS_NAMES[best],
        "confidence": round(float(probabilities[best]), 4),
        "model_uri": MODEL_URI,
    }