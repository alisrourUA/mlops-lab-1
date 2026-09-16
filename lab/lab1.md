# Lab 1 - Answers

## Question 1
`uv init` created:
- `.python-version` - pins the Python version used by uv for this project.
- `pyproject.toml` - project metadata and dependency config (PEP 621 standard).
- `README.md` - empty placeholder readme.
- `src/` - source layout folder where our package code (food11/data.py) will live.

## Question 2
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

## Question 7

## Question 8

## Notes / Adopted solutions