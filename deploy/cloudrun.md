# Deploying SEEN to Google Cloud Run

The AI Builder Cup requires the prototype to run on **Cloud Run or Firebase** and to use **Gemini/Gemma**.
SEEN already uses Gemini through `google-genai`; this folder adds the Cloud Run deployment.

What gets deployed: the Streamlit app (`app/`) plus the analysed data (`data/seen.duckdb`, `data/derived/`)
baked into the image, so the hosted app shows the same Unseen XI, kits and translations as your laptop.
The pipeline itself (Cricsheet → graph → gap model → kits) stays a local/batch job: re-run it, redeploy.

```
Browser ──► Cloud Run (seen, asia-south1) ──► Streamlit app ──► DuckDB + derived JSON (in image)
                     │                              └──► Gemini API (google-genai) for "Translate now" / "Rewrite with Gemini"
                     └── Secret Manager: GEMINI_API_KEY
```

## One-time setup (15 minutes)

1. Google Cloud account with **billing enabled** (Cloud Run has a free tier; a warm 1 vCPU / 1 GiB instance costs
   roughly ₹10–20 per day while `--min-instances 1` is set — switch it to 0 after judging).
2. Create a project (or reuse one) and note its **Project ID**.
3. Install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install — then in a new terminal:
   `gcloud auth login` and `gcloud auth application-default login` (both open the browser; sign in yourself).
4. Make sure `.env` in the project folder has `LLM_PROVIDER=gemini` and your `GEMINI_API_KEY`.
   For judging, a pay-as-you-go key (AI Studio → billing on) avoids the free tier's ~20 requests/day cap.

## Deploy (Windows)

```
deploy\deploy_cloudrun.bat YOUR_PROJECT_ID
```

(macOS/Linux/Cloud Shell: `bash deploy/deploy_cloudrun.sh YOUR_PROJECT_ID`.)

The script enables the APIs, stores the API key from `.env` in **Secret Manager** (never printed, never in the
image), builds the image with Cloud Build from the `Dockerfile`, and deploys service `seen` in `asia-south1`
(Mumbai) with `--session-affinity` (Streamlit keeps a websocket per visitor) and `--min-instances 1` (no cold start
when a judge opens it). It prints the public URL at the end — that is the "Functional Prototype" link for the submission.

Optional arguments: `deploy\deploy_cloudrun.bat PROJECT_ID asia-southeast1 seen gemini`
(region, service name, provider). The Nebius × NVIDIA variant is the same image with the Nemotron provider:
`deploy\deploy_cloudrun.bat PROJECT_ID asia-south1 seen-nemotron nebius` (needs `NEBIUS_API_KEY` in `.env`).

## Redeploy after a pipeline run

Run `run_windows.bat run` as usual (close the app first), then the deploy command again. Only the changed layer
(data + code) is rebuilt; 2–3 minutes.

## Check it is healthy

- Open the URL: the Home page should show the Unseen XI within ~5 s.
- `https://<url>/_stcore/health` returns `ok`.
- Logs: `gcloud run services logs read seen --region asia-south1 --limit 50`.
- Something off with the key? `gcloud run services describe seen --region asia-south1` shows the env/secret wiring.

## Costs and clean-up

- After the finale: `gcloud run services update seen --region asia-south1 --min-instances 0` (scale to zero),
  or delete: `gcloud run services delete seen --region asia-south1`.
- The secret stays in Secret Manager (free for the first few); delete with `gcloud secrets delete gemini-api-key`.

## Local test of the exact container (optional, needs Docker Desktop)

```
docker build -t seen .
docker run --rm -p 8080:8080 -e PORT=8080 --env-file .env seen
```
Then open http://localhost:8080.
