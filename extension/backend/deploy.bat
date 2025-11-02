@echo off
REM TruthScope Backend - Cloud Run Deployment Script (Windows)
REM This script deploys the text analysis service to Google Cloud Run

echo ========================================
echo TruthScope Backend - Cloud Run Deployment
echo ========================================
echo.

REM Check if gcloud is installed
where gcloud >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: gcloud CLI is not installed
    echo Please install it from: https://cloud.google.com/sdk/docs/install
    pause
    exit /b 1
)

REM Set project configuration
set PROJECT_ID=truthscope-prod-2025
set REGION=us-central1
set SERVICE_NAME=truthscope-text-analysis
set CLOUD_SQL_INSTANCE=truthscope-prod-2025:us-central1:truthscope-db

echo Setting GCP project to: %PROJECT_ID%
gcloud config set project %PROJECT_ID%

echo.
echo Enabling required APIs...
gcloud services enable run.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com aiplatform.googleapis.com translate.googleapis.com

echo.
echo ========================================
echo Deploying to Cloud Run...
echo ========================================
echo This will take 3-5 minutes...
echo.

gcloud run deploy %SERVICE_NAME% ^
    --source . ^
    --region %REGION% ^
    --platform managed ^
    --allow-unauthenticated ^
    --memory 2Gi ^
    --cpu 2 ^
    --timeout 300 ^
    --max-instances 10 ^
    --min-instances 0 ^
    --concurrency 80 ^
    --add-cloudsql-instances %CLOUD_SQL_INSTANCE% ^
    --set-env-vars "GCP_PROJECT_ID=%PROJECT_ID%,GCP_LOCATION=%REGION%,DB_USER=appuser,DB_PASSWORD=AppUserPassword456!,DB_NAME=news_analysis_db,CLOUD_SQL_CONNECTION_NAME=%CLOUD_SQL_INSTANCE%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Deployment Successful!
    echo ========================================
    echo.
    echo Getting service URL...
    gcloud run services describe %SERVICE_NAME% --region %REGION% --format "value(status.url)"
    echo.
    echo IMPORTANT: Update your Chrome extension background.js with the service URL above
) else (
    echo.
    echo ERROR: Deployment failed!
    echo Check the error messages above for details.
)

echo.
pause
