# Deploy TruthScope Backend to Google Cloud Run

## 📋 Prerequisites

1. **Google Cloud CLI installed** - Download from: https://cloud.google.com/sdk/docs/install
2. **Authenticated with Google Cloud**:
   ```cmd
   gcloud auth login
   gcloud auth application-default login
   ```
3. **Database password ready** - Get your Cloud SQL postgres password

## 🚀 Quick Deployment (Windows)

### Option 1: Automated Script (Easiest)

1. **Open the deployment script**:
   ```cmd
   cd c:\Users\biswa\OneDrive\Desktop\TruthScope-Final\extension\backend
   notepad deploy.bat
   ```

2. **Edit line 47** - Replace `your-db-password-here` with your actual database password:
   ```batch
   --set-env-vars "GCP_PROJECT_ID=%PROJECT_ID%,GCP_LOCATION=%REGION%,DB_USER=postgres,DB_PASSWORD=YOUR_ACTUAL_PASSWORD,DB_NAME=news_analysis_db,CLOUD_SQL_CONNECTION_NAME=%CLOUD_SQL_INSTANCE%"
   ```

3. **Run the script**:
   ```cmd
   deploy.bat
   ```

4. **Wait 3-5 minutes** for deployment to complete

5. **Copy the service URL** displayed at the end (looks like: `https://truthscope-text-analysis-xxxxx-uc.a.run.app`)

### Option 2: Manual Deployment

```cmd
cd c:\Users\biswa\OneDrive\Desktop\TruthScope-Final\extension\backend

REM Set project
gcloud config set project truthscope-prod-2025

REM Enable APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com aiplatform.googleapis.com translate.googleapis.com

REM Deploy to Cloud Run
gcloud run deploy truthscope-text-analysis --source . --region us-central1 --platform managed --allow-unauthenticated --memory 2Gi --cpu 2 --timeout 300 --max-instances 10 --min-instances 0 --concurrency 80 --add-cloudsql-instances truthscope-prod-2025:us-central1:truthscope-db --set-env-vars "GCP_PROJECT_ID=truthscope-prod-2025,GCP_LOCATION=us-central1,DB_USER=postgres,DB_PASSWORD=YOUR_DB_PASSWORD,DB_NAME=news_analysis_db,CLOUD_SQL_CONNECTION_NAME=truthscope-prod-2025:us-central1:truthscope-db"
```

**Important**: Replace `YOUR_DB_PASSWORD` with your actual database password!

## 📝 Post-Deployment Steps

### 1. Test the Deployed Service

```cmd
REM Get service URL
gcloud run services describe truthscope-text-analysis --region us-central1 --format "value(status.url)"

REM Test health endpoint
curl https://YOUR-SERVICE-URL.run.app/
```

### 2. Update Chrome Extension

Edit `extension/frontend/background.js`:

```javascript
// Change from localhost to your Cloud Run URL
const TEXT_ANALYSIS_URL = 'https://truthscope-text-analysis-xxxxx-uc.a.run.app/analyze';
```

### 3. Add Cloud Run URL to OAuth Redirect URIs

1. Go to: https://console.cloud.google.com/apis/credentials
2. Click on your OAuth 2.0 Client ID
3. Under "Authorized redirect URIs", add:
   - `https://YOUR-SERVICE-URL.run.app/*`
4. Click **Save**

### 4. Reload Chrome Extension

1. Go to `chrome://extensions`
2. Click **Reload** button on your extension
3. Test by analyzing a news article

## 🔍 Monitoring & Logs

### View Logs
```cmd
gcloud run services logs read truthscope-text-analysis --region us-central1 --limit 50
```

### View Real-Time Logs
```cmd
gcloud run services logs tail truthscope-text-analysis --region us-central1
```

### Check Service Status
```cmd
gcloud run services describe truthscope-text-analysis --region us-central1
```

### View in Console
Open: https://console.cloud.google.com/run?project=truthscope-prod-2025

## 💰 Cost Optimization

Current configuration:
- **Memory**: 2GB (adjust if needed)
- **CPU**: 2 vCPUs (adjust if needed)
- **Min instances**: 0 (scale to zero when idle - saves money!)
- **Max instances**: 10 (prevent runaway costs)
- **Timeout**: 300 seconds (5 minutes)

Estimated cost: **$0-5/month** for light usage (Free tier covers most of it)

## 🛠️ Update Deployed Service

After making code changes:

```cmd
cd c:\Users\biswa\OneDrive\Desktop\TruthScope-Final\extension\backend
gcloud run deploy truthscope-text-analysis --source . --region us-central1
```

Cloud Run will automatically rebuild and redeploy.

## ⚠️ Troubleshooting

### "Permission denied" errors
```cmd
gcloud auth login
gcloud config set project truthscope-prod-2025
```

### "Cloud SQL connection failed"
- Verify Cloud SQL instance is running: `gcloud sql instances list`
- Check connection name matches: `truthscope-prod-2025:us-central1:truthscope-db`
- Verify database password is correct

### "Deployment timeout"
- Increase timeout: Add `--timeout 600` to deploy command
- Check build logs: `gcloud builds list --limit 5`

### "Container failed to start"
Check logs for errors:
```cmd
gcloud run services logs read truthscope-text-analysis --region us-central1 --limit 100
```

### "Out of memory" errors
Increase memory allocation:
```cmd
gcloud run services update truthscope-text-analysis --memory 4Gi --region us-central1
```

## 🔐 Security Notes

- Service is currently set to `--allow-unauthenticated` for Chrome extension access
- Database credentials are stored as environment variables in Cloud Run
- Cloud Run uses Google's managed SSL certificates automatically
- Enable Cloud Armor for DDoS protection if needed

## 📊 Scaling Information

Cloud Run automatically scales based on traffic:
- **Cold start**: ~5-10 seconds (first request after idle)
- **Warm requests**: ~50-500ms
- **Concurrent requests per instance**: 80
- **Auto-scaling**: 0 to 10 instances

## 🎯 Next Steps

1. ✅ Deploy backend to Cloud Run
2. ✅ Update extension with Cloud Run URL
3. ✅ Add Cloud Run URL to OAuth config
4. ✅ Test end-to-end flow
5. 📊 Monitor logs and performance
6. 💰 Review billing after first week

## 📚 Additional Resources

- Cloud Run docs: https://cloud.google.com/run/docs
- Cloud SQL connector: https://cloud.google.com/sql/docs/postgres/connect-run
- Pricing calculator: https://cloud.google.com/products/calculator

---

**Need help?** Check the logs first:
```cmd
gcloud run services logs read truthscope-text-analysis --region us-central1 --limit 50
```
