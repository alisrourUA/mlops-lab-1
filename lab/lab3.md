# Lab 3 - Containerizing the model with Docker

## Register your best model

### Question 1: Open the "Models" tab in the mlflow UI. What version number was your model given? What's the difference between a run's logged model artifact and a registered model?

The model from the best Lab 2 run (`adorable-stoat-293`, run ID
`9a01d131e7fe44978c344663cdc96d20`, val_accuracy 0.75) was registered
under the name `food11` and was given **version 1**, since it is the first
version of that registered model.

- A **logged model** is the output of one training run: the files saved by
  `mlflow.pytorch.log_model` (weights, `MLmodel`, environment files), with
  its own ID (`m-c529e2302cd548a68b2f0fad2712acd7`), linked to the run that
  produced it, together with its params, metrics and even the git commit.
  Every run creates one, whether the model is good or not.
- A **registered model** is a named entry in the **Model Registry**
  (`food11`) that groups selected logged models as numbered **versions**
  (v1, v2, ...). Registering is a deliberate decision ("this one is worth
  using"); the registry adds a stable name, version numbers, aliases,
  tags and descriptions on top, without copying or changing the run.

In short: a logged model answers *"what did this run produce?"*, while a
registered model answers *"which model is `food11`, and what are its
versions?"*.

### Question 2: What aliases replaced the old built-in stages in mlflow? Why version a model separately from the run that produced it, and why is an alias more flexible than a fixed stage name?

**What replaced stages:** the fixed stages (`None`, `Staging`, `Production`,
`Archived`) were replaced by **aliases**: named, mutable pointers to one
specific model version, whose names you choose yourself (the common
convention is `champion` for the model currently served and `challenger`
for a candidate being evaluated), plus free-form **tags** (key-value
labels such as `validation_status=approved`) for any other metadata.
Here, `food11` version 1 got the alias `champion`.

**Why version separately from the run:**
- Runs are experiments: most of them are never used (in Lab 2, 4 of 6 runs
  were worse or failed). The registry keeps only the models chosen for
  use, under a stable name (`food11`) that consumers can rely on, while
  the version still links back to its run for traceability (params,
  metrics, code commit).
- A model's lifecycle (deployment, rollback, retirement) continues long
  after its training run ends. Versions give it a clear history
  (v1, v2, v3...) independent of run IDs, which are random and meaningless
  to the people deploying it.

**Why aliases are more flexible than stages:**
- You can create **any names you need** (`champion`, `challenger`,
  `shadow`, `eu-region`...) instead of being limited to a fixed set of
  stages.
- An alias is just a pointer: **moving it to another version** is a single
  update, and code that loads `models:/food11@champion` automatically gets
  the new version without changing anything. **Rollback** is equally
  simple: point the alias back to the previous version.
- Each alias points to exactly one version at a time, so there is no
  ambiguity, whereas with stages several versions could be in
  `Production` at once.


  ## Write a serving script

### Question 3: Why load the model through an mlflow model URI (`models:/food11@champion`) instead of pointing directly at the `.pth` file on disk? What would you have to change to serve a newer model version?

**Why a model URI:**
- **Decoupling:** the serving code does not need to know where the files
  are, which run produced them, or their file format. It asks the
  registry for "the model called `food11` that currently has the
  `champion` alias", and MLflow resolves that to a version (here v1),
  then to the logged model's artifacts, and downloads them.
- **Portability:** a hard-coded path like
  `mlruns/1/models/m-.../artifacts/...` only exists on my laptop. A
  container, another server or a teammate cannot use it, but they can all
  reach the tracking server and resolve the same URI.
- **Everything needed comes with it:** `mlflow.pyfunc.load_model` loads
  the model together with its `MLmodel` metadata (flavor, `pt2` format,
  input signature) and environment information, and gives a standard
  `predict()` interface. A raw weights file would also require the code
  that rebuilds the ResNet-18 architecture with 11 outputs.
- **Traceability:** the served model is always a registered version,
  linked back to its run, params, metrics and git commit.

**Serving a newer version:** no code change and no rebuild. Train and
register the new model (it becomes `food11` version 2), then **move the
`champion` alias** from v1 to v2 in the UI or with
`client.set_registered_model_alias("food11", "champion", 2)`. Since the
API loads the model once at startup, the only thing left is to
**restart the service**. Rolling back is the same operation in reverse:
point `champion` back to v1 and restart.

Tested locally: `GET /health` returned `{"status":"ok"}`, and
`POST /predict` returned `Soup` (confidence 0.9998) for a Soup image, and
`Fried food` (0.8635) for a Bread image, a wrong but plausible prediction
for a model with ~75% accuracy.


## Write the Dockerfile

### Question 4: Why copy `pyproject.toml`/`uv.lock` and run `uv sync` *before* copying the rest of the source code, instead of copying everything at once? What happens to the build cache when you only change a line in `serve.py`?

Docker builds an image layer by layer and caches each layer. A layer is
reused only if its instruction **and everything before it** are
unchanged (for a `COPY`, Docker compares the checksums of the copied
files). As soon as one layer changes, it and **every layer after it**
are rebuilt.

Installing the dependencies is by far the slowest step (`uv sync` took
910 s, about 15 minutes, in the first build), while the source code is
what changes most often. So the Dockerfile is ordered from
least-to-most-frequently changed:

1. `COPY pyproject.toml uv.lock ./` - changes only when dependencies change
2. `RUN uv sync --frozen --no-dev --no-install-project` - depends only on those two files
3. `COPY src/ ./src/` (in the runtime stage) - changes on every code edit

**When I only change a line in `serve.py`:** `pyproject.toml` and
`uv.lock` are unchanged, so the `COPY` of those files and the `uv sync`
layer are taken **from the cache** (shown as `CACHED` in the build
output), as is the copy of the venv into the runtime stage. Only the
`COPY src/` layer is rebuilt, so the rebuild takes seconds instead of
15 minutes.

If everything were copied at once (`COPY . .` before `uv sync`), any
change to any file, even a comment in `serve.py`, would change that
`COPY` layer and invalidate the cache for `uv sync`, forcing a full
reinstall of every dependency on every build.


## Build and run the image

### Question 7: Why can't the container simply use `127.0.0.1:5000` to reach the mlflow server on your host? What does `host.docker.internal` resolve to?

A container has its **own network namespace**: its own network
interfaces, IP address and loopback interface. Inside the container,
`127.0.0.1` / `localhost` means **the container itself**, not my laptop
(`docker exec food11-api getent hosts localhost` returns `::1`, the
container's own loopback). Nothing listens on port 5000 inside the
container, so `127.0.0.1:5000` would just get "connection refused".
On Windows and Mac this is even more true: Docker Desktop runs
containers inside a Linux VM (WSL2 here), so they don't even share the
host's network stack. (On Linux, `--network host` removes this
isolation, which is why the Linux command in the lab can use
`127.0.0.1`.)

`host.docker.internal` is a special DNS name that Docker Desktop
provides inside containers. It **resolves to an IP address that
routes back to the host machine**: here
`docker exec food11-api getent hosts host.docker.internal` returned
**`192.168.65.254`**, an address on Docker Desktop's internal network
that forwards traffic to the Windows host.

Two extra changes were needed on the host for this to work:
- The MLflow server had to listen on all interfaces
  (`--host 0.0.0.0` instead of `127.0.0.1`), since the connection now
  arrives from Docker's network rather than from the loopback.
- MLflow 3's security middleware only accepts requests whose `Host`
  header is localhost or a private IP, so `host.docker.internal` had to
  be allowed explicitly with
  `--allowed-hosts "localhost:*,127.0.0.1:*,host.docker.internal:*"`.

Reaching the server is not enough to get the model, though: the
registry only returns the model's **location**, and here that location
is a local Windows folder
(`file:C:/Users/ali/mlops-lab-1/mlruns/1/models/m-c529.../artifacts`).
The container could only read it because the host's `mlruns/` folder
was bind-mounted (read-only) at that path. In a real deployment,
artifacts are stored in shared storage reachable over the network
(S3, MinIO, or MLflow's `--serve-artifacts` proxy).

The containerized API returned the same results as the local run:
Soup 0.9998 for `Soup/9_0.jpg` and Fried food 0.8635 for
`Bread/0_0.jpg`.



### Question 8: Stop the container and start a new one from the same image. Does the model still load correctly without you rebuilding? What does that tell you about what's baked into the image versus fetched at runtime?

Yes. After stopping the container (started with `--rm`, so it was
deleted: `docker ps -a --filter name=food11-api` showed nothing), I
started a brand-new container from the same `food11-api:latest` image
without rebuilding. It logged
`Loaded model models:/food11@champion from http://host.docker.internal:5000`
again, and `/predict` returned the same result (Soup, 0.9998).

**Baked into the image (fixed at build time):** the base OS and Python
3.13, the virtual environment with all dependencies (CPU torch 2.11.0,
torchvision, MLflow, FastAPI...), and the serving code (`src/`). These
are identical in every container started from the image.

**Fetched at runtime (on every container start):** the **model
itself**. The image contains no weights at all; at startup `serve.py`
reads `MLFLOW_TRACKING_URI` from the environment, asks the registry
which version the `champion` alias points to, and copies that
version's files into the container's temporary folder. That copy is
thrown away when the container is removed, which is why the new
container downloaded it again.

Consequences:
- **Model and code are versioned and deployed independently.** To
  serve a new model, move the `champion` alias and restart the
  container: no rebuild, the same image serves any version.
- **The same image can be configured differently** per environment
  only through runtime settings (`-e MLFLOW_TRACKING_URI=...`).
- **But the container depends on external services at startup:** if
  the tracking server or the artifact storage (here the mounted
  `mlruns/` folder) is unreachable, the container cannot start
  serving. It also means two containers started at different times
  can serve different models if the alias moved in between.


  ## Commit your work

### Question 9: The Dockerfile and image are versioned differently — one lives in git, the other doesn't (yet). What's still missing before another machine (like a CI runner or a Kubernetes cluster) could reliably pull and run the exact image you just built?

The **recipe** (Dockerfile, `.dockerignore`, `pyproject.toml`,
`uv.lock`, `src/`) is versioned in git, but the **built image** only
exists in my local Docker Desktop. What's missing:

1. **A container registry.** The image must be pushed
   (`docker tag` + `docker push`) to a registry another machine can pull
   from: Docker Hub, GitHub Container Registry (ghcr.io), or a cloud
   registry (ECR, GCR, ACR). Today, `docker pull food11-api:latest`
   on any other machine would simply fail.
2. **Immutable, meaningful tags instead of `latest`.** `latest` is a
   moving label: it points to whatever was built last, so two machines
   pulling it at different times can get different images. The image
   should be tagged with something unique and traceable, typically the
   git commit SHA (e.g. `ghcr.io/<user>/food11-api:0c0dce0`) and/or a
   version number, and deployments should reference that tag, or even
   better the image **digest** (`@sha256:...`), which identifies the
   exact content and can never change.
3. **An automated build (CI).** The image was built by hand on my
   laptop. A CI pipeline (e.g. GitHub Actions) should build it from a
   specific git commit, run tests, and push it to the registry, so every
   image is reproducibly linked to the code that produced it, and it is
   built for the target platform (`linux/amd64` here).
4. **Runtime dependencies that exist outside my laptop.** The image
   does not contain the model; at startup it needs a reachable MLflow
   tracking server and model storage. Today these are my laptop's
   server (`host.docker.internal:5000`) and a bind-mounted local
   `mlruns/` folder, which a CI runner or Kubernetes cluster cannot
   access. They need a shared tracking server and artifacts in shared
   storage (S3, MinIO, `--serve-artifacts`), with the URL passed through
   configuration (environment variables, Kubernetes ConfigMaps/Secrets,
   registry credentials).

In short: git versions *how* to build the image; a registry with
immutable tags, built by CI, versions *the image itself*, and shared
infrastructure makes it runnable anywhere.