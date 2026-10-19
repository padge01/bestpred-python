# Hosting (Google Cloud Run)

Live since 19 Oct 2026 at **https://bestpred.dairydatascience.com** (MCP endpoint `/mcp`; pages `/`, `/privacy`,
`/llms.txt`). That name is a Cloudflare Worker (`dds-bestpred`, his personal Cloudflare account) forwarding to the Cloud
Run service https://bestpred-455691864978.us-west1.run.app. The Cloudflare token (DNS and Workers, dairydatascience.com
only) is on Jess: `/etc/credstore.encrypted/dds_cloudflare_api_token` (systemd-creds). Project `dairydatascience` (account dairydatascience@gmail.com), region us-west1, budget $10 a month.

Limits: 0 to 2 instances (scales to zero when idle), 512 MiB, 1 CPU, 20 calls per instance, 60 s per call, 5 MB a
call (in the app). Nothing stored.

Release a new version:

```bash
gcloud builds submit . --config cloudbuild.yaml --substitutions=_IMAGE=us-west1-docker.pkg.dev/dairydatascience/images/bestpred-mcp:VERSION
gcloud run deploy bestpred --image us-west1-docker.pkg.dev/dairydatascience/images/bestpred-mcp:VERSION --region us-west1 \
  --allow-unauthenticated --min-instances 0 --max-instances 2 --memory 512Mi --cpu 1 --concurrency 20 --timeout 60
```

One-time setup done: Artifact Registry repo `images` (us-west1); the Compute default service account has
cloudbuild.builds.builder, storage.objectViewer, artifactregistry.writer and logging.logWriter.

Still to do: the OpenAI domain token (`OPENAI_APPS_CHALLENGE` env var) and the directory submissions as an MCP
connector. The Ration Lab takes rationlab.dairydatascience.com the same way.
