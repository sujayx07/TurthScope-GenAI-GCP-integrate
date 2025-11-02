# TruthScope Codebase Description

This document provides a comprehensive overview of the TruthScope Chrome Extension codebase, detailing its architecture, features, and individual components.

## 1. Project Overview

TruthScope is a Chrome extension designed to combat misinformation by analyzing web content. It provides users with real-time analysis of articles and media (images, videos) to identify potential fake news, manipulation, and bias. The extension leverages a combination of AI/ML models, fact-checking APIs, and a custom credibility database.

The project is structured into two main parts:
-   **Frontend**: A Chrome extension responsible for user interaction, content extraction from web pages, and displaying analysis results.
-   **Backend**: A set of Python Flask servers that perform the heavy lifting of content analysis.

## 2. System Architecture

### 2.1. Frontend (Chrome Extension)

The frontend is the user-facing part of the extension. It consists of several components that work together to deliver the user experience.

-   **Manifest (`manifest.json`)**: Defines the extension's core properties, permissions, and components. It registers the background service worker, content scripts, popup, and side panel.
-   **Background Script (`background.js`)**: Acts as the central coordinator for the extension. It manages authentication, handles communication between different parts of the extension (content script, popup, side panel), and makes API calls to the backend for analysis.
-   **Content Script (`content.js`)**: Injected into web pages to extract article text and identify media elements. It also injects UI elements like analysis buttons on media and a warning header for misleading content.
-   **Popup (`popup.html`, `popup.js`)**: A small window that appears when the user clicks the extension icon. It provides a quick summary of the analysis for the current page.
-   **Side Panel (`sidepanel.html`, `sidepanel.js`)**: A persistent panel that displays detailed analysis results, including fact-checking information, AI-generated reasoning, and related news articles.

### 2.2. Backend (Python Flask Servers)

The backend consists of microservices built with Python and Flask, each responsible for a specific type of analysis.

-   **Text Analysis Service (`check_text.py`)**:
    -   Receives text content from the frontend.
    -   Uses the Google Gemini model with function calling capabilities to perform a sophisticated analysis.
    -   Leverages several tools:
        -   `check_database_for_url`: Checks a PostgreSQL database for a pre-existing verdict on the source's domain.
        -   `search_gdelt_context`: Searches the GDELT dataset for corroborating news articles.
        -   `fact_check_claims`: Uses the Google Fact Check Tools API to verify specific claims within the text.
    -   Returns a detailed JSON object with a credibility label (`LABEL_0` for real, `LABEL_1` for fake), a confidence score, highlighted misleading sentences, and the reasoning behind the verdict.

-   **Media Analysis Service (`check_media.py`)**:
    -   Analyzes images, videos, and audio.
    -   **Image Analysis**: Uses the Sightengine API to detect AI-generated or manipulated images.
    -   **Video/Audio Analysis**: Placeholder endpoints exist, intended for a paid tier. These would integrate with services to detect deepfakes or AI-generated audio.
    -   Manages user authentication and authorization, restricting certain features (like video/audio analysis) to users with a 'paid' subscription tier.

-   **Sentiment & Bias Service (`check_sentiment.py` - not provided but referenced)**:
    -   Analyzes text for emotional sentiment (positive, negative, neutral) and potential political or ideological bias.

## 3. Core Features

-   **Real-time Content Analysis**: Automatically analyzes article text upon page load.
-   **Media Manipulation Detection**: Allows users to trigger analysis of images and videos on a page to check for AI generation.
-   **User Authentication**: Integrates with Google Sign-In (OAuth 2.0) to identify users and manage subscription tiers.
-   **Credibility Score**: Provides a confidence score for the text analysis, indicating the likelihood of it being real or fake.
-   **Highlighting**: Automatically highlights specific sentences within the article that are identified as potentially misleading.
-   **Detailed Reporting**: The side panel offers a deep dive into the analysis, showing fact-check results, AI reasoning, and related news.
-   **UI Themes**: Supports light, dark, and system themes for user preference.

## 4. File-by-File Breakdown

### `frontend/manifest.json`
-   **`manifest_version`**: 3 (latest standard).
-   **`permissions`**: Requests permissions for `activeTab`, `storage` (for settings like theme), `notifications`, `sidePanel`, `scripting`, `tabs`, and `identity` (for Google OAuth).
-   **`background`**: Registers `background.js` as the service worker.
-   **`content_scripts`**: Injects `content.js` into all URLs (`<all_urls>`) at `document_idle`.
-   **`action`**: Defines `popup.html` as the default popup.
-   **`side_panel`**: Enables the side panel feature with `sidepanel.html` as its content.
-   **`host_permissions`**: Grants access to the backend servers and Google APIs.
-   **`oauth2`**: Configures the Google OAuth 2.0 client ID and scopes required for user authentication.

### `frontend/background.js`
-   **Central Hub**: Manages all communication and state.
-   **Authentication**: Contains all logic for `signIn`, `signOut`, and checking the initial auth state using `chrome.identity`. It securely stores the user's auth token.
-   **State Management**: Uses a `processingState` object to store analysis results per tab ID.
-   **API Broker**: Receives requests from `content.js` and forwards them to the appropriate backend service (`TEXT_ANALYSIS_URL`, `IMAGE_ANALYSIS_URL`, etc.), adding the necessary `Authorization` header with the user's token.
-   **Error Handling**: Implements logic to handle API errors, including 401/403 status codes which trigger a user sign-out.

### `frontend/content.js`
-   **Content Extraction**: Scrapes the main text content from the page using a list of common article-related selectors (`article`, `.post-content`, etc.).
-   **Media Discovery**: Finds all `<img>`, `<video>`, and YouTube `<iframe>` elements on the page.
-   **UI Injection**:
    -   Dynamically adds an "Analyze" button to media elements, allowing users to trigger on-demand analysis.
    -   Injects a prominent warning header at the top of the page if the text analysis returns a "fake" label.
    -   Applies yellow highlights to specific text snippets returned by the backend.
-   **Communication**: Sends extracted text and media URLs to `background.js` for processing and listens for results to display.

### `frontend/popup.js`
-   **Quick View**: Provides a summarized status of the current page's analysis.
-   **UI Logic**:
    -   Displays a status indicator (e.g., "Verified", "Misleading", "Unknown").
    -   Shows sentiment and bias tags if available.
    -   Contains a button that opens the side panel for more details.
-   **Data Fetching**: On load, it requests the analysis data for the active tab from `background.js`.
-   **Theme Handling**: Includes logic to apply and toggle between light/dark/system themes, syncing the preference to `chrome.storage`.

### `frontend/sidepanel.js`
-   **Detailed View**: The main interface for displaying comprehensive analysis results.
-   **Authentication UI**: Manages the sign-in/sign-out UI. It prompts users to sign in and displays user profile information when authenticated.
-   **Data Display**:
    -   Shows the overall credibility status and confidence score.
    -   Renders a detailed AI-generated reasoning for the verdict.
    -   Lists results from fact-checking APIs and related news from GDELT.
-   **Data Fetching**: Like the popup, it requests the full analysis data for the active tab from `background.js` upon opening. It also listens for real-time updates.

### `backend/check_text.py`
-   **Main Logic**: The core of the fake news detection.
-   **Gemini Agent**: Uses the `gemini-1.5-flash-latest` model configured with a detailed system instruction and a set of Python functions (tools) it can call.
-   **Function Calling**:
    -   `check_database_for_url`: Checks a PostgreSQL `url_verdicts` table for the domain's reputation.
    -   `search_gdelt_context`: Queries GDELT for related news to check for corroboration.
    -   `fact_check_claims`: Queries the Google Fact Check API for specific claims.
-   **Authentication**: Protected by a `@require_auth` decorator which verifies the Google access token passed in the `Authorization` header.
-   **Database Interaction**: Creates and manages a `psycopg2` connection pool for efficient database access. It stores final analysis results in an `analysis_results` table.

### `backend/check_media.py`
-   **Media Analysis**: Handles analysis of images, videos, and audio.
-   **API Integration**:
    -   `call_sightengine_api`: Checks an image URL against Sightengine's `genai` model to detect AI generation.
    -   `call_sightengine_video_api`: A placeholder for synchronous video analysis.
-   **Tiered Access Control**: Implements a `@require_auth_and_paid_tier` decorator. This decorator first verifies the user's Google token and then checks the `users` table in the database to ensure the user has a `paid` tier before allowing access to the function. This is used to restrict video and audio analysis.
-   **User Management**: Contains the `get_or_create_user` function, which looks up a user by their Google ID and creates a new entry with a `free` tier if they don't exist.

## 5. Setup and Installation

1.  **Frontend**: No build step is required. The extension can be loaded directly in Chrome's developer mode.
2.  **Backend**:
    -   Requires Python 3.8+.
    -   A PostgreSQL database must be set up, and the schema from `db.sql` must be applied.
    -   A `.env` file must be created in the `extension` directory containing all necessary API keys (Google, Sightengine, etc.) and database credentials.
    -   Python dependencies must be installed from `requirements.txt` into a virtual environment.
    -   Each Flask server (`check_text.py`, `check_media.py`) is run as a separate process.
