# Lab 2 - Model training and experiment tracking with MLflow

## Question 1: Look at pyproject.toml and uv.lock. What changed?

**pyproject.toml** (a few lines, human-readable, what *we* asked for):
- The four new libraries were added to `dependencies` with minimum versions
  (`>=`) equal to what was installed: `mlflow>=3.16.1`, `scikit-learn>=1.9.1`,
  `torch>=2.11.0`, `torchvision>=0.26.0`. `pillow` from Lab 1 is unchanged.
- A `[[tool.uv.index]]` and a `[tool.uv.sources]` section were added so that
  `torch` and `torchvision` are downloaded from PyTorch's CUDA 12.8 index
  (`cu128`) instead of PyPI. On Windows the default PyPI torch is CPU-only, so
  this is needed to use the NVIDIA GPU (RTX 4050). `explicit = true` means only
  these two packages use that index; everything else still comes from PyPI.
- `[tool.uv.build-backend] module-name = "food11"` was added, and the old
  `[project.scripts]` entry was removed, because the package lives in
  `src/food11/` rather than `src/mlops_lab_1/`.

**uv.lock** (2,690 lines added, 6 removed, machine-generated):
- It records the *entire* resolved dependency tree, not just the 4 packages we
  requested: 97 packages were installed, because mlflow, torch etc. pull in
  many transitive dependencies (numpy, pandas, sqlalchemy, flask, ...).
- Every package is pinned to an exact version (e.g. `torch==2.11.0+cu128`),
  with its download URL/index and file hashes for each platform.

**Difference:** `pyproject.toml` declares the *constraints* we want (minimum
versions), while `uv.lock` records the *exact* environment that satisfies
them. Committing both means anyone running `uv sync` gets the identical set of
packages, which makes the environment reproducible.


### Question 2: What is `--backend-store-uri` used for? What is `--default-artifact-root` used for? What is the difference between the metadata mlflow stores and the artifacts it stores?

- `--backend-store-uri sqlite:///mlflow.db` tells the server where to store
  **run metadata**: experiments, runs, parameters, metrics (with their steps
  and timestamps), tags, and run status/start/end times. Here it is a local
  SQLite database file, `mlflow.db`, created on first start ("Creating initial
  MLflow database tables"). Since no registry URI was given, the model registry
  uses the same database.
- `--default-artifact-root ./mlruns` tells the server where to store
  **artifacts**, the files produced by runs (trained models, plots, any other
  output files). Here it is the local `./mlruns` folder; in production this is
  often object storage such as S3.
- **Difference:** metadata is small, structured data (key-value pairs and
  numbers) that the UI needs to search, sort, filter and compare runs, so it
  goes in a database. Artifacts are arbitrary files that can be large (a
  ResNet-18 model is ~45 MB), so they go in file/object storage; the database
  only keeps a reference (URI) to where each run's artifacts are stored.


  ### Question 3: Why shouldn't `mlflow.db` and `mlruns/` be tracked by git, and why shouldn't they be tracked by dvc either?

**Not git:**
- They are generated run outputs (local state of the tracking server), not
  source code. Git is for human-written text files that change deliberately.
- `mlflow.db` is a binary SQLite file that changes on every run: git can't
  show meaningful diffs or merge it, and two people committing it would
  always conflict.
- `mlruns/` contains artifacts such as trained models (~45 MB each for
  ResNet-18); every run adds more, and once committed they stay in the git
  history forever, bloating the repo.

**Not dvc either:**
- dvc versions data and models as *inputs/outputs of a reproducible pipeline*
  (like the Food-11 datasets from Lab 1). `mlflow.db` and `mlruns/` are a
  live log that MLflow itself manages: MLflow *is* already the system that
  records the history of runs, so versioning snapshots of it is redundant.
- They change on every single run, so each snapshot would be outdated
  immediately, and the db and the artifact folder reference each other, so
  restoring them separately could leave them inconsistent.
- To share runs with a team, the right approach is a shared/remote MLflow
  tracking server (with remote artifact storage), not copying its files
  through git or dvc.


  ### Question 4: What happens the first time you call `set_experiment` with a name that doesn't exist yet? Check the mlflow UI.

MLflow does not raise an error: since no experiment named `food11` exists,
it **creates it automatically** on the tracking server and makes it the
active experiment, so all following runs are logged into it. In the UI,
the Experiments page now shows `food11` next to `Default`, with its
creation time. The new experiment gets the next ID (Default is 0, so
food11 is 1) and its own artifact location under `./mlruns`.

Calling `set_experiment("food11")` again later does not create a duplicate:
it just finds the existing experiment by name and sets it as active. This
makes it safe to put the call at the top of the training script.


### Question 5: What is the difference between `mlflow.log_param` and `mlflow.log_metric`? Why does `log_metric` take a `step` argument and `log_param` doesn't?

- `log_param` records a **configuration value** chosen before training and
  fixed for the whole run: `lr`, `batch_size`, `epochs`, `dataset`, model
  architecture, optimizer... It is logged once, and a param cannot be changed
  afterwards in the same run (logging the same key with a different value
  raises an error).
- `log_metric` records a **numeric result** produced by training, which can
  be logged many times and evolve: `train_loss`, `val_loss`, `val_accuracy`,
  `test_accuracy`.
- `log_metric` takes a `step` because a metric is a **time series**: each
  value is stored with its step (here the epoch number) and a timestamp, so
  MLflow keeps the whole history and can plot curves (e.g. `val_loss` per
  epoch, which shows overfitting when it rises while `train_loss` keeps
  decreasing). A param has a single value per run, so it has no history and
  no step.

  ### Question 6: Open the run in the mlflow UI. Find the params, the metric charts, and the logged model artifact. Where does the model artifact actually live on disk?

In the run page (`inquisitive-goat-141`):
- **Overview** tab: the 8 parameters (dataset, epochs, lr, batch_size, seed,
  model, optimizer, device) and the final value of the 4 metrics.
- **Model metrics** tab: `train_loss`, `val_loss` and `val_accuracy` are
  plotted as curves over steps 1-5 (one point per epoch), while
  `test_accuracy` is a single bar since it was logged once.
- **Artifacts** tab: the logged model, containing `MLmodel` (metadata:
  flavor, serialization format `pt2`, input/output signature), `data/` (the
  serialized weights), `conda.yaml`, `python_env.yaml` and `requirements.txt`
  (the environment needed to reload it), and `input_example.json` /
  `serving_input_example.json`.

On disk, the model lives in the artifact root given to the server
(`--default-artifact-root ./mlruns`), under the experiment ID (1 = food11):

    C:\Users\ali\mlops-lab-1\mlruns\1\models\m-f98adb7eca3449e19706666240decb2e\artifacts\

In MLflow 3, a model is a separate "logged model" entity with its own ID
(`m-...`), linked to the run, so it is stored under `models/<model_id>/`
rather than inside the run's folder. The database (`mlflow.db`) only stores
the metadata and the URI pointing to this folder, which confirms the
metadata/artifact split from Question 2.


### Question 7: In the mlflow UI, open the `food11` experiment. Select these runs and click "Compare". Which learning rate gave the best `val_accuracy`? Is higher always better?

Compared runs (mini dataset, 5 epochs, final values):

| lr     | batch | val_accuracy | test_accuracy |
|--------|-------|--------------|---------------|
| 0.01   | 32    | 0.155        | 0.145         |
| 0.001  | 32    | 0.601        | 0.630         |
| 0.0001 | 32    | 0.750        | 0.775         |
| 0.001  | 64    | 0.571        | 0.596         |

The best `val_accuracy` came from the **smallest learning rate, 0.0001**
(0.750). Higher is **not** better here, the opposite happened:

- **lr = 0.01** was too high: the training failed. Its `train_loss` stayed
  around 2.37, about ln(11) ≈ 2.40, which is the loss of a model predicting
  all 11 classes with equal probability, and its accuracy (~15%) is close
  to random guessing (1/11 ≈ 9%). The large updates destroyed the useful
  pretrained ImageNet features instead of adapting them.
- **lr = 0.001** learned, but unstably: `val_loss` jumped up and down
  between epochs, and it rose while `train_loss` kept falling (overfitting).
- **lr = 0.0001** improved smoothly: `val_loss` decreased steadily
  (1.16 → 0.81) and accuracy rose every epoch. In the `val_accuracy`
  metric chart, this run is above all the others from the very first epoch.

This is expected when **fine-tuning a pretrained model**: the weights are
already good, so small updates work best. A learning rate that is too low
can also be a problem (very slow training), so the best value is a
trade-off that must be found experimentally, which is exactly what
tracking and comparing runs in MLflow makes easy.


### Question 8: Use the parallel coordinates plot on the compare page to look at `lr`, `batch_size` and `val_accuracy` together. What pattern do you see?

Each line is one run, passing through its `batch_size`, `lr` and final
`val_accuracy` (colour = val_accuracy, red = high, blue = low).

- **`lr` is the parameter that matters most, with an inverse relationship:**
  the lines cross between the `lr` axis and the `val_accuracy` axis. The
  highest lr (0.01) goes to the lowest accuracy (0.155, dark blue line), the
  lowest lr (0.0001) goes to the highest accuracy (0.75, red line), and the
  two lr = 0.001 runs land in the middle (~0.57-0.60).
- **`batch_size` has a much smaller effect:** the only pair that differs by
  batch size (32 vs 64, both at lr = 0.001) ends almost at the same point
  (0.601 vs 0.571). Batch 64 is slightly lower, which is plausible since it
  makes half as many weight updates per epoch, but the difference is too
  small to conclude anything from a single run each: while debugging the
  script, three runs with the exact same settings (lr = 0.001, batch 32)
  gave final val_accuracy of 0.487, 0.563 and 0.601, so run-to-run noise
  is about as large as this difference.

Conclusion: in this setup the learning rate dominates; to properly judge
batch size we would need several runs per configuration (or more epochs /
the full dataset).


### Question 9: Sort the runs table by `val_accuracy` descending. Which run is the best one? Note its run ID, you'll need it in the next lab.

Best run: **adorable-stoat-293**
- Run ID: `9a01d131e7fe44978c344663cdc96d20`
- Params: dataset = mini, epochs = 5, **lr = 0.0001**, batch_size = 32
- Metrics: **val_accuracy = 0.750**, val_loss = 0.815,
  test_accuracy = 0.775, train_loss = 0.094

It is first when sorting by `val_accuracy` descending, ahead of
inquisitive-goat-141 (lr 0.001, batch 32, 0.601) and bustling-skunk-5
(lr 0.001, batch 64, 0.571). Its logged model artifact is the one to use in
the next lab.