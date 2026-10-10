# SEEN — container image for Google Cloud Run (also runs anywhere Docker runs).
#
#   gcloud run deploy seen --source . --region asia-south1 ...   (see deploy/cloudrun.md)
#   docker build -t seen . && docker run -p 8080:8080 -e PORT=8080 --env-file .env seen
#
# The image bakes in the analysed data (data/seen.duckdb + data/derived) so the app serves the
# current Unseen XI without re-running the pipeline. Re-run the pipeline locally, then redeploy.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUTF8=1 \
    PORT=8080

WORKDIR /app

# Dependencies first (cached layer). The LLM SDKs are optional for the pipeline but cheap to include:
# google-genai for Gemini (AI Builder Cup), openai for Nebius Token Factory / Nemotron (Nebius x NVIDIA).
COPY requirements.txt .
RUN pip install -r requirements.txt "google-genai>=1.0" "openai>=1.30"

# Application code + analysed data (.dockerignore keeps raw downloads, caches and .env out)
COPY . .

# Streamlit reads .streamlit/config.toml (headless, minimal toolbar, theme); the port comes from Cloud Run's $PORT.
RUN useradd --create-home --uid 1000 seen && chown -R seen:seen /app
USER seen

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8080\")}/_stcore/health')" || exit 1

CMD ["sh", "-c", "streamlit run app/Home.py --server.port=${PORT} --server.address=0.0.0.0"]
