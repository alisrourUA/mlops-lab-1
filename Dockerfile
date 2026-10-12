# ---------- Stage 1: builder ----------
# Builds the virtual environment with all dependencies.
FROM python:3.13-slim AS builder

# Install uv by copying its single static binary from the official uv image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Compile .pyc files at build time (faster startup), copy files instead of
# hard-linking them from the uv cache, and use the image's own Python.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Copy ONLY the dependency definitions first: this layer (and the slow
# `uv sync` below) is reused from cache as long as these two files don't change.
COPY pyproject.toml uv.lock ./

# --frozen: install exactly what uv.lock says, never re-resolve.
# --no-dev: skip development dependencies.
# --no-install-project: install only the dependencies, not our own package
#   (its source isn't copied yet; the runtime stage runs it from src/).
RUN uv sync --frozen --no-dev --no-install-project


# ---------- Stage 2: runtime ----------
# Same Python version and path as the builder, so the copied venv works as-is.
FROM python:3.13-slim AS runtime

WORKDIR /app

# Only the finished virtual environment comes over; uv and its cache stay behind.
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Source code last: it changes most often, so only this layer is rebuilt
# when serve.py is edited.
COPY src/ ./src/

EXPOSE 8000

ENTRYPOINT ["uvicorn", "src.food11.serve:app", "--host", "0.0.0.0", "--port", "8000"]