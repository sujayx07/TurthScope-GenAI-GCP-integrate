# TruthScope Extension Testing Guide

## Prerequisites
✅ Backend is running on http://127.0.0.1:8080
✅ Google Cloud credentials are set up (you've already done this)
✅ Extension files are updated with local backend URLs

## Step-by-Step Testing Instructions

### 1. Load the Extension in Chrome

1. **Open Chrome** and go to: `chrome://extensions/`
2. **Enable "Developer mode"** (toggle in top-right corner)
3. Click **"Load unpacked"**
4. Navigate to: `C:\Users\biswa\OneDrive\Desktop\TruthScope-Final\extension\frontend`
5. Select the folder and click "Select Folder"
6. You should see **TruthScope** extension loaded

### 2. Sign In to the Extension

1. **Click the TruthScope extension icon** in your Chrome toolbar
   - If you don't see it, click the puzzle icon and pin TruthScope

2. **Click "View Details"** button in the popup
   - This will open the Side Panel

3. **In the Side Panel**, you should see a **"Sign in"** button (top-left)
   - Click the "Sign in" button
   - A Google OAuth popup will appear
   - Sign in with your Google account
   - Grant the requested permissions

4. **After signing in**, you should see:
   - Your profile picture in the top-left
   - The "Sign in" button disappears

**IMPORTANT**: The sign-in button is **ONLY in the Side Panel**, not in the main popup!

### 3. Test the Extension

#### Test 1: Analyze a News Article

1. **Open a news website** in a new tab, for example:
   - https://www.bbc.com/news
   - https://www.cnn.com
   - https://www.reuters.com

2. **Click on any news article** to open it

3. **The extension should automatically analyze** the article
   - You'll see a notification (optional)
   - The analysis happens in the background

4. **Click the TruthScope extension icon**
   - You should see the analysis result in the popup:
     - "Verified" (green) for credible content
     - "Misleading" (red) for potentially fake content
     - Sentiment and bias tags

5. **Click "View Details"** to open the Side Panel
   - See full analysis results
   - View fact-checks
   - See reasoning and educational insights

#### Test 2: Check Backend Communication

1. **Open Chrome DevTools**: Press `F12`
2. Go to the **Console** tab
3. Look for messages like:
   - "Background: Token string obtained"
   - "User profile fetched"
   - "Analysis request sent"

4. Go to the **Network** tab
5. Filter by "analyze"
6. You should see requests to `http://127.0.0.1:8080/analyze`
7. Check if they return **200 OK** status

### 4. Troubleshooting

#### Problem: "Sign in" button not appearing

**Solution**: 
- The sign-in button is **ONLY in the Side Panel**, not the popup
- Click "View Details" in the popup first
- Then you'll see the "Sign in" button

#### Problem: Extension can't connect to backend

**Check**:
1. Backend is running: `python check_text.py`
2. Backend is accessible: Open http://127.0.0.1:8080 in your browser
3. Console shows: `{"message": "TruthScope Analysis Backend (GCP-Native)", ...}`

#### Problem: Authentication fails

**Check**:
1. OAuth client ID in `manifest.json` matches your GCP project
2. Current client ID: `705488681605-p8ck7c4uubiqfo81p2eosv92v0d336ff.apps.googleusercontent.com`
3. Make sure this client ID has the extension's Chrome ID in the authorized origins

**To get your extension's Chrome ID**:
1. Go to `chrome://extensions/`
2. Find TruthScope
3. Copy the ID (looks like: `abcdefghijklmnopqrstuvwxyz123456`)

4. **Add it to Google Cloud Console**:
   - Go to: https://console.cloud.google.com/apis/credentials
   - Click on your OAuth 2.0 Client ID
   - Add to "Authorized redirect URIs":
     ```
     https://<YOUR_EXTENSION_ID>.chromiumapp.org/
     ```
   - Replace `<YOUR_EXTENSION_ID>` with your actual extension ID

#### Problem: No analysis happening

**Check**:
1. You're signed in (profile picture visible in side panel)
2. Backend console shows incoming requests
3. No errors in browser console (F12)
4. The website you're testing on has readable content

### 5. Testing Checklist

- [ ] Backend running on port 8080
- [ ] Extension loaded in Chrome
- [ ] Opened Side Panel
- [ ] Signed in successfully (profile picture visible)
- [ ] Opened a news article
- [ ] Extension icon shows result (green/red indicator)
- [ ] Popup shows analysis summary
- [ ] Side Panel shows full details
- [ ] Fact-checks visible
- [ ] Sentiment and bias tags showing
- [ ] No errors in console

### 6. Expected Behavior

**When everything works correctly:**

1. **Popup** (click extension icon):
   - Shows quick analysis status
   - Green "Verified" or Red "Misleading" indicator
   - Sentiment tag (Positive/Negative/Neutral)
   - Bias indicators
   - "View Details" button

2. **Side Panel** (click "View Details"):
   - User profile (top-left)
   - Full analysis results
   - Confidence score
   - Reasoning points
   - Educational insights
   - Fact-check results
   - Localized summary (if non-English)

3. **Backend Console** (check_text.py terminal):
   ```
   2025-11-02 XX:XX:XX,XXX - INFO - Received analysis request for URL: ...
   2025-11-02 XX:XX:XX,XXX - INFO - User authenticated successfully...
   2025-11-02 XX:XX:XX,XXX - INFO - --- Analyzing Article ---
   2025-11-02 XX:XX:XX,XXX - INFO - Analysis successful for URL: ...
   ```

### 7. Quick Test Commands

**Check backend status:**
```cmd
curl http://127.0.0.1:8080/
```

**Test analysis endpoint** (requires auth token):
```cmd
python test_api.py
```

### 8. Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| Backend not responding | Run: `python check_text.py` |
| Sign-in button missing | Open Side Panel (not popup) |
| OAuth error | Update authorized redirect URIs in GCP |
| No analysis results | Check if signed in & backend logs |
| CORS errors | Already handled in Flask CORS config |

## Next Steps After Successful Testing

1. ✅ Test with multiple news websites
2. ✅ Test with different article types
3. ✅ Verify sentiment analysis works
4. ✅ Check bias detection
5. ✅ Test fact-checking integration
6. ✅ Verify localization (try non-English articles)

## Need Help?

- Check browser console (F12 → Console)
- Check backend console (terminal running check_text.py)
- Check Network tab (F12 → Network) for API calls
- Look for error messages in any of the above

---

**Your current setup:**
- Backend: `http://127.0.0.1:8080`
- Client ID: `705488681605-p8ck7c4uubiqfo81p2eosv92v0d336ff.apps.googleusercontent.com`
- GCP Project: `truthscope-prod-2025`
