# Debug Guide: "Signing in..." Stuck Issue

## How to Debug the OAuth Sign-In Issue

### Step 1: Check Browser Console for Errors

1. **Open the TruthScope side panel** (where you see "Signing in...")
2. **Right-click anywhere in the side panel** → Select **"Inspect"**
3. In DevTools, go to the **Console** tab
4. Look for any error messages (they'll be in red)
5. **Copy and paste any errors you see**

### Step 2: Check Background Service Worker Console

1. Go to **`chrome://extensions/`**
2. Find **TruthScope** extension
3. Click **"service worker"** (blue link under "Inspect views")
4. A new DevTools window will open for the background script
5. Check the **Console** tab for errors
6. Look for messages starting with "Background:"

### Step 3: Most Common Issues & Fixes

#### Issue 1: OAuth Redirect URI Not Configured

**Symptoms**: Sign-in popup appears then immediately closes, or shows an error

**Fix**:
1. Get your extension's Chrome ID:
   - Go to `chrome://extensions/`
   - Find TruthScope
   - Copy the **ID** (looks like: `abcdefghijklmnopqrstuvwxyz123456`)

2. Add redirect URI to Google Cloud Console:
   - Go to: https://console.cloud.google.com/apis/credentials?project=truthscope-prod-2025
   - Click on your OAuth 2.0 Client ID: `705488681605-p8ck7c4uubiqfo81p2eosv92v0d336ff`
   - Under **"Authorized redirect URIs"**, click **"+ ADD URI"**
   - Add these two URIs (replace `YOUR_EXTENSION_ID` with your actual ID):
     ```
     https://YOUR_EXTENSION_ID.chromiumapp.org/
     https://YOUR_EXTENSION_ID.chromiumapp.org/callback
     ```
   - Click **"SAVE"**

#### Issue 2: Chrome Identity API Not Working

**Symptoms**: No popup appears, button just says "Signing in..." forever

**Fix**:
1. Check if you're using a Chrome profile that supports extensions
2. Try reloading the extension:
   - Go to `chrome://extensions/`
   - Click the refresh icon on TruthScope
3. Try removing and re-adding the extension

#### Issue 3: Network or CORS Issues

**Symptoms**: Console shows network errors or CORS errors

**Fix**:
- Make sure you're testing on `https://` websites (not `http://`)
- Check if the Google OAuth popup is being blocked by your browser
- Look for a popup blocker icon in Chrome's address bar

### Step 4: Manual Testing

Let me create a simple test to verify OAuth is working:

**Test the OAuth flow manually:**

1. Open Chrome DevTools Console (F12)
2. Paste this code and press Enter:

```javascript
chrome.identity.getAuthToken({ interactive: true }, (token) => {
  if (chrome.runtime.lastError) {
    console.error("OAuth Error:", chrome.runtime.lastError);
  } else {
    console.log("OAuth Success! Token:", token);
  }
});
```

If this works, you'll see the token printed. If not, you'll see the error.

### Step 5: Check Extension Permissions

Make sure the extension has the necessary permissions:

1. Go to `chrome://extensions/`
2. Click **"Details"** on TruthScope
3. Scroll down to **"Permissions"**
4. Make sure these are enabled:
   - Identity
   - Storage
   - Active Tab

### Step 6: Reload and Retry

1. **Reload the extension**:
   - `chrome://extensions/` → Click refresh icon on TruthScope

2. **Close and reopen the side panel**

3. **Try signing in again**

### What to Report Back

Please check the above steps and report:

1. **Extension ID**: (from `chrome://extensions/`)
2. **Console errors**: (from both side panel and service worker)
3. **Test result**: (from Step 4 manual test)
4. **Does Google popup appear?**: Yes/No

---

## Quick Fix to Try First

**Most likely issue**: The OAuth redirect URI needs to be configured.

1. Get your extension ID from `chrome://extensions/`
2. Go to: https://console.cloud.google.com/apis/credentials?project=truthscope-prod-2025
3. Click on the OAuth client
4. Add redirect URI: `https://YOUR_EXTENSION_ID.chromiumapp.org/`
5. Save
6. Wait 1-2 minutes for changes to propagate
7. Reload your extension
8. Try signing in again
