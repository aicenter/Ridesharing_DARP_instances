# Deploying the graph editor and the builder service

Two deployables live in this directory:

| what | where | how |
|---|---|---|
| the editor (static files from `npm run build`) | <https://fido.ninja/darp-instances-editor/> | GitHub Actions workflow [`deploy-gui.yml`](../../.github/workflows/deploy-gui.yml), FTP upload on every push to `main` touching `web/graph-editor/` |
| the builder service (`server/`, `POST /instances`) | <https://mi.fido.ninja> (Google Cloud Run, service `darp-builder`) | [`Dockerfile`](../../Dockerfile) at the repository root, `gcloud run deploy --source .` |

The editor build uses a relative base (`base: './'` in `vite.config.ts`), so the same `dist/` works in the hosting subfolder and at the root of the service.

## Editor: GitHub Actions over FTP

Repository settings → Secrets and variables → Actions:

- secrets `FTP_SERVER`, `FTP_USERNAME`, `FTP_PASSWORD`;
- variables `FTP_PROTOCOL` (`ftp` or `ftps`) and `FTP_SERVER_DIR` (target folder relative to the FTP root, e.g. `www/darp-instances-editor/`; the action creates it and keeps its sync state in `.ftp-deploy-sync-state.json` there).

The workflow runs the unit tests, builds, and uploads `dist/`. It can also be started by hand from the Actions tab (`workflow_dispatch`).

## Builder service: Google Cloud Run

One-time setup (Google Cloud CLI installed, <https://cloud.google.com/sdk/docs/install>):

```bash
gcloud init                                  # log in, pick (or create) the project
gcloud config set run/region europe-west1   # optional: default region, so later commands can omit --region
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

Use a dedicated project for the service: the spending protection is per project. In the console, Billing → Budgets & alerts, create

1. a **spend cap** budget (budget type "Spend cap", scope: the project and the Cloud Run service, e.g. 5 € per month): when reached, Cloud Run in the project is paused until the cap is lifted by hand;
2. a normal **alerts** budget with e-mail thresholds (50 / 90 / 100 %) as the early warning. An alerts budget cannot be turned into a spend cap later.

Deploy (first time and every update) from the repository root:

```bash
gcloud run deploy darp-builder --source . \
  --region europe-west1 --allow-unauthenticated \
  --cpu 1 --memory 1Gi --concurrency 1 --max-instances 1 --min-instances 0 \
  --timeout 60 --port 8080
```

- The first run offers to create the Artifact Registry repository `cloud-run-source-deploy`; accept. Cloud Build builds the image (several minutes: the base image ships Chromium) and the command prints the service URL.
- `--max-instances 1` with `--concurrency 1` bounds the worst case to one busy instance; `--min-instances 0` scales to zero when idle (the first request after a pause starts the container and Chromium, a few seconds).
- Later deployments remember the flags: `gcloud run deploy darp-builder --source .` is enough.
- Artifact Registry keeps every built image (about 1.5 GB each). Add a cleanup policy to the repository (keep the most recent versions) or delete old images now and then.

Check:

```bash
URL=https://mi.fido.ninja   # or the *.run.app URL printed by the deployment
curl -s "$URL/health"
curl -s -X POST "$URL/instances" -H "content-type: application/json" --data @web/graph-editor/examples/small-darp.json | head -c 300
```

### Custom domain

`mi.fido.ninja` is a Cloud Run domain mapping to the service; the DNS of `fido.ninja` (Namecheap) has a CNAME `mi` → `ghs.googlehosted.com`. Google issues and renews the certificate. The mapping is independent of the deployments, so it needs no care after a redeploy. One-time setup, if ever needed again:

```bash
gcloud domains verify fido.ninja          # adds a TXT record at the domain apex
gcloud beta run domain-mappings create --service darp-builder --domain mi.fido.ninja --region europe-west1
```

### Running the container locally

```bash
docker build -t darp-builder .            # repository root
docker run --rm -p 8080:8080 darp-builder
```

The image is `mcr.microsoft.com/playwright:<playwright version>-noble`; its tag must equal the `playwright` version pinned in `package.json` (it ships the matching Chromium). Bump both together.

### Without Docker

`npm run build && npm run serve` starts the service on `http://0.0.0.0:8080/` with the locally installed Playwright Chromium. Environment: `PORT`, `DARP_CHROMIUM_PATH`, `DARP_NO_RENDER=1` (no pictures), `DARP_MAX_NODES`, `DARP_MAX_EDGES`, `DARP_MAX_VEHICLES`, `DARP_MAX_REQUESTS` (request limits; defaults 200 / 2000 / 100 / 500).
