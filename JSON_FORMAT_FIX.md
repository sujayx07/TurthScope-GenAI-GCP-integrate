# JSON Format Fix - Analysis Results Display

## Issue Description
The frontend was showing "Analysis format unknown" error because the backend was returning inconsistent JSON formats for error cases.

## Root Cause
- **Backend**: The `analyze_article()` function had an early validation that returned `{"error": "..."}` instead of the expected `{"textResult": {"error": "..."}}`
- **Frontend**: The code expected `data.textResult.label` and `data.textResult.score` to always be present, but didn't handle cases where `textResult` contained only an error

## Changes Made

### Backend Changes (`extension/backend/check_text.py`)

#### 1. Fixed Error Response Format (Line ~825)
**Before:**
```python
if not url or not article_text:
    return {"error": "URL and article text must be provided."}
```

**After:**
```python
if not url or not article_text:
    return {
        "textResult": {
            "error": "URL and article text must be provided."
        }
    }
```

#### 2. Updated Error Detection in Endpoint (Lines ~1007-1028)
**Before:**
```python
status_code = 500 if "error" in result else 200
if "error" in result:
    error_msg = result["error"]
    # ... error handling
```

**After:**
```python
has_error = False
if "textResult" in result and "error" in result.get("textResult", {}):
    has_error = True
    logging.error(f"Analysis returned error: {result['textResult'].get('error')}")

# Determine status code based on error type
if has_error:
    error_msg = result.get("textResult", {}).get("error", "")
    if "Analysis failed due to tool error" in error_msg:
        status_code = 502  # Bad Gateway
    elif "Model did not return valid JSON" in error_msg:
        status_code = 500  # Internal Server Error
    # ... etc
```

### Frontend Changes

#### 1. Sidepanel.js (`extension/frontend/sidepanel.js`)

**Enhanced Error Handling (Lines ~340-365):**
- Added detailed error display with `error` and `details` fields
- Shows `raw_response_preview` in a collapsible section for debugging
- Better messaging for incomplete data (missing `label` or `score`)

**Before:**
```javascript
if (data.textResult.error) {
    statusBadge.textContent = "Error";
    statusBadge.className = "status-badge unknown";
    confidenceDiv.textContent = `Error: ${data.textResult.error}`;
    // ...
} else if (data.textResult.label !== undefined) {
    // ... success case
} else {
    statusBadge.textContent = "Unknown";
    confidenceDiv.textContent = "Analysis format unknown.";
}
```

**After:**
```javascript
if (data.textResult.error) {
    // Enhanced error display
    statusBadge.textContent = "Error";
    statusBadge.className = "status-badge unknown";
    const errorDetails = data.textResult.details ? ` (${data.textResult.details})` : '';
    confidenceDiv.textContent = `Error: ${data.textResult.error}${errorDetails}`;
    
    // Show detailed error in AI Summary with raw response preview
    let errorHtml = `<div class="text-red-500 dark:text-red-400 p-4">
        <p class="font-semibold mb-2">Analysis Error:</p>
        <p>${data.textResult.error}</p>`;
    // ... includes details and raw_response_preview
    
} else if (data.textResult.label !== undefined && data.textResult.score !== undefined) {
    // ... success case
} else {
    // Better handling for incomplete data
    statusBadge.textContent = "Unknown";
    confidenceDiv.textContent = "Analysis incomplete: missing required data.";
    // Shows available data in debug section
}
```

#### 2. Popup.js (`extension/frontend/popup.js`)

**Enhanced Validation (Lines ~147-185):**
- Added check for both `label` AND `score` fields
- Better visual feedback for incomplete/error states
- Added proper icon and status indicators

**Before:**
```javascript
} else if (data.textResult.label !== undefined) {
    const isFake = data.textResult.label === "LABEL_1";
    const confidence = (data.textResult.score * 100).toFixed(1);
    // ...
} else {
    statusDiv.textContent = 'Analysis result format unknown.';
    statusIndicator.className = 'status-indicator unknown';
}
```

**After:**
```javascript
} else if (data.textResult.label !== undefined && data.textResult.score !== undefined) {
    const isFake = data.textResult.label === "LABEL_1";
    const confidence = (data.textResult.score * 100).toFixed(1);
    // ...
} else {
    // Missing required fields
    statusDiv.textContent = 'Analysis incomplete: missing required data.';
    statusIndicator.className = 'status-indicator unknown';
    statusIndicator.innerHTML = `
        <div class="flex items-center gap-1.5">
            <div class="icon">
                <svg>...</svg>
            </div>
            <span>Incomplete</span>
        </div>
    `;
}
```

## Expected JSON Format

### Success Response
```json
{
  "textResult": {
    "label": "LABEL_0",
    "score": 0.9234,
    "sentiment": {
      "label": "neutral",
      "score": 0.85
    },
    "bias": {
      "summary": "Minimal bias detected",
      "indicators": ["Neutral Language"]
    },
    "highlights": ["Notable quote"],
    "reasoning": [
      "Source is credible",
      "Claims verified by fact-checkers"
    ],
    "educational_insights": [
      "This source has a history of accuracy"
    ],
    "fact_check": [
      {
        "source": "BBC News",
        "title": "Fact Check Article",
        "url": "https://example.com",
        "claim": "Claim text",
        "rating": "True"
      }
    ],
    "localized_summary": {
      "reasoning": "Translated reasoning",
      "educational_insights": "Translated insights"
    }
  }
}
```

### Error Response
```json
{
  "textResult": {
    "error": "Model did not return valid JSON in the final response.",
    "details": "JSON parse error: Expecting property name",
    "raw_response_preview": "The model's actual response text..."
  }
}
```

## Testing Checklist

- [ ] Valid article analysis returns proper format with `label` and `score`
- [ ] Backend validation errors show user-friendly messages
- [ ] Model JSON parsing errors display raw preview for debugging
- [ ] Frontend displays detailed error messages in sidepanel
- [ ] Popup shows appropriate status indicators for all states
- [ ] Missing fields case (no label/score) shows "incomplete" message
- [ ] All error types return correct HTTP status codes (400, 500, 502)

## Benefits

1. **Consistent Format**: All responses follow the same `{"textResult": {...}}` structure
2. **Better Debugging**: Error responses include `details` and `raw_response_preview`
3. **User-Friendly**: Clear error messages instead of "format unknown"
4. **Developer-Friendly**: Frontend can reliably check `data.textResult.error` to detect errors
5. **Proper HTTP Codes**: Backend returns appropriate status codes (400, 500, 502)

## Notes

- Authentication errors (401) at the decorator level still use `{"error": "..."}` format (handled before analysis logic)
- All analysis-related responses now consistently use `{"textResult": {...}}` format
- Frontend gracefully degrades when optional fields are missing
- Debug information is available but collapsed by default in the UI
