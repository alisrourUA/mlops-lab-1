# Lab 1 - Answers

## Question 1
`uv init` created:
- `.python-version` - pins the Python version used by uv for this project.
- `pyproject.toml` - project metadata and dependency config (PEP 621 standard).
- `README.md` - empty placeholder readme.
- `src/` - source layout folder where our package code (food11/data.py) will live.


## Question 2
`dvc init` created the `.dvc/` folder containing:
- `.dvc/.gitignore` - auto-generated, tells git to ignore dvc's internal tmp/cache paths - pushed to git
- `.dvc/config` - dvc configuration (remotes, settings) - pushed to git
- `.dvc/tmp/` - dvc's internal temp/working files (locks, state) - NOT pushed to git
(`.dvc/cache/` will appear later once we actually track data with `dvc add`, and is also NOT pushed to git - it holds the actual data content locally)
- `.dvcignore` (project root) - like .gitignore but for dvc, to exclude paths from being tracked - pushed to git

Per the lab instructions we push `.dvc` and `.dvcignore` to git.

## Question 3
Initially we set up DagsHub as the dvc remote following the lab steps (`origin`), with credentials stored globally (not pushed to git). However, due to slow internet, we switched to a **local dvc remote** as recommended by the instructor:

dvc remote add --global local_storage C:\Users\ali\dvc-storage
dvc remote default local_storage   (set at project level, overriding the global default)

This remote requires no credentials since it's just a local folder DVC reads/writes directly — no `auth`/`user`/`password` config needed. The DagsHub `origin` remote is still configured but no longer used as default.

## Notes / Adopted solutions
Per the lab's suggested workaround #1 ("Use a local remote instead of dagshub"), we set up a local dvc remote at `C:\Users\ali\dvc-storage` (outside the git repo) due to slow internet making the full DagsHub push (~1.1 GB, 16,643 files) impractical.
## Question 4
Running `dvc add data` automatically added a line to `.gitignore`:

/data

This tells git to completely ignore the `data/` folder — git will never track or commit the actual data files inside it. This makes sense because the data is now managed by dvc instead; git only needs to track the small `data.dvc` pointer file, not the ~1.1 GB of raw content.

## Question 5
Yes, a `data.dvc` file was created. Its contents:

outs:
- md5: a3a457d03c51ff8b037a833440f6ad13.dir
  size: 1188442712
  nfiles: 16643
  hash: md5
  path: data

This is dvc's pointer/metadata file. It records:
- `md5`: a hash representing the entire `data` directory's content (a "directory hash" — computed from the hashes of all files inside it), used to detect if the data has changed and to locate the matching content in the dvc cache/remote
- `size`: total size in bytes (1,188,442,712 ≈ 1.1 GB)
- `nfiles`: total number of files tracked (16,643)
- `path`: the path this pointer corresponds to (`data`)

This is the file that gets committed to git — it's tiny (just text) but lets anyone with git + dvc + access to the remote reconstruct the full data folder via `dvc checkout` (or `dvc pull` if data isn't in cache yet). It's the bridge between git (versioning the pointer) and dvc (versioning the actual content).

## Question 6
Checking the GitHub web UI (main branch):
- **Code is there**: yes — src/mlops_lab_1/, pyproject.toml, uv.lock, .python-version, README.md, lab/
- **Data is there**: no — the actual data/food11_raw files are NOT on GitHub, since `data/` is listed in `.gitignore`
- **File pointing to data location**: yes — `data.dvc`, which contains the md5 hash, size, file count, and path of the tracked data directory

Checking DagsHub web UI:
- Since we switched to a **local dvc remote** (due to slow internet) instead of DagsHub, we never ran `dvc push` against DagsHub. DagsHub was never configured as our *git* remote either (only initially considered as the dvc data remote). So the DagsHub repo page shows no data and no meaningful commits from this project — it remains essentially as created, unused for this workflow.

## Question 7
In a completely new clone of the GitHub repo, the `data/` folder does NOT exist — only the small `data.dvc` pointer file (tracked by git) and code are present.

The command needed to restore it is:

dvc pull

This fetches the data from the configured remote (in our case, a local folder at C:\Users\ali\dvc-storage) into the local `.dvc/cache`, then checks it out into the `data/` workspace folder. After running it, all 16,643 files across food11_raw/training, evaluation, and validation are correctly restored, matching the original dataset exactly.

(Note: DVC's cache is content-addressable — files with identical content are stored once and referenced by multiple paths. Our local remote ended up holding 16,021 unique content blobs that expand back into the full 16,643 tracked file paths, which is why `dvc status -c` reported everything as "in sync" even though the raw file count differed. An initial `dvc pull` attempt failed likely due to a transient issue but succeeded on retry.)

## Question 8
After running:

git checkout b988f50   (the commit before food11_processed/food11_processed_mini were added)
dvc checkout

The `data/` folder now contains **only `food11_raw`** — the `food11_processed` and `food11_processed_mini` folders are gone entirely (confirmed via `dir data`).

This happens because `dvc checkout` reconstructs the workspace to exactly match what `data.dvc` records at the currently checked-out git commit. At `b988f50`, the tracked `data.dvc` hash only reflects the raw dataset — dvc doesn't know about the processed folders yet at that point in history, so it removes anything in `data/` that isn't part of the recorded snapshot. This demonstrates that git + dvc together give you full, synchronized versioning of both code and data: checking out an old commit rolls back the data to match, not just the code/pointer file.

## Notes / Adopted solutions
Due to slow internet, pushing the Food-11 dataset (~1.1 GB, 16,643 files) to DagsHub was impractical. Per the lab's suggested workaround #1, and per instructor guidance, we used a **local dvc remote** instead of DagsHub:

    dvc remote add --global local_storage C:\Users\ali\dvc-storage
    dvc remote default local_storage

This remote is a folder outside the git repository, on the same machine. All `dvc push`/`dvc pull`/`dvc checkout` operations in this lab used this local remote rather than DagsHub. DagsHub was still configured as an available remote (`origin`) but never used to store data.