# TruthScope Backend Migration to Google Cloud Platform

## Overview
This document describes the major refactoring of TruthScope backend services from third-party APIs to a fully Google Cloud Platform (GCP) native architecture.

## Migration Summary

### Services Migrated
1. **check_text.py** - Core text and news article analysis
2. **check_media.py** - Multi-modal media analysis (images, video, audio)
3. **check_sentiment.py** - DEPRECATED (functionality merged into check_text.py)

---

## Architecture Changes

### 1. Database Migration
**Before:** Direct PostgreSQL connections using `psycopg2.pool`
**After:** Cloud SQL for PostgreSQL using Google Cloud SQL Python Connector

#### Changes Made:
- Replaced `psycopg2.pool.SimpleConnectionPool` with `google.cloud.sql.connector.Connector`
- Updated connection methods to use Cloud SQL connection strings
- Format: `project:region:instance` (e.g., `my-project:us-central1:truthscope-db`)

#### Required Environment Variables:
```
CLOUD_SQL_CONNECTION_NAME=project:region:instance
DB_NAME=news_analysis_db
DB_USER=your_db_user
DB_PASSWORD=your_db_password
```

---

### 2. AI/ML Services Migration

#### check_text.py Changes

##### Gemini Integration
**Before:** `google.genai.Client` (beta SDK)
**After:** Vertex AI SDK (`google.cloud.aiplatform`)

**Key Changes:**
- Replaced `genai.Client` with `aiplatform.GenerativeModel`
- Model: `gemini-1.5-flash-002` or `gemini-1.5-pro-002`
- Uses Vertex AI's stable production API

##### Search API Replacement
**Before:** GDELT Context API
**After:** Google Custom Search API

**Implementation:**
- Replaced `search_gdelt_context()` with `search_google_for_context()`
- Prioritizes Indian news sources (geolocation: `gl=in`)
- Supports multilingual results (`lang_en|lang_hi`)

**Required Environment Variables:**
```
GOOGLE_CUSTOM_SEARCH_API_KEY=your_api_key
GOOGLE_CUSTOM_SEARCH_ENGINE_ID=your_search_engine_id
```

##### Enhanced System Instruction
**New Features Added:**
1. **Sentiment Analysis** - Consolidated from check_sentiment.py
   - Returns: `{"label": "positive|negative|neutral", "score": float}`
   
2. **Bias Detection**
   - Returns: `{"summary": "string", "indicators": ["string"]}`
   
3. **Educational Insights**
   - User-friendly explanations of why content is misleading
   - Examples of logical fallacies, manipulation tactics
   
4. **Localized Summaries**
   - Automatic language detection using Google Cloud Translation API
   - Translates reasoning and insights to source article language

**New Response Structure:**
```json
{
  "textResult": {
    "label": "LABEL_0 or LABEL_1",
    "score": 0.9127,
    "sentiment": {"label": "negative", "score": 0.85},
    "bias": {
      "summary": "Strong political leaning detected",
      "indicators": ["Sensational Language", "Cherry-picking"]
    },
    "highlights": ["string"],
    "reasoning": ["string"],
    "educational_insights": ["string"],
    "fact_check": [{...}],
    "localized_summary": {
      "reasoning": "translated text",
      "educational_insights": "translated text"
    }
  }
}
```

---

#### check_media.py Changes

##### Image Analysis
**Before:** Sightengine API (third-party)
**After:** Google Cloud Vision API + Gemini Multi-modal

**Implementation:**
- `analyze_image_with_vision_api()` - SafeSearch + Web Detection
- `analyze_image_with_gemini()` - AI generation detection + context analysis

**Features:**
- Deepfake detection
- Manipulation indicators
- Visual similarity search
- Context analysis for misinformation potential

##### Video Analysis
**Before:** Placeholder/Not Implemented
**After:** Gemini 1.5 Pro Multi-modal

**Implementation:**
- `analyze_video_logic()` function
- Analyzes for:
  - Deepfake indicators
  - Audio-visual consistency
  - Out-of-context manipulation
  - Overall credibility assessment

**Note:** Full implementation requires:
- Video download and frame extraction
- Audio extraction
- Google Cloud Speech-to-Text integration

##### Audio Analysis
**Before:** Placeholder/Not Implemented
**After:** Gemini + Speech-to-Text API

**Implementation:**
- `analyze_audio_logic()` function
- Detects:
  - Scam language
  - Deceptive tactics (urgency, fear, false promises)
  - Phishing indicators
  - Fraud attempts

---

### 3. Translation Services

**New Integration:** Google Cloud Translation API

**Functions:**
- `detect_language(text)` - Auto-detect source language
- `translate_text(text, target_lang, source_lang)` - Translate content

**Use Cases:**
- Analyzing non-English articles
- Providing localized explanations to users
- Multi-language support for global deployment

---

## Deployment Configuration

### Required GCP Services
1. ✅ Cloud Run (application hosting)
2. ✅ Cloud SQL for PostgreSQL (database)
3. ✅ Vertex AI (Gemini models)
4. ✅ Cloud Vision API
5. ✅ Cloud Speech-to-Text API
6. ✅ Cloud Translation API
7. ✅ Custom Search API

### Required Environment Variables

#### Core Configuration
```bash
# GCP Project
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1

# Authentication
GOOGLE_CLIENT_ID=your-oauth-client-id.apps.googleusercontent.com
GOOGLE_API_KEY=your-api-key

# Cloud SQL
CLOUD_SQL_CONNECTION_NAME=project:region:instance
DB_NAME=news_analysis_db
DB_USER=postgres
DB_PASSWORD=your-secure-password

# APIs
GOOGLE_FACT_CHECK_API_KEY=your-fact-check-api-key
GOOGLE_CUSTOM_SEARCH_API_KEY=your-custom-search-api-key
GOOGLE_CUSTOM_SEARCH_ENGINE_ID=your-search-engine-id
```

### Cloud Run Deployment

#### Dockerfile Example
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8080

# Run with gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 check_text:app
```

#### Deploy Commands
```bash
# Set project
gcloud config set project YOUR_PROJECT_ID

# Deploy check_text service
gcloud run deploy truthscope-text-analysis \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_LOCATION=us-central1 \
  --add-cloudsql-instances YOUR_CLOUD_SQL_CONNECTION_NAME

# Deploy check_media service
gcloud run deploy truthscope-media-analysis \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_LOCATION=us-central1 \
  --add-cloudsql-instances YOUR_CLOUD_SQL_CONNECTION_NAME
```

---

## Breaking Changes

### API Response Changes

1. **Sentiment/Bias Fields Added**
   - Old: Not present
   - New: `sentiment` and `bias` objects in response

2. **Educational Insights**
   - Old: Not present
   - New: `educational_insights` array with explanations

3. **Localized Summary**
   - Old: Not present
   - New: `localized_summary` object with translations

4. **Fact Check Format**
   - Old: Basic structure
   - New: Enhanced with `rating` field and Google Search results

### Removed Dependencies
- ❌ `gdeltdoc` - Replaced by Google Custom Search
- ❌ `nltk` - Sentiment analysis moved to Gemini
- ❌ Third-party credentials (Sightengine, Zenrows, OCR.space)

---

## Testing Checklist

### check_text.py
- [ ] Text analysis with English article
- [ ] Text analysis with non-English article (verify translation)
- [ ] Sentiment analysis accuracy
- [ ] Bias detection
- [ ] Educational insights generation
- [ ] Fact-checking integration
- [ ] Google Search context retrieval
- [ ] Database connection (Cloud SQL)
- [ ] User authentication flow

### check_media.py
- [ ] Image analysis (Vision API + Gemini)
- [ ] AI-generated image detection
- [ ] Deepfake detection
- [ ] Video analysis (basic implementation)
- [ ] Audio analysis (basic implementation)
- [ ] Paid tier access control
- [ ] Database connection (Cloud SQL)

---

## Performance Considerations

1. **Latency:**
   - Vision API: ~1-2s per image
   - Gemini calls: ~2-5s per request
   - Translation: <1s per request
   - Total expected: 5-10s per full analysis

2. **Cost Optimization:**
   - Use Gemini Flash for faster/cheaper text analysis
   - Use Gemini Pro for complex multi-modal tasks
   - Cache translation results when possible
   - Implement rate limiting per user tier

3. **Scaling:**
   - Cloud Run auto-scales based on traffic
   - Cloud SQL connection pooling via Connector
   - Consider Cloud Tasks for long-running video/audio analysis

---

## Monitoring & Logging

### Key Metrics to Track
1. API call success rates (Vision, Gemini, Translation)
2. Average response times per endpoint
3. Cloud SQL connection pool utilization
4. Error rates by service
5. User tier distribution

### Logging Strategy
- All API calls logged with timing
- Errors include full stack traces
- User IDs tracked for debugging
- Cloud Logging integration for centralized logs

---

## Security Enhancements

1. **Authentication:**
   - Google OAuth token verification maintained
   - User tier validation in place

2. **API Keys:**
   - All credentials in environment variables
   - No hardcoded secrets
   - Secret Manager integration recommended

3. **Database:**
   - Cloud SQL with IAM authentication
   - Connection encryption enforced
   - Regular backups automated

---

## Rollback Plan

If issues arise, revert by:
1. Redeploy previous Docker image
2. Switch DNS/load balancer to old endpoints
3. Restore database from backup if needed
4. Update environment variables to old configuration

Keep previous deployment available for 30 days.

---

## Future Enhancements

1. **Video/Audio:** Complete implementation with actual Speech-to-Text integration
2. **Caching:** Implement Redis for frequently analyzed content
3. **Batch Processing:** Cloud Tasks for async analysis
4. **ML Pipeline:** Custom model training with Vertex AI
5. **Multi-region:** Deploy to additional regions for lower latency

---

## Support & Troubleshooting

### Common Issues

**Issue:** "Cloud SQL Connector not available"
**Solution:** Verify `CLOUD_SQL_CONNECTION_NAME` format and IAM permissions

**Issue:** "Gemini model not found"
**Solution:** Ensure Vertex AI API is enabled and model name is correct

**Issue:** "Translation API quota exceeded"
**Solution:** Increase quota in GCP Console or implement caching

**Issue:** "Vision API authentication failed"
**Solution:** Check service account has `roles/cloudvision.user` role

---

## Contact

For questions or issues with the migration:
- Technical Lead: [Your Contact]
- GCP Support: https://cloud.google.com/support
- Documentation: This file + inline code comments

---

**Migration Completed:** December 2024
**Last Updated:** December 2024
**Version:** 2.0.0 (GCP-Native)
