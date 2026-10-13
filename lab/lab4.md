# Lab 4 - Orchestrating the app with Docker Compose

## The mlflow service

I changed a few things in the mlflow Dockerfile compared to the one given in the lab:

- I pinned `mlflow==3.16.1` so the server is the same version as the client used in the project.
- I added `RUN mkdir -p /mlflow-data`, otherwise SQLite can't create the database when no volume is mounted.
- I used `--serve-artifacts --artifacts-destination /mlflow-data/mlruns` instead of `--default-artifact-root`. With a plain artifact root, the server gives clients a folder path that only exists inside the mlflow container, so neither the inference container nor the training script on my laptop could read or write the models (this is the same problem I had at the end of Lab 3). With the artifact proxy, the files are still stored on the volume, but they are uploaded and downloaded over HTTP through the server (`mlflow-artifacts:/` URIs).
- I added `--allowed-hosts "mlflow:*,localhost:*,127.0.0.1:*"`, because MLflow 3 has a security middleware that rejects requests sent to `mlflow:5000` by default.

### Question 1: What happens to everything written to `/mlflow-data` if you never mount a volume there and just `docker run` this image standalone? Try it: run the container, register nothing, stop it, remove it, start a new one from the same image — what do you see in the UI?

Without a volume, `/mlflow-data` is just a normal folder inside the container's writable layer. That layer belongs to the container only, so the database and the artifacts exist only as long as that container exists.

To test it, I ran the image with `docker run --rm -d --name mlflow-test -p 5000:5000 food11-mlflow:latest` and created an experiment called `q1-test` in the UI. At that point the list showed `q1-test` and `Default` (created at 11:12:27 PM). Then I stopped the container (with `--rm` it was also removed) and started a new one from the same image. After refreshing, only `Default` was left, and its creation time had changed to 11:14:55 PM. So it wasn't only `q1-test` that disappeared: the whole database had been created again from zero.

The reason is that a new container always starts from the image, and the image never contains what was written at runtime. Everything was in the writable layer of the old container, which was deleted with it. For a service that keeps state, like the tracking server and the registry, the data has to be stored outside the container, in a volume.

### Question 2: Why a named volume here instead of a bind mount to a folder in your repo (the way you might for local dev)? Would a bind mount work just as well?

A named volume is storage that Docker creates and manages itself. A bind mount links a specific folder from the host into the container.

I think the named volume is the better choice here for a few reasons:

- The compose file stays portable. A bind mount depends on a path on my machine (like `C:\Users\ali\...`) and on the host's OS and file permissions, which can cause problems when moving between Windows and Linux.
- The database and the models are outputs of the service, not code. If they were in a folder inside the repo, they could end up committed, deleted by a `git clean`, or sent in a Docker build context by mistake. This already happened with `mlflow.db` and `mlruns/` in Lab 2, which I had to add to `.gitignore`.
- On Docker Desktop, a named volume is stored inside Docker's Linux VM. A bind mount of a Windows folder goes through a file-sharing layer that is slower, and SQLite can have file locking problems with it.
- Docker manages its lifecycle: I can list or inspect it with `docker volume`, and it is only deleted when I explicitly ask for it (`docker compose down -v`).

A bind mount would still work: the data would also survive a `down`/`up`, and it's practical in development when you want to open the files directly from the host. But it is less portable and slower on Windows, and it mixes the service's data with the repository, so for persistent service data I would use a named volume.

## Update the inference service

### Question 3: In Lab 3 you had to use `host.docker.internal` or `--network host` to reach mlflow from inside the container. In this lab, `MLFLOW_TRACKING_URI` will simply be `http://mlflow:5000`. Why does that hostname resolve now when it didn't before?

In Lab 3, mlflow was running directly on Windows, outside Docker, and the inference container was alone on Docker's default network. The only way to reach the host from the container was the special name `host.docker.internal`, and a name like `mlflow` didn't exist anywhere.

Now mlflow is a container too, and Docker Compose creates a private network for the project (`mlops-lab-1_default`) and connects all the services to it. On this kind of network, Docker has an embedded DNS server that resolves each service name (`mlflow`, `inference`, `frontend`) to the IP address of that service's container. So from the inference container, `mlflow` resolves to the private IP of the mlflow container, and `http://mlflow:5000` reaches the server directly, without going through the host or a published port. It also keeps working if a container is recreated with a different IP, because the name stays the same.

I still needed one extra change for this to work: MLflow 3 only accepts requests addressed to localhost or a private IP by default, so I started the server with `--allowed-hosts "mlflow:*,..."` so it accepts requests sent to `mlflow:5000`.

## The frontend service

### Question 4: Why does the frontend read `INFERENCE_URL` from an environment variable instead of hardcoding `http://inference:8000`? Think about what happens if you ever `docker run` this frontend image on its own, outside Compose.

The name `inference` only exists inside the Compose network. If I ran the frontend image on its own with `docker run`, or ran the app directly on my laptop, there would be no service called `inference`, so a hardcoded `http://inference:8000` would fail on every request with a name resolution error. The only way to fix it would be to change the code and rebuild the image.

With an environment variable, the same image can be used anywhere and only the configuration changes when it is started:

- in Compose: `INFERENCE_URL=http://inference:8000`, set in the compose file;
- alone with `docker run`, with the API running on the host: `-e INFERENCE_URL=http://host.docker.internal:8000`;
- on my laptop for development: no variable, so it uses the default `http://127.0.0.1:8000`;
- in production: whatever address the inference service has there.

The idea is to build the image once and configure it when it runs, so the image doesn't need to know where it will be deployed. It's the same pattern as `MLFLOW_TRACKING_URI` in `serve.py`.

## Wire it together with Docker Compose

### Question 5: Only `mlflow` and `frontend` publish a port to the host. `inference` doesn't. Why not, and how does the frontend still reach it?

A port only needs to be published when something outside Docker has to reach it. Here that's the case for:

- `frontend` (8501), the web page that users open in their browser;
- `mlflow` (5000), for the UI and for the training script on my laptop, which logs runs and models to it.

Nobody outside Docker needs to call the inference API directly. Its only client is the frontend, which is on the same Compose network. Traffic between containers on that network goes straight from one container to the other, without going through the host. The frontend uses `INFERENCE_URL=http://inference:8000`: the Compose DNS resolves `inference` to the inference container's IP, and 8000 is the port uvicorn listens on inside the container.

Not publishing the port is also safer. The API isn't exposed on the host's network, users can only access it through the frontend, and it can't conflict with another program using port 8000 on the host. Only the entry points of the system need to be published.

### Question 6: `depends_on` here only waits for the mlflow *container process* to start, not for the tracking server inside it to be ready to accept connections. If your `serve.py` tries to load the Staging model at startup and mlflow isn't ready yet, what happens to the `inference` container? Look at `docker compose logs inference` if it fails.

I checked this on a cold start (`docker compose down` then `docker compose up`), using the timestamps from `docker compose logs -t`:

| Time (UTC) | What happened |
|---|---|
| 20:50:26.0 | inference starts and begins loading the model (`Waiting for application startup`) |
| 20:50:29.4 | mlflow only starts listening (`Uvicorn running on http://0.0.0.0:5000`) |
| 20:50:44.8 to 20:50:45.8 | mlflow's 4 workers are ready (`Application startup complete`) |
| 20:51:12 to 20:51:14.7 | inference: `Loaded model models:/food11@champion from http://mlflow:5000` and `Application startup complete` |

So `depends_on` only made Compose start the mlflow container first. The inference container started 3 seconds before mlflow was even listening, and about 19 seconds before mlflow could answer requests, so its first requests to `http://mlflow:5000` failed.

In this case the startup still worked, because the MLflow client retries failed HTTP requests automatically, waiting a bit longer each time (by default it retries 7 times, which can take a few minutes in total). The container stayed on "Waiting for application startup" for about 46 seconds and then loaded the model without any error. I saw the same thing after the `down -v` test: inference had started before 20:53:55, but its request only reached mlflow at 20:54:24, after mlflow was ready at 20:54:11.

If the error doesn't go away (mlflow takes longer than all the retries, or the error is one that isn't retried), the exception comes out of the `lifespan` function in `serve.py`. Uvicorn prints the traceback and `ERROR: Application startup failed. Exiting.`, and the container stops. This happened on my very first `docker compose up`: the registry was still empty, so the client got `RESOURCE_DOES_NOT_EXIST: Registered Model with name=food11 not found`, which is not retried. Since the compose file has no restart policy, the container just stayed exited. The frontend was still running, but every prediction would fail until I restarted inference manually with `docker compose restart inference`.

To make this more robust, I could:

- add a healthcheck to the mlflow service and use `depends_on` with `condition: service_healthy`, so inference only starts once mlflow really answers;
- add a restart policy to inference (`restart: on-failure` or `unless-stopped`), so a failed start is retried automatically;
- handle it in the code, with a retry loop around the model loading, or by loading the model later and having `/health` report "not ready" until the model is loaded.

## Bring the stack up

### Question 7: Run `docker compose ps`. Which services have a published port listed, and which don't? Does that match what you'd expect from the `docker-compose.yml`?

```
NAME                      SERVICE     STATUS          PORTS
mlops-lab-1-frontend-1    frontend    Up 10 minutes   0.0.0.0:8501->8501/tcp, [::]:8501->8501/tcp
mlops-lab-1-inference-1   inference   Up 53 seconds   8000/tcp
mlops-lab-1-mlflow-1      mlflow      Up 10 minutes   0.0.0.0:5000->5000/tcp, [::]:5000->5000/tcp
```

`frontend` and `mlflow` have a published port. `0.0.0.0:8501->8501` means that port 8501 on all the host's network interfaces (IPv4, and IPv6 with `[::]`) is forwarded to port 8501 in the container, and it's the same for 5000.

`inference` only shows `8000/tcp`, without an arrow or a host address. The port is declared in the image (`EXPOSE 8000` in the Dockerfile) and other containers on the Compose network can use it, but it isn't mapped to the host, so `http://127.0.0.1:8000` doesn't reach it from my laptop.

This is what I expected from the compose file, since only `mlflow` and `frontend` have a `ports:` section. The inference container shows "Up 53 seconds" instead of 10 minutes because I restarted it after registering the model: its first start failed with `Registered Model with name=food11 not found`.

To test the whole stack, I opened the frontend at http://127.0.0.1:8501 and uploaded `Fried food/4_0.jpg`, and I got "Prediction: Fried food (96.3%)", which is correct.

## Promote a new model version and reload

The lab asks to move the new version to `Staging`, but stages are deprecated in current MLflow (the UI even shows "Stage (deprecated)"), so I kept using the `champion` alias from Lab 3, which is what `serve.py` loads (`models:/food11@champion`).

Since the volume was new, I first trained a model with the Lab 2 best settings on the mini dataset (5 epochs, lr 0.0001, batch size 32, run `mysterious-carp-824`) and registered it as `food11` version 1 with the `champion` alias. For version 2, I trained with the same settings on the full dataset (run `angry-robin-303`). It got a val_accuracy of 0.818 and a test accuracy of 0.846, which is better than the mini model. I registered it as version 2 of `food11` and moved the `champion` alias from v1 to v2.

### Question 8: Refresh the frontend and upload an image again. Does the prediction come from the new model version, or the old one? Your `serve.py` loads the model once, at startup — what single command lets you pick up the new Staging version without rebuilding any image?

It still came from the old version. After moving the alias, I uploaded the same image (`Fried food/4_0.jpg`) and got exactly the same result as before: Fried food (96.3%).

Moving the alias only changes a pointer in the MLflow registry, and nothing tells the inference service about it. `serve.py` resolves `models:/food11@champion` once, when the container starts, and then keeps that model in memory. So the running container keeps using v1 until it loads the model again.

The command is:

```
docker compose restart inference
```

After the restart, the same image gave Fried food (91.9%). The class is the same but the confidence changed, so the prediction now comes from v2. The confidence is a bit lower on this image, but that doesn't mean v2 is worse: its accuracy on the whole test set is higher (0.846).

### Question 9: Why does `restart` alone work here — no rebuild needed? What does that tell you about what's baked into the inference image versus fetched at container startup?

`docker compose restart` stops and starts the same container, with the same image and the same configuration. When the process starts again, `serve.py` runs its startup code again: it asks the registry which version `champion` points to (now v2) and downloads that version through MLflow's artifact proxy. Nothing in the image had to change, because the model isn't stored in the image.

- The image contains what was decided at build time: the OS, Python, the dependencies (torch, MLflow, FastAPI...) and the serving code. It knows how to serve a model and where to ask for one (`MLFLOW_TRACKING_URI`), but not which model.
- The model itself is downloaded when the container starts, depending on where the alias points at that moment.

So the code and the model are updated separately. Changing the code needs a rebuild, but changing the model only needs moving the alias and restarting, which takes a few seconds. Rolling back is the same, by pointing `champion` back to v1. The downside is that a container serves whatever version the alias pointed to when it started, so after moving the alias, every running inference container has to be restarted to use the new version.

## Persistence check

### Question 10: Is your registered model and its Staging assignment still there after this `down`/`up` cycle? Now try `docker compose down -v` followed by `docker compose up` — what's different this time, and why?

After `docker compose down` and `docker compose up`, everything was still there. The registry showed `food11` with Version 2 as the latest version and `@champion : Version 2`, and the inference service loaded it at startup (`Loaded model models:/food11@champion from http://mlflow:5000`).

`docker compose down` removes the containers and the network, but not the named volumes. The database (`/mlflow-data/mlflow.db`) and the model files (`/mlflow-data/mlruns`) are on the `mlflow-data` volume, so the new mlflow container mounted the same volume and found all the data again.

After `docker compose down -v` and `docker compose up`, everything was gone:

- `down -v` printed `Volume mlops-lab-1_mlflow-data Removed`. The `-v` flag also deletes the named volumes of the compose file.
- `up` printed `Volume mlops-lab-1_mlflow-data Created`, and mlflow logged `Creating initial MLflow database tables...`, so it started with a new empty volume and a new database.
- The Model registry was empty: no `food11`, no versions, no alias, and no runs or experiments.
- The inference service couldn't find its model and stopped: `RESOURCE_DOES_NOT_EXIST: Registered Model with name=food11 not found`, then `Application startup failed. Exiting.` and `inference-1 exited with code 3`.

This shows that the volume is the only place where the state of the system is stored. The containers can be deleted and recreated from their images at any time, but deleting the volume deletes the data for good. In a real setup, this data would need backups, or would be stored outside Docker, in a managed database and object storage.

## Commit your work

### Question 11: This compose file is still meant to run on one machine. What would have to change for the `inference` service to run as three replicas behind a load balancer, or for the mlflow service to survive a machine failure? (You don't need to implement this — just name what Docker Compose can't give you here.)

Docker Compose only manages containers on one Docker host. If that machine goes down, all the services go down with it, and Compose has no idea of a cluster of several machines.

For three inference replicas behind a load balancer:

- Compose can start several copies of a service on the same machine (`docker compose up --scale inference=3`), but they share the same CPU and memory and they all fail together if the machine fails. The traffic is only spread by simple DNS round-robin on the service name, which isn't a real load balancer and doesn't check if a replica is healthy.
- What's missing is a container orchestrator like Kubernetes (or Docker Swarm). It can place the replicas on different machines, put a load balancer (a Service, plus an Ingress for outside traffic) in front of them, use health checks so traffic only goes to replicas whose model is loaded and crashed replicas are restarted or replaced, do rolling updates (for example to load a new `champion` version without downtime), and scale the number of replicas automatically with the load.
- The image would also need to be in a container registry with a fixed tag, so every machine can pull exactly the same image (like in Lab 3, Q9).

For mlflow to survive a machine failure:

- Right now its state is a SQLite file and model files on a local volume, on one machine's disk. If that machine dies, the data is lost or unreachable, and a SQLite file can't be shared by several servers.
- The database would have to be moved to a replicated database server like PostgreSQL or MySQL (for example a managed one like AWS RDS or Cloud SQL), with backups, and the artifacts to object storage like S3, GCS, Azure Blob or MinIO. Then the mlflow server itself doesn't store anything, so several copies can run on different machines behind a load balancer, and an orchestrator can restart them on another machine if one fails.
- Compose also doesn't handle other things needed across machines, like secrets management for the database credentials, monitoring, and TLS and authentication, since right now the mlflow server is open without any access control.