#!/usr/bin/env bash
# SEEN — deploy the app to Google Cloud Run (macOS/Linux/Cloud Shell). Cloud Build builds the image.
#   deploy/deploy_cloudrun.sh PROJECT_ID [REGION=asia-south1] [SERVICE=seen] [PROVIDER=gemini|nebius|none]
# The API key is read from .env (GEMINI_API_KEY / NEBIUS_API_KEY) into Secret Manager and never printed.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="${1:?usage: deploy/deploy_cloudrun.sh PROJECT_ID [REGION] [SERVICE] [PROVIDER]}"
REGION="${2:-asia-south1}"; SERVICE="${3:-seen}"; PROVIDER="${4:-gemini}"
command -v gcloud >/dev/null || { echo "gcloud not found: https://cloud.google.com/sdk/docs/install"; exit 1; }
[ -f data/seen.duckdb ] || { echo "data/seen.duckdb missing - run the pipeline first"; exit 1; }

case "$PROVIDER" in
  gemini) KEYNAME=GEMINI_API_KEY; SECRET=gemini-api-key ;;
  nebius) KEYNAME=NEBIUS_API_KEY; SECRET=nebius-api-key ;;
  *) KEYNAME=""; SECRET="" ;;
esac

echo "=== 1/4 project and APIs ==="
gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

SECRET_ARGS=()
if [ -n "$KEYNAME" ]; then
  echo "=== 2/4 API key -> Secret Manager ($SECRET) ==="
  KEY="$( [ -f .env ] && grep -E "^${KEYNAME}=" .env | head -1 | cut -d= -f2- | tr -d '"'"'" || true )"
  if [ -z "$KEY" ]; then
    echo "$KEYNAME is empty in .env - the app will run in TEMPLATE mode."
  else
    if gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
      printf '%s' "$KEY" | gcloud secrets versions add "$SECRET" --data-file=-
    else
      printf '%s' "$KEY" | gcloud secrets create "$SECRET" --data-file=- --replication-policy=automatic
    fi
    PROJNUM="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
    gcloud secrets add-iam-policy-binding "$SECRET" \
      --member="serviceAccount:${PROJNUM}-compute@developer.gserviceaccount.com" \
      --role="roles/secretmanager.secretAccessor" >/dev/null
    SECRET_ARGS=(--set-secrets="${KEYNAME}=${SECRET}:latest")
  fi
else
  echo "=== 2/4 no API key for provider $PROVIDER - TEMPLATE mode ==="
fi

echo "=== 3/4 build and deploy (3-6 minutes the first time) ==="
gcloud run deploy "$SERVICE" --source . --region "$REGION" --platform managed --allow-unauthenticated \
  --memory 1Gi --cpu 1 --min-instances 1 --max-instances 3 --concurrency 40 --timeout 3600 --session-affinity \
  --set-env-vars "LLM_PROVIDER=${PROVIDER},SEEN_USER_AGENT=SEEN-hackathon/0.1 (contact: see repository README),SEEN_DEPLOYMENT=cloudrun" \
  "${SECRET_ARGS[@]}"

echo "=== 4/4 done ==="
URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo "SEEN is live at: $URL"
echo "(after judging: gcloud run services update $SERVICE --region $REGION --min-instances 0)"
