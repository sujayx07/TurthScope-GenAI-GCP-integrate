# TruthScope Backend - Pre-Deployment Checklist

## ✅ Verification Steps

Run these commands to verify your setup before deployment:

### 1. Check Python Version
```bash
python --version
# Should be Python 3.11 or higher
```

### 2. Install Dependencies
```bash
cd extension/backend
pip install -r requirements.txt
```

### 3. Verify GCP CLI
```bash
gcloud --version
gcloud auth list
gcloud config get-value project
```

### 4. Check Environment Variables
```bash
# Copy and edit the example file
cp .env.example .env
nano .env  # or use your preferred editor

# Verify all required variables are set
cat .env | grep -v '^#' | grep -v '^$'
```

### 5. Test Import Statements (Local)
```bash
python -c "
from google.cloud import aiplatform
from google.cloud import vision
from google.cloud import speech_v1
from google.cloud import translate_v2
from google.cloud.sql.connector import Connector
import pg8000
print('✓ All imports successful!')
"
```

### 6. Validate Code Syntax
```bash
python -m py_compile check_text.py
python -m py_compile check_media.py
echo "✓ No syntax errors"
```

### 7. Check Required APIs are Enabled
```bash
gcloud services list --enabled | grep -E "(run|sql|aiplatform|vision|speech|translate)"
```

### 8. Verify Cloud SQL Instance
```bash
gcloud sql instances list
gcloud sql instances describe truthscope-db
```

### 9. Test Database Connection (Local)
```bash
# Replace with your actual connection name
export CLOUD_SQL_CONNECTION_NAME="your-project:us-central1:truthscope-db"
export DB_USER="postgres"
export DB_PASSWORD="your-password"
export DB_NAME="news_analysis_db"

python -c "
from google.cloud.sql.connector import Connector
import pg8000

connector = Connector()
conn = connector.connect(
    '$CLOUD_SQL_CONNECTION_NAME',
    'pg8000',
    user='$DB_USER',
    password='$DB_PASSWORD',
    db='$DB_NAME'
)
print('✓ Database connection successful!')
conn.close()
connector.close()
"
```

### 10. Build Docker Image (Optional - Local Test)
```bash
docker build -t truthscope-backend .
docker run -p 8080:8080 --env-file .env truthscope-backend
```

### 11. Dry-Run Deployment
```bash
# Check what would be deployed without actually deploying
gcloud run deploy truthscope-text-analysis \
    --source . \
    --region us-central1 \
    --dry-run
```

### 12. Final Checklist

- [ ] Python 3.11+ installed
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] gcloud CLI configured and authenticated
- [ ] GCP project created and set
- [ ] All required APIs enabled
- [ ] Cloud SQL instance created and running
- [ ] Database schema loaded (db.sql)
- [ ] Custom Search Engine configured
- [ ] All environment variables set in .env
- [ ] All imports work (test with python -c)
- [ ] No syntax errors in code
- [ ] Database connection test passed
- [ ] Docker image builds successfully (optional)
- [ ] Team notified about deployment

---

## 🚨 Common Issues

### "Module not found" errors
**Solution:** Run `pip install -r requirements.txt`

### "gcloud command not found"
**Solution:** Install gcloud CLI from https://cloud.google.com/sdk/docs/install

### "Permission denied" errors
**Solution:** Run `gcloud auth login` and ensure you have required IAM roles

### "Cloud SQL connection refused"
**Solution:** 
1. Check instance is running: `gcloud sql instances list`
2. Verify connection name format: `project:region:instance`
3. Ensure Cloud SQL API is enabled

### "API not enabled" errors
**Solution:** Run the enable commands from SETUP_GUIDE.md

### "Billing account required"
**Solution:** Link a billing account: `gcloud billing projects link PROJECT_ID --billing-account=ACCOUNT_ID`

---

## 📊 Deployment Decision

After completing all checks:

✅ **All Green?** → Proceed with deployment: `./deploy.sh`

⚠️ **Any Issues?** → Review error messages, consult SETUP_GUIDE.md, fix issues, then retry

---

## 🆘 Emergency Rollback

If deployment fails or causes issues:

```bash
# List previous revisions
gcloud run revisions list --service=truthscope-text-analysis --region=us-central1

# Rollback to previous version
gcloud run services update-traffic truthscope-text-analysis \
    --region=us-central1 \
    --to-revisions=PREVIOUS_REVISION_NAME=100
```

---

**Good luck with your deployment! 🚀**
