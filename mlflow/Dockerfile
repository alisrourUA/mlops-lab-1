   FROM python:3.11-slim

   # Same MLflow version as the client in the project (uv.lock), so client and server match.
   RUN pip install --no-cache-dir mlflow==3.16.1

   # Create the data folder, so the image also runs without a mounted volume.
   RUN mkdir -p /mlflow-data

   EXPOSE 5000

   # --serve-artifacts + --artifacts-destination: artifacts are stored under /mlflow-data
   # but uploaded/downloaded THROUGH this server over HTTP (mlflow-artifacts:/ URIs),
   # so other containers and the host never need access to this container's filesystem.
   # --allowed-hosts: accept requests addressed to the Compose service name "mlflow".
   CMD ["mlflow", "server", \
        "--host", "0.0.0.0", "--port", "5000", \
        "--backend-store-uri", "sqlite:////mlflow-data/mlflow.db", \
        "--serve-artifacts", \
        "--artifacts-destination", "/mlflow-data/mlruns", \
        "--allowed-hosts", "mlflow:*,localhost:*,127.0.0.1:*"]