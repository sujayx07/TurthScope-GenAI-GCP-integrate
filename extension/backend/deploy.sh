#!/bin/bash

# TruthScope Backend - Cloud Run Deployment Script
# This script deploys both text and media analysis services to Google Cloud Run

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="${GCP_PROJECT_ID}"
REGION="${GCP_LOCATION:-us-central1}"
CLOUD_SQL_INSTANCE="${CLOUD_SQL_CONNECTION_NAME}"

# Service names
TEXT_SERVICE="truthscope-text-analysis"
MEDIA_SERVICE="truthscope-media-analysis"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}TruthScope Backend Deployment to Cloud Run${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if project ID is set
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: GCP_PROJECT_ID environment variable is not set${NC}"
    echo "Please set it with: export GCP_PROJECT_ID=your-project-id"
    exit 1
fi

# Set the project
echo -e "${YELLOW}Setting GCP project to: $PROJECT_ID${NC}"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo -e "${YELLOW}Enabling required GCP APIs...${NC}"
gcloud services enable \
    run.googleapis.com \
    sqladmin.googleapis.com \
    aiplatform.googleapis.com \
    vision.googleapis.com \
    speech.googleapis.com \
    translate.googleapis.com \
    cloudbuild.googleapis.com

echo -e "${GREEN}✓ APIs enabled${NC}"
echo ""

# Function to deploy a service
deploy_service() {
    local SERVICE_NAME=$1
    local ENTRY_POINT=$2
    
    echo -e "${YELLOW}Deploying $SERVICE_NAME...${NC}"
    
    gcloud run deploy $SERVICE_NAME \
        --source . \
        --region $REGION \
        --platform managed \
        --allow-unauthenticated \
        --memory 2Gi \
        --cpu 2 \
        --timeout 300 \
        --max-instances 10 \
        --min-instances 0 \
        --concurrency 80 \
        --add-cloudsql-instances $CLOUD_SQL_INSTANCE \
        --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,GCP_LOCATION=$REGION" \
        --command "gunicorn" \
        --args "--bind,:$PORT,--workers,1,--threads,8,--timeout,300,--log-level,info,$ENTRY_POINT"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $SERVICE_NAME deployed successfully${NC}"
        
        # Get the service URL
        SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')
        echo -e "${GREEN}Service URL: $SERVICE_URL${NC}"
    else
        echo -e "${RED}✗ Failed to deploy $SERVICE_NAME${NC}"
        exit 1
    fi
    echo ""
}

# Deploy text analysis service
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Deploying Text Analysis Service${NC}"
echo -e "${YELLOW}========================================${NC}"
deploy_service $TEXT_SERVICE "check_text:app"

# Deploy media analysis service
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Deploying Media Analysis Service${NC}"
echo -e "${YELLOW}========================================${NC}"
deploy_service $MEDIA_SERVICE "check_media:app"

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Text Analysis Service: $(gcloud run services describe $TEXT_SERVICE --region $REGION --format 'value(status.url)')"
echo -e "Media Analysis Service: $(gcloud run services describe $MEDIA_SERVICE --region $REGION --format 'value(status.url)')"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Set environment variables via Secret Manager or Cloud Run console"
echo "2. Configure your frontend to use the new service URLs"
echo "3. Test the endpoints with sample requests"
echo "4. Monitor logs: gcloud run logs read --service=$TEXT_SERVICE --region=$REGION"
echo ""
echo -e "${GREEN}Deployment script completed successfully!${NC}"
