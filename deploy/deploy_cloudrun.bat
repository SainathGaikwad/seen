@echo off
REM SEEN - deploy the app to Google Cloud Run from Windows (no Docker needed; Cloud Build builds the image).
REM
REM   deploy\deploy_cloudrun.bat PROJECT_ID [REGION] [SERVICE] [PROVIDER]
REM
REM   PROJECT_ID  your Google Cloud project (billing enabled; Cloud Run has a free tier)
REM   REGION      default asia-south1 (Mumbai). asia-southeast1 = Singapore.
REM   SERVICE     default seen            (use seen-nemotron for the Nebius/NVIDIA variant)
REM   PROVIDER    default gemini          (gemini | nebius | none)
REM
REM The API key is read from .env (GEMINI_API_KEY or NEBIUS_API_KEY) and stored in Secret Manager.
REM It is never printed. Run this from the project folder (the one with config.yaml).
setlocal EnableDelayedExpansion
cd /d "%~dp0\.."

set PROJECT=%1
set REGION=%2
set SERVICE=%3
set PROVIDER=%4
if "%PROJECT%"=="" (
  echo Usage: deploy\deploy_cloudrun.bat PROJECT_ID [REGION] [SERVICE] [PROVIDER]
  exit /b 1
)
if "%REGION%"=="" set REGION=asia-south1
if "%SERVICE%"=="" set SERVICE=seen
if "%PROVIDER%"=="" set PROVIDER=gemini

where gcloud >nul 2>nul || (
  echo gcloud not found. Install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install
  exit /b 1
)
if not exist data\seen.duckdb (
  echo data\seen.duckdb is missing - run the pipeline first ^(run_windows.bat run^) so the image has data.
  exit /b 1
)

if /i "%PROVIDER%"=="gemini" (set KEYNAME=GEMINI_API_KEY& set SECRET=gemini-api-key)
if /i "%PROVIDER%"=="nebius" (set KEYNAME=NEBIUS_API_KEY& set SECRET=nebius-api-key)

echo === 1/4 project and APIs ===
call gcloud config set project %PROJECT% || exit /b 1
call gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com || exit /b 1

set SECRET_ARGS=
if not "%KEYNAME%"=="" (
  echo === 2/4 API key -^> Secret Manager ^(%SECRET%^) ===
  set "KEY="
  if exist .env for /f "usebackq tokens=1,* delims==" %%a in (".env") do if /i "%%a"=="%KEYNAME%" set "KEY=%%b"
  if "!KEY!"=="" (
    echo %KEYNAME% is empty in .env - the app will run in TEMPLATE mode ^(no model prose, no translation^).
  ) else (
    REM the key goes through a temporary file (no newline) that is deleted straight after
    set "KEYFILE=%TEMP%\seen_%SECRET%.txt"
    <nul set /p "=!KEY!" > "!KEYFILE!"
    call gcloud secrets describe %SECRET% >nul 2>nul
    if errorlevel 1 (
      call gcloud secrets create %SECRET% --data-file="!KEYFILE!" --replication-policy=automatic || (del "!KEYFILE!" & exit /b 1)
    ) else (
      call gcloud secrets versions add %SECRET% --data-file="!KEYFILE!" || (del "!KEYFILE!" & exit /b 1)
    )
    del "!KEYFILE!"
    for /f "usebackq delims=" %%n in (`gcloud projects describe %PROJECT% --format="value(projectNumber)"`) do set PROJNUM=%%n
    call gcloud secrets add-iam-policy-binding %SECRET% --member="serviceAccount:!PROJNUM!-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" >nul || exit /b 1
    set SECRET_ARGS=--set-secrets=%KEYNAME%=%SECRET%:latest
  )
) else (
  echo === 2/4 no API key for provider %PROVIDER% - TEMPLATE mode ===
)

echo === 3/4 build and deploy ^(3-6 minutes the first time^) ===
call gcloud run deploy %SERVICE% --source . --region %REGION% --platform managed --allow-unauthenticated ^
  --memory 1Gi --cpu 1 --min-instances 1 --max-instances 3 --concurrency 40 --timeout 3600 --session-affinity ^
  --set-env-vars "LLM_PROVIDER=%PROVIDER%,SEEN_USER_AGENT=SEEN-hackathon/0.1 (contact: see repository README),SEEN_DEPLOYMENT=cloudrun" ^
  %SECRET_ARGS% || exit /b 1

echo === 4/4 done ===
for /f "usebackq delims=" %%u in (`gcloud run services describe %SERVICE% --region %REGION% --format="value(status.url)"`) do set URL=%%u
echo.
echo SEEN is live at: %URL%
echo (min-instances=1 keeps it warm for judges; after judging run:  gcloud run services update %SERVICE% --region %REGION% --min-instances 0)
endlocal
