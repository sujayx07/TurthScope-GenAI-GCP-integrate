# TruthScope Backend - Quick Setup Guide

## Prerequisites
1. Google Cloud Platform account with billing enabled
2. `gcloud` CLI installed and authenticated
3. Docker installed (for local testing)

## Initial Setup

### 1. Create GCP Project
```bash
gcloud projects create truthscope-prod --name="TruthScope Production"
gcloud config set project truthscope-prod
gcloud alpha billing accounts list
gcloud alpha billing projects link truthscope-prod --billing-account=YOUR_BILLING_ACCOUNT_ID
```

### 2. Enable Required APIs
```bash
gcloud services enable \
    run.googleapis.com \
    sqladmin.googleapis.com \
    aiplatform.googleapis.com \
    vision.googleapis.com \
    speech.googleapis.com \
    translate.googleapis.com \
    cloudbuild.googleapis.com \
    customsearch.googleapis.com
```

### 3. Create Cloud SQL Instance
```bash
gcloud sql instances create truthscope-db \
    --database-version=POSTGRES_15 \
    --tier=db-g1-small \
    --region=us-central1 \
    --root-password=YOUR_SECURE_PASSWORD

# Create database
gcloud sql databases create news_analysis_db --instance=truthscope-db

# Create user
gcloud sql users create appuser --instance=truthscope-db --password=YOUR_APP_PASSWORD
```

### 4. Set Up Database Schema
```bash
# Connect to database
gcloud sql connect truthscope-db --user=postgres

# Run the schema from db.sql
\i /path/to/db.sql
```

### 5. Configure Custom Search
1. Go to: https://programmablesearchengine.google.com/
2. Create a new search engine
3. Configure to search entire web with emphasis on news sites
4. Note your **Search Engine ID**
5. Get API Key from: https://console.cloud.google.com/apis/credentials

### 6. Set Environment Variables
```bash
# Copy example file
cp .env.example .env

# Edit .env with your values
nano .env

# Key variables to set:
# - GCP_PROJECT_ID
# - CLOUD_SQL_CONNECTION_NAME
# - GOOGLE_CUSTOM_SEARCH_ENGINE_ID
# - All API keys and passwords
```

### 7. Local Testing (Optional)
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
export $(cat .env | xargs)
python check_text.py

# In another terminal
python check_media.py
```

### 8. Deploy to Cloud Run
```bash
# Make script executable
chmod +x deploy.sh

# Export required variables
export GCP_PROJECT_ID=truthscope-prod
export GCP_LOCATION=us-central1
export CLOUD_SQL_CONNECTION_NAME=truthscope-prod:us-central1:truthscope-db

# Run deployment
./deploy.sh
```

### 9. Configure Secrets (Recommended)
```bash
# Create secrets in Secret Manager
echo -n "YOUR_DB_PASSWORD" | gcloud secrets create db-password --data-file=-
echo -n "YOUR_API_KEY" | gcloud secrets create google-api-key --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding db-password \
    --member=serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
```

### 10. Test Deployment
```bash
# Get service URLs
TEXT_URL=$(gcloud run services describe truthscope-text-analysis --region us-central1 --format 'value(status.url)')
MEDIA_URL=$(gcloud run services describe truthscope-media-analysis --region us-central1 --format 'value(status.url)')

# Test text analysis
curl -X POST $TEXT_URL/analyze \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "url": "https://example.com/article",
    "article_text": "Test article content..."
  }'

# Test media analysis
curl -X POST $MEDIA_URL/analyze_image \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "media_url": "https://example.com/image.jpg"
  }'
```

## Quick Commands

### View Logs
```bash
# Text service
gcloud run logs read --service=truthscope-text-analysis --region=us-central1 --limit=50

# Media service
gcloud run logs read --service=truthscope-media-analysis --region=us-central1 --limit=50
```

### Update Service
```bash
# Redeploy after code changes
gcloud run deploy truthscope-text-analysis --source . --region us-central1
```

### Scale Service
```bash
# Set min/max instances
gcloud run services update truthscope-text-analysis \
    --region us-central1 \
    --min-instances 1 \
    --max-instances 20
```

### Monitor Costs
```bash
# View billing
gcloud billing accounts list
gcloud billing projects describe truthscope-prod
```

## Troubleshooting

### Service won't start
1. Check logs: `gcloud run logs read --service=SERVICE_NAME --region=us-central1`
2. Verify environment variables are set correctly
3. Confirm Cloud SQL instance is running
4. Check IAM permissions for service account

### Database connection fails
1. Verify Cloud SQL instance name format: `project:region:instance`
2. Check if Cloud SQL API is enabled
3. Verify service account has Cloud SQL Client role
4. Test connection: `gcloud sql connect truthscope-db --user=postgres`

### API quota exceeded
1. Check quota: `gcloud compute project-info describe`
2. Request increase: https://console.cloud.google.com/iam-admin/quotas
3. Implement rate limiting in application

### High latency
1. Check region proximity to users
2. Increase Cloud Run CPU/memory allocation
3. Enable Cloud CDN for static assets
4. Consider multi-region deployment

## Cost Optimization

1. **Cloud Run**: Set appropriate min/max instances
2. **Cloud SQL**: Use smaller tier for dev/test
3. **Vertex AI**: Use Gemini Flash instead of Pro when possible
4. **Translation API**: Cache results to reduce calls
5. **Vision API**: Batch process when possible

## Security Best Practices

1. Use Secret Manager for sensitive data
2. Enable Cloud Armor for DDoS protection
3. Implement rate limiting per user
4. Use IAM service accounts with minimal permissions
5. Enable Cloud Audit Logs
6. Regular security audits

## Maintenance

### Regular Tasks
- [ ] Weekly: Review logs for errors
- [ ] Monthly: Check and optimize costs
- [ ] Monthly: Update dependencies
- [ ] Quarterly: Security audit
- [ ] Quarterly: Performance review

### Backup Strategy
- Cloud SQL: Automated daily backups (enabled by default)
- Secrets: Versioned in Secret Manager
- Code: Git repository with tags for releases

## Support Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud SQL Documentation](https://cloud.google.com/sql/docs)
- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Cloud Vision API](https://cloud.google.com/vision/docs)
- [GCP Status Dashboard](https://status.cloud.google.com/)

## Emergency Contacts

- GCP Support: https://cloud.google.com/support
- On-call: [Your team's contact]
- Escalation: [Manager contact]
