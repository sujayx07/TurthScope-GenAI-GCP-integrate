import os
import json
import requests
import logging
import traceback
from urllib.parse import urlparse, quote
from dotenv import load_dotenv # For .env file support
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union # For improved type hinting
from flask import Flask, request, jsonify, g # Added g for request context
from flask_cors import CORS # Added for CORS support
from functools import wraps # Added for decorators

# --- Google Cloud Platform Imports ---
from google.cloud import aiplatform
from google.cloud.aiplatform import gapic as aip_gapic
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel, Content, Part, GenerationConfig
    VERTEXAI_AVAILABLE = True
    logging.info("vertexai module imported successfully")
except ImportError as e:
    logging.error(f"Failed to import vertexai: {e}")
    GenerativeModel = None
    GenerationConfig = None
    VERTEXAI_AVAILABLE = False
try:
    from google.cloud import translate_v2 as translate
except ImportError:
    # Fallback if translate is not installed
    translate = None
from google.cloud.sql.connector import Connector
import pg8000

# --- Google Auth ---
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# --- Load Environment Variables ---
load_dotenv() # Load variables from .env file if it exists

# --- Configuration & Constants ---
current_datetime = datetime.now()
# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API Keys & Credentials (Loaded from environment)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_FACT_CHECK_API_KEY = os.getenv("GOOGLE_FACT_CHECK_API_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CUSTOM_SEARCH_API_KEY = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY", GOOGLE_API_KEY)
GOOGLE_CUSTOM_SEARCH_ENGINE_ID = os.getenv("GOOGLE_CUSTOM_SEARCH_ENGINE_ID")

# GCP Configuration
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")

# Cloud SQL Configuration (Loaded from environment)
CLOUD_SQL_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")  # Format: project:region:instance
DB_NAME = os.getenv("DB_NAME", "news_analysis_db")
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# Database Constants
URL_VERDICTS_TABLE = "url_verdicts"
ANALYSIS_RESULTS_TABLE = "analysis_results"
USERS_TABLE = "users"
DEFAULT_USER_TIER = "free"
VERDICT_REAL = "real"
VERDICT_FAKE = "fake"
VERDICT_NOT_FOUND = "not_found"

# API Constants
FACT_CHECK_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
API_TIMEOUT_SECONDS = 15
FACT_CHECK_CLAIM_LIMIT = 3 # Max claims to check per article
FACT_CHECK_QUERY_SIZE_LIMIT = 500 # Max characters per claim query
GOOGLE_SEARCH_RESULT_LIMIT = 10

# Vertex AI / Gemini Constants
GEMINI_MODEL_NAME = "gemini-2.5-flash" # Or "gemini-2.5-flash"
GEMINI_TEMPERATURE = 0.2

# --- Custom Exceptions ---
class ConfigurationError(Exception):
    """Custom exception for missing configuration."""
    pass

class DatabaseError(Exception):
    """Custom exception for database related errors."""
    pass

class ApiError(Exception):
    """Custom exception for external API errors."""
    pass

class AuthenticationError(Exception): # <-- NEW
    """Custom exception for authentication/token verification errors."""
    pass

# --- Cloud SQL Database Connection ---
connector = None

def initialize_cloud_sql_connector():
    """Initializes the Cloud SQL Python Connector."""
    global connector
    if connector is None:
        logging.info("Initializing Cloud SQL Connector...")
        try:
            connector = Connector()
            logging.info("Cloud SQL Connector initialized successfully.")
        except Exception as e:
            logging.error(f"Error initializing Cloud SQL Connector: {e}")
            connector = None
            raise DatabaseError(f"Failed to initialize Cloud SQL Connector: {e}")

def get_db_connection():
    """Gets a connection using the Cloud SQL Python Connector."""
    if connector is None:
        initialize_cloud_sql_connector()
        if connector is None:
            raise DatabaseError("Cloud SQL Connector is not available.")
    
    try:
        conn = connector.connect(
            CLOUD_SQL_CONNECTION_NAME,
            "pg8000",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME
        )
        logging.debug("Successfully got Cloud SQL connection.")
        return conn
    except Exception as e:
        logging.error(f"Error getting Cloud SQL connection: {e}")
        raise DatabaseError(f"Failed to get Cloud SQL connection: {e}")

def release_db_connection(conn):
    """Closes a Cloud SQL connection."""
    if conn:
        try:
            conn.close()
            logging.debug("Successfully closed Cloud SQL connection.")
        except Exception as e:
            logging.error(f"Error closing Cloud SQL connection: {e}")

def close_cloud_sql_connector():
    """Closes the Cloud SQL Connector."""
    global connector
    if connector:
        logging.info("Closing Cloud SQL Connector.")
        try:
            connector.close()
            logging.info("Cloud SQL Connector closed successfully.")
        except Exception as e:
            logging.error(f"Error closing Cloud SQL Connector: {e}")
        finally:
            connector = None

# --- Configuration Check ---
def check_configuration():
    """Checks if all necessary environment variables are set."""
    logging.info("Checking configuration...")
    required_vars = {
        "GOOGLE_API_KEY": GOOGLE_API_KEY,
        "GOOGLE_FACT_CHECK_API_KEY": GOOGLE_FACT_CHECK_API_KEY,
        "GCP_PROJECT_ID": GCP_PROJECT_ID,
        "CLOUD_SQL_CONNECTION_NAME": CLOUD_SQL_CONNECTION_NAME,
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD,
        "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
    }
    missing_vars = [name for name, value in required_vars.items() if not value or value.startswith("YOUR_")]
    if missing_vars:
        raise ConfigurationError(f"Missing required configuration variables: {', '.join(missing_vars)}")
    
    # Check optional variables
    if not GOOGLE_CUSTOM_SEARCH_ENGINE_ID:
        logging.warning("GOOGLE_CUSTOM_SEARCH_ENGINE_ID not set. Google Search functionality may be limited.")
    
    logging.info("Configuration check passed.")
    # Initialize Cloud SQL connector after config check passes
    initialize_cloud_sql_connector()
    
    # Initialize Vertex AI
    aiplatform.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)


# --- Helper Functions ---

def extract_domain_from_url(url: str) -> Optional[str]:
    """Extracts the domain name from a URL, removing 'www.'."""
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain and domain.startswith('www.'):
            domain = domain[4:]
        return domain.lower() if domain else None
    except Exception as e:
        logging.warning(f"Error parsing URL '{url}': {e}")
        return None

# --- NEW: Google Token Verification --- (Using UserInfo endpoint)
def verify_google_access_token(access_token: str) -> Dict[str, Any]:
    """Verifies a Google access token by calling the userinfo endpoint.

    Args:
        access_token: The access token received from the client.

    Returns:
        A dictionary containing user info (e.g., 'sub', 'email') if valid.

    Raises:
        AuthenticationError: If the token is invalid, expired, or the request fails.
    """
    logging.debug("Verifying Google access token...")
    userinfo_url = 'https://www.googleapis.com/oauth2/v1/userinfo?alt=json'
    try:
        response = requests.get(
            userinfo_url,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=API_TIMEOUT_SECONDS
        )
        response.raise_for_status() # Raises HTTPError for 4xx/5xx
        user_info = response.json()
        if not user_info or 'id' not in user_info: # 'id' is the 'sub' field in v1
            raise AuthenticationError("Invalid user info received from Google.")
        # Rename 'id' to 'sub' for consistency if needed, or just use 'id'
        user_info['sub'] = user_info.get('id')
        logging.info(f"Access token verified successfully for user sub: {user_info.get('sub')}")
        return user_info
    except requests.exceptions.Timeout:
        logging.error("Timeout calling Google UserInfo endpoint.")
        raise AuthenticationError("Timeout during token verification.")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        logging.warning(f"Google UserInfo request failed with status {status_code}. Token likely invalid or expired.")
        raise AuthenticationError(f"Token verification failed (HTTP {status_code}).")
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error calling Google UserInfo endpoint: {e}")
        raise AuthenticationError("Network error during token verification.")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode Google UserInfo response: {e}")
        raise AuthenticationError("Invalid response from token verification endpoint.")
    except Exception as e:
        logging.error(f"Unexpected error during token verification: {e}", exc_info=True)
        raise AuthenticationError(f"Unexpected error during token verification: {e}")

# --- Modified: get_or_create_user ---
def get_or_create_user(google_id: str, email: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieves user details (id, tier) from the database based on Google ID.
    If the user doesn't exist, creates a new user with the default tier and provided email.

    Args:
        google_id: The user's unique Google ID ('sub').
        email: The user's email address (optional).

    Returns:
        A dictionary containing the user's internal ID and tier.

    Raises:
        DatabaseError: If database operations fail.
        ValueError: If google_id is empty.
        AuthenticationError: If google_id is invalid (reusing for simplicity).
    """
    logging.debug(f"Getting or creating user for google_id: {google_id}, email: {email}")
    if not google_id:
        logging.error("Attempted to get/create user with empty google_id.")
        raise AuthenticationError("Google User ID cannot be empty.") # Use AuthError
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, tier FROM {USERS_TABLE} WHERE google_id = %s", (google_id,))
        user_record = cursor.fetchone()

        if user_record:
            user_id, tier = user_record
            logging.info(f"Found existing user (ID: {user_id}, Tier: {tier}) for google_id: {google_id}")
            return {"id": user_id, "tier": tier}
        else:
            logging.info(f"Creating new user for google_id: {google_id} with email: {email}")
            cursor.execute(
                f"""
                INSERT INTO {USERS_TABLE} (google_id, email, tier, created_at)
                VALUES (%s, %s, %s, NOW())
                RETURNING id, tier;
                """,
                (google_id, email, DEFAULT_USER_TIER)
            )
            conn.commit()  # Commit the transaction
            new_user_record = cursor.fetchone()
            if new_user_record:
                user_id, tier = new_user_record
                logging.info(f"Created new user (ID: {user_id}, Tier: {tier})")
                return {"id": user_id, "tier": tier}
            else:
                raise DatabaseError("Failed to retrieve new user details after insertion.")
    except DatabaseError as e:
        logging.error(f"Database error getting/creating user for google_id {google_id}: {e}")
        raise DatabaseError(f"DB error accessing user data: {e}")
    except AuthenticationError as ae: # Catch and re-raise AuthError
        raise ae
    except Exception as e: # Catch other unexpected errors
        logging.error(f"Unexpected error in get_or_create_user for {google_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error accessing user data: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            release_db_connection(conn)

# --- NEW: Authentication Decorator --- (Can be shared with check_media.py)
def require_auth(f):
    """
    Decorator to verify Google access token from Authorization header,
    fetch/create user, and store user info in Flask's 'g'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        endpoint = request.endpoint or "unknown_endpoint"
        logging.debug(f"@{endpoint}: require_auth decorator invoked.")
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logging.warning(f"@{endpoint}: Missing or invalid Authorization header.")
            return jsonify({"error": "Authorization header missing or invalid"}), 401

        access_token = auth_header.split('Bearer ')[1]
        if not access_token:
            logging.warning(f"@{endpoint}: Empty token in Authorization header.")
            return jsonify({"error": "Empty token provided"}), 401

        try:
            # Step 1: Verify Access Token via Google UserInfo
            user_info = verify_google_access_token(access_token)
            google_id = user_info.get('sub') # or user_info.get('id')
            email = user_info.get('email')

            if not google_id:
                 # Should not happen if verify_google_access_token is correct
                 raise AuthenticationError("Verified token info missing user ID ('sub').")

            # Step 2: Get/Create User in DB
            db_user = get_or_create_user(google_id=google_id, email=email)

            # Step 3: Store user info in request context 'g'
            g.user = {
                "id": db_user.get('id'),
                "tier": db_user.get('tier'),
                "google_id": google_id,
                "email": email
            }
            logging.info(f"@{endpoint}: User authenticated successfully. DB User ID: {g.user['id']}, Tier: {g.user['tier']}")

            # Proceed to the actual route function
            return f(*args, **kwargs)

        except AuthenticationError as auth_err:
            logging.warning(f"@{endpoint}: Authentication failed. Error: {auth_err}")
            return jsonify({"error": f"Authentication failed: {auth_err}"}), 401
        except DatabaseError as db_err:
            logging.error(f"@{endpoint}: Database error during user processing. Error: {db_err}", exc_info=True)
            return jsonify({"error": f"Server error during user processing: {db_err}"}), 500
        except Exception as e:
             logging.error(f"@{endpoint}: Unexpected error during authentication/user processing. Error: {e}", exc_info=True)
             return jsonify({"error": "Unexpected server error during authentication"}), 500

    return decorated_function

# --- Agent Tool Functions ---

def check_database_for_url(url: str) -> str:
    """
    Checks if a URL's domain is in the credibility database.
    Connects to the PostgreSQL database via pool, extracts the domain from the URL,
    and queries the URL_VERDICTS_TABLE for a matching domain.
    Returns the verdict ('real', 'fake') or 'not_found'.
    Raises DatabaseError on connection or query issues.
    """
    logging.info(f"Tool Call: check_database_for_url(url='{url}')")
    domain = extract_domain_from_url(url)
    if not domain:
        logging.warning("Invalid URL or domain could not be extracted.")
        return "invalid_url" # Return specific string for invalid URL

    conn = None
    cursor = None
    verdict = VERDICT_NOT_FOUND
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT verdict FROM {URL_VERDICTS_TABLE} WHERE domain = %s", (domain,))
        result = cursor.fetchone()
        if result:
            verdict = result[0] # Should be VERDICT_REAL or VERDICT_FAKE
            logging.info(f"Verdict found for domain '{domain}': {verdict}")
        else:
            logging.info(f"No verdict found for domain '{domain}'.")
        return verdict
    except DatabaseError as e:
        logging.error(f"Database error checking URL '{url}' (domain: {domain}): {e}")
        raise DatabaseError(f"DB error checking URL: {e}")
    except Exception as e:
        logging.error(f"Unexpected error checking URL '{url}': {e}")
        raise DatabaseError(f"Unexpected DB error: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            release_db_connection(conn)


def search_google_for_context(query: str) -> List[Dict[str, str]]:
    """
    Searches for corroborating news articles using Google Custom Search API.
    Prioritizes Indian news sources where possible.
    Returns a list of {title, link, snippet} dictionaries.
    """
    logging.info(f"Tool Call: search_google_for_context(query='{query[:50]}...')")
    
    if not GOOGLE_CUSTOM_SEARCH_API_KEY or not GOOGLE_CUSTOM_SEARCH_ENGINE_ID:
        logging.warning("Google Custom Search API not configured. Skipping search.")
        return []
    
    endpoint = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_CUSTOM_SEARCH_API_KEY,
        "cx": GOOGLE_CUSTOM_SEARCH_ENGINE_ID,
        "q": query,
        "num": GOOGLE_SEARCH_RESULT_LIMIT,
        "gl": "in",  # Geolocation: India
        "lr": "lang_en|lang_hi",  # Language: English or Hindi
    }
    
    results: List[Dict[str, str]] = []
    try:
        response = requests.get(endpoint, params=params, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        for item in items:
            title = str(item.get("title", ""))
            link = str(item.get("link", ""))
            snippet = str(item.get("snippet", ""))
            results.append({"title": title, "link": link, "snippet": snippet})
            
        logging.info(f"Found {len(results)} search results for query.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error querying Google Custom Search API for query '{query}': {e}")
    except Exception as e:
        logging.error(f"Unexpected error during Google search: {e}")
    
    return results


def fact_check_claims(claims: List[str]) -> List[Dict[str, str]]:
    """
    Performs fact checks on a list of claims using the Google Fact Check Tools API.
    Returns a list of fact-check result dictionaries.
    Raises ApiError or ConfigurationError.
    """
    logging.info(f"Tool Call: fact_check_claims({len(claims)} claims)")
    if not GOOGLE_FACT_CHECK_API_KEY or GOOGLE_FACT_CHECK_API_KEY.startswith("YOUR_"):
         raise ConfigurationError("Google Fact Check API Key not configured.")

    if not claims:
        return []

    all_results = []
    claims_to_check = claims[:FACT_CHECK_CLAIM_LIMIT]
    tool_errors = []

    for claim_text in claims_to_check:
         truncated_claim = claim_text[:FACT_CHECK_QUERY_SIZE_LIMIT]
         logging.info(f"Checking claim: '{truncated_claim[:100]}...'")
         try:
             response = requests.get(
                 FACT_CHECK_API_URL,
                 params={"query": truncated_claim, "pageSize": 1, "languageCode": "en"},
                 headers={"X-Goog-Api-Key": GOOGLE_FACT_CHECK_API_KEY},
                 timeout=API_TIMEOUT_SECONDS
             )
             response.raise_for_status()
             data = response.json()
             found_claims_data = data.get("claims", [])

             if found_claims_data and isinstance(found_claims_data, list):
                 first_claim_data = found_claims_data[0]
                 if first_claim_data and isinstance(first_claim_data, dict):
                     review_list = first_claim_data.get("claimReview", [])
                     if review_list and isinstance(review_list, list):
                         review = review_list[0]
                         if review and isinstance(review, dict):
                             publisher = review.get("publisher", {})
                             publisher_name = "Unknown Source"
                             if publisher and isinstance(publisher, dict):
                                 publisher_name = str(publisher.get("name", "Unknown Source"))

                             all_results.append({
                                 "source": publisher_name,
                                 "title": str(review.get("title", first_claim_data.get("text", "N/A"))),
                                 "url": str(review.get("url", "#")),
                                 "claim": str(first_claim_data.get("text", claim_text)), # Original or API's version
                                 "review_rating": str(review.get("textualRating", "N/A"))
                             })
         except requests.exceptions.Timeout:
             err_msg = f"Timeout calling Fact Check API for claim: {truncated_claim}"
             logging.error(err_msg)
             tool_errors.append(err_msg)
         except requests.exceptions.RequestException as e:
             err_msg = f"Error calling Google Fact Check API: {e}"
             logging.error(err_msg)
             tool_errors.append(err_msg)
         except json.JSONDecodeError as e:
             err_msg = f"Error decoding Google Fact Check API response: {e}"
             logging.error(err_msg)
             tool_errors.append(err_msg)
         except Exception as e:
             err_msg = f"Unexpected error during fact check for claim '{truncated_claim}': {e}"
             logging.error(err_msg)
             tool_errors.append(err_msg)

    if tool_errors:
        combined_error_msg = f"Fact check tool encountered errors: {'; '.join(tool_errors)}"
        logging.error(combined_error_msg)
        raise ApiError(combined_error_msg)

    logging.info(f"Found {len(all_results)} fact checks for {len(claims_to_check)} claims.")
    return all_results


def update_analysis_results(url: str, analysis_result: Dict[str, Any]) -> None:
    """
    Stores the final analysis result in the ANALYSIS_RESULTS_TABLE PostgreSQL table.
    Connects via pool and inserts/updates the result based on the URL.
    Raises DatabaseError on connection or query issues.
    """
    logging.info(f"DB Call: update_analysis_results(url='{url}')")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO {ANALYSIS_RESULTS_TABLE} (url, result_json, timestamp)
            VALUES (%s, %s, NOW())
            ON CONFLICT (url) DO UPDATE SET
                result_json = EXCLUDED.result_json,
                timestamp = NOW();
            """,
            (url, json.dumps(analysis_result))
        )
        conn.commit()  # Commit the transaction
        logging.info(f"Analysis result saved/updated for URL: {url}")
    except DatabaseError as e:
        logging.error(f"Database error updating analysis results for '{url}': {e}")
        raise DatabaseError(f"DB error updating results: {e}")
    except json.JSONDecodeError as e:
         logging.error(f"Error encoding analysis result to JSON for URL '{url}': {e}")
         raise DatabaseError(f"Failed to serialize result to JSON: {e}")
    except Exception as e:
        logging.error(f"Unexpected error updating analysis results: {e}")
        raise DatabaseError(f"Unexpected DB error: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            release_db_connection(conn)


# --- Translation Helper Functions ---

translate_client = None

def get_translate_client():
    """Lazily initializes and returns the Google Cloud Translation client."""
    global translate_client
    if translate_client is None:
        if translate is None:
            raise ConfigurationError("Google Cloud Translation library is not installed. Run: pip install google-cloud-translate")
        try:
            translate_client = translate.Client()
            logging.info("Google Cloud Translation client initialized.")
        except Exception as e:
            logging.error(f"Error initializing Translation client: {e}")
            raise ConfigurationError(f"Failed to initialize Translation client: {e}")
    return translate_client

def detect_language(text: str) -> str:
    """
    Detects the language of the given text.
    Returns the language code (e.g., 'en', 'hi', 'es').
    If Translation API is not available, defaults to English.
    """
    try:
        client = get_translate_client()
        result = client.detect_language(text)
        language = result['language']
        confidence = result.get('confidence', 0)
        logging.info(f"Detected language: {language} (confidence: {confidence:.2f})")
        return language
    except Exception as e:
        # Log the error but don't fail - just default to English
        logging.warning(f"Language detection unavailable (Translation API may not be enabled): {e}")
        logging.info("Defaulting to English (en)")
        return 'en'  # Default to English on error

def translate_text(text: str, target_language: str, source_language: str = 'en') -> str:
    """
    Translates text from source language to target language.
    If Translation API is not available, returns original text.
    """
    if source_language == target_language:
        return text  # No translation needed
    
    try:
        client = get_translate_client()
        result = client.translate(
            text,
            target_language=target_language,
            source_language=source_language
        )
        translated_text = result['translatedText']
        logging.info(f"Translated text from {source_language} to {target_language}")
        return translated_text
    except Exception as e:
        logging.warning(f"Translation unavailable (Translation API may not be enabled): {e}")
        logging.info("Returning original text without translation")
        return text  # Return original text on error


# --- Vertex AI / Gemini Setup ---

gemini_model = None
system_instruction = None  # Will be set after initialization

try:
    check_configuration() # Check config and initialize Cloud SQL connector and Vertex AI
    
    # Initialize Vertex AI
    if VERTEXAI_AVAILABLE:
        try:
            vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
            logging.info(f"Vertex AI initialized for project {GCP_PROJECT_ID} in {GCP_LOCATION}")
        except Exception as e:
            logging.warning(f"Could not initialize vertexai module: {e}")
    
    # Initialize Gemini model via Vertex AI
    try:
        if GenerativeModel is None:
            raise ImportError("GenerativeModel not available. Install: pip install google-cloud-aiplatform")
        
        gemini_model = GenerativeModel(
            GEMINI_MODEL_NAME
        )
        logging.info(f"Vertex AI Gemini model '{GEMINI_MODEL_NAME}' initialized.")
    except Exception as e:
        logging.error(f"Error initializing Gemini model: {e}")
        raise ConfigurationError(f"Failed to initialize Gemini model: {e}")

    agent_tools = [
        check_database_for_url,
        search_google_for_context,
        fact_check_claims,
    ]

    # Define system instruction (using global variable to avoid NameError)
    current_date_str = current_datetime.strftime("%Y-%m-%d")
    system_instruction = '''You are an AI agent specialized in detecting and classifying online news articles as credible or misleading. Your output must be highly accurate and well-supported.

You will be given:
- url: a string containing the article's URL
- text: the full text of the article
- Today's date is ''' + current_date_str + '''

Your final determination must be an absolute confidence score. If a news article is credible, trustworthy, and verifiable across all tools, you MUST provide a very high score (e.g., 0.90 to 0.95). If the article is clearly misleading, sensational, or a scam, you MUST also provide a very high score (e.g., 0.90 to 0.95), reflecting your strong conviction. Do not provide a neutral score (e.g., 50-75%) unless the analysis is genuinely inconclusive.

Your job is to:
1. Determine whether the article is likely real or fake.
2. Provide a clear, high-confidence score (not a rounded number, e.g., 0.9345).
3. Analyze the text for sentiment (positive, negative, neutral) and bias.
4. Support your determination with specific, educational reasoning.

Output ONLY the following JSON object (no additional text):
{
  "textResult": {
    "label": "LABEL_1" or "LABEL_0",
    "score": 0.85,
    "sentiment": { "label": "neutral", "score": 0.5 },
    "bias": { "summary": "No significant bias detected", "indicators": [] },
    "highlights": ["Key claim from article"],
    "reasoning": ["Reason 1", "Reason 2"],
    "educational_insights": ["Insight 1"],
    "fact_check": [
      {
        "source": "Source Name",
        "title": "Fact check title",
        "url": "https://example.com",
        "claim": "The claim",
        "rating": "True/False/Mixed"
      }
    ],
    "localized_summary": {
        "reasoning": "Summary in English",
        "educational_insights": "Insights in English"
    }
  }
}

IMPORTANT RULES:
- LABEL_0 = likely real/credible news
- LABEL_1 = likely fake/misleading news
- score MUST be a decimal number between 0 and 1 (e.g., 0.8523, NOT 85%)
- sentiment label MUST be one of: "positive", "negative", "neutral"
- ALL fields are REQUIRED - do not omit any field

Process & Edge-Case Rules:

1. **Tool Calls (MUST CALL):**
   * Call `check_database_for_url(url)`. This verdict is a strong signal.
   * Call `search_google_for_context(query)` using the article's main claims to find corroborating news.
   * Call `fact_check_claims(claims)` for specific assertions.

2. **Sentiment/Bias Analysis (Consolidated):**
   * Perform sentiment analysis on the text and populate the `sentiment` object with a label ("positive", "negative", "neutral") and confidence score.
   * Perform bias analysis and populate the `bias` object with a summary and specific indicators (e.g., "Sensational Language," "Political Leaning," "Emotional Manipulation").

3. **Scoring & Label:**
   * Base the `score` on the cumulative evidence from all tools. If `check_database_for_url`, `search_google_for_context`, and `fact_check_claims` all align, your score MUST be between 0.90 and 0.95.
   * Use non-rounded confidence scores (e.g., 0.9127, not 0.90).

4. **Educational Insights (NEW FIELD):**
   * Populate `educational_insights` with user-friendly explanations of *why* the content is misleading. Examples:
     - "The article uses emotionally charged language, a common tactic of sensationalism."
     - "This claim is a logical fallacy known as a 'straw man,' where the author misrepresents an opponent's argument."
     - "The source has a history of publishing unverified information."

5. **Merge Tool Results:**
   * The `fact_check` array must combine all results from `fact_check_claims` (with a `rating`) and `search_google_for_context`.
   * Format for search results: {{"source": "Google Search", "title": "<title>", "url": "<url>", "claim": "<snippet>", "rating": "Corroborating" or "Contradicting"}}

6. **Localization (NEW FIELD):**
   * The system will handle translation. Output your analysis in English only.


Process & Analysis Rules:

1. **Tool Calls (MUST USE):**
   - Call check_database_for_url(url) to verify domain credibility
   - Call search_google_for_context(query) to find corroborating news
   - Call fact_check_claims(claims) for specific assertions

2. **Scoring Guidelines:**
   - Base score on cumulative evidence from ALL tools
   - If all tools align (real/fake), score MUST be 0.90-0.95
   - Use non-rounded scores (e.g., 0.9127, NOT 0.90)

3. **Sentiment/Bias Analysis:**
   - Analyze article tone (positive/negative/neutral)
   - Identify bias indicators (sensationalism, emotional manipulation, etc.)

4. **Educational Insights:**
   - Explain WHY content may be misleading
   - Provide logical fallacy examples
   - Help users understand misinformation tactics

5. **Fact Check Merging:**
   - Combine results from fact_check_claims() and search_google_for_context()
   - Each entry needs: source, title, url, claim, rating

CRITICAL OUTPUT REQUIREMENTS:
- Your response MUST be ONLY valid JSON
- NO explanatory text before or after JSON
- NO markdown code blocks (no ``` or ```json)
- NO comments or notes inside JSON
- Start with { and end with }
- ALL fields are REQUIRED (label, score, sentiment, bias, highlights, reasoning, educational_insights, fact_check, localized_summary)
'''


except ConfigurationError as e:
    logging.critical(f"Configuration failed: {e}")
except Exception as e:
    logging.critical(f"Failed to initialize Vertex AI Gemini model or Cloud SQL connector: {e}")

# --- Main Analysis Function ---

def analyze_article(url: str, article_text: str) -> Dict[str, Any]:
    """
    Analyzes a news article using Vertex AI Gemini with the comprehensive analysis system.

    Args:
        url: The URL of the article.
        article_text: The text content of the article.

    Returns:
        A dictionary containing the analysis results in the specified format,
        or an error dictionary if analysis cannot proceed.
    """
    logging.info(f"--- Analyzing Article --- URL: {url}")
    logging.debug(f"Text: {article_text[:200]}...")

    if not url or not article_text:
        return {
            "textResult": {
                "error": "URL and article text must be provided."
            }
        }

    # Detect language for localization
    detected_language = detect_language(article_text[:500])  # Use first 500 chars for detection
    logging.info(f"Detected article language: {detected_language}")

    initial_prompt = f"{system_instruction}\n\nAnalyze the following article:\nURL: {url}\n\nText:\n{article_text}"

    try:
        # Use Vertex AI Gemini model
        if GenerationConfig is None:
            raise ImportError("GenerationConfig not available")
        
        generation_config = GenerationConfig(
            temperature=GEMINI_TEMPERATURE,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            response_mime_type="application/json"  # Force JSON response
        )
        
        response = gemini_model.generate_content(
            initial_prompt,
            generation_config=generation_config
        )

        if hasattr(response, 'text') and response.text:
            final_text = response.text
            logging.info("Received final text response from Vertex AI Gemini.")
            logging.debug(f"Raw response (first 500 chars): {final_text[:500]}")
            
            try:
                # Clean up markdown code blocks if present
                cleaned_text = final_text.strip()
                
                # Remove markdown code blocks
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]  # Remove ```json
                elif cleaned_text.startswith("```"):
                    cleaned_text = cleaned_text[3:]  # Remove ```
                
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]  # Remove trailing ```
                
                cleaned_text = cleaned_text.strip()
                
                # Try to find JSON if there's extra text
                if not cleaned_text.startswith('{'):
                    # Look for the first { and last }
                    start_idx = cleaned_text.find('{')
                    end_idx = cleaned_text.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        cleaned_text = cleaned_text[start_idx:end_idx+1]
                        logging.info("Extracted JSON from response text")
                
                logging.debug(f"Cleaned text (first 500 chars): {cleaned_text[:500]}")
                analysis_result = json.loads(cleaned_text)
                
                # Validate the response structure
                if "textResult" not in analysis_result:
                    logging.warning("Response missing 'textResult' key, wrapping response")
                    analysis_result = {"textResult": analysis_result}
                
                # Ensure required fields exist
                text_result = analysis_result.get("textResult", {})
                if "label" not in text_result:
                    logging.warning("Response missing 'label' field")
                if "score" not in text_result:
                    logging.warning("Response missing 'score' field")
                
                logging.info(f"Analysis successful for URL: {url}")

                # Add localization if language is not English
                if detected_language and detected_language != 'en':
                    try:
                        text_result = analysis_result.get("textResult", {})
                        reasoning_en = "\n".join(text_result.get("reasoning", []))
                        insights_en = "\n".join(text_result.get("educational_insights", []))
                        
                        # Translate reasoning and insights to detected language
                        reasoning_localized = translate_text(reasoning_en, detected_language, 'en')
                        insights_localized = translate_text(insights_en, detected_language, 'en')
                        
                        # Update localized_summary
                        text_result["localized_summary"] = {
                            "reasoning": reasoning_localized,
                            "educational_insights": insights_localized
                        }
                        analysis_result["textResult"] = text_result
                        logging.info(f"Added localized summary in language: {detected_language}")
                    except Exception as e:
                        logging.error(f"Error adding localization: {e}")

                # Store results in database
                try:
                    update_analysis_results(url, analysis_result)
                except DatabaseError as db_err:
                    logging.error(f"Failed to store analysis result in DB: {db_err}")
                
                return analysis_result
                
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding final model JSON response: {e}")
                logging.error(f"Raw final model response text (first 1000 chars): {final_text[:1000]}")
                logging.error(f"JSON error at position {e.pos}: {e.msg}")
                
                # Return error in the expected format so frontend can display it
                return {
                    "textResult": {
                        "error": "Model did not return valid JSON in the final response.",
                        "details": f"JSON parse error: {e.msg}",
                        "raw_response_preview": final_text[:500] if len(final_text) > 500 else final_text
                    }
                }
        else:
            logging.error("Final response from Vertex AI Gemini did not contain text.")
            if hasattr(response, 'prompt_feedback'):
                 logging.error(f"Prompt Feedback: {response.prompt_feedback}")
            if hasattr(response, 'candidates') and response.candidates:
                 logging.error(f"Finish Reason: {getattr(response.candidates[0], 'finish_reason', 'N/A')}")
                 logging.error(f"Safety Ratings: {getattr(response.candidates[0], 'safety_ratings', 'N/A')}")

            return {
                "textResult": {
                    "error": "Model did not provide a final text analysis.",
                    "details": "No text in response"
                }
            }

    except (ApiError, DatabaseError, ConfigurationError) as known_err:
         logging.error(f"A tool function failed during analysis for URL '{url}': {known_err}")
         return {
             "textResult": {
                 "error": f"Analysis failed due to tool error: {known_err}"
             }
         }
    except Exception as e:
        logging.critical(f"An unexpected error occurred during Gemini interaction for URL '{url}': {e}")
        logging.critical(traceback.format_exc())
        return {
            "textResult": {
                "error": f"An unexpected server error occurred during analysis interaction.",
                "details": str(e)
            }
        }


# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

try:
    check_configuration()
except ConfigurationError as e:
    logging.critical(f"CRITICAL CONFIGURATION ERROR: {e}. Flask app might not function correctly.")

# --- Modified: /analyze Endpoint ---
@app.route('/analyze', methods=['POST'])
@require_auth # Apply the new authentication decorator
def handle_analyze():
    """Flask endpoint to handle article analysis requests."""
    # Authentication is handled by the @require_auth decorator
    # g.user is now available with verified user info

    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    url = data.get('url')
    article_text = data.get('article_text')

    if not url or not article_text:
        return jsonify({"error": "Missing 'url' or 'article_text' in JSON payload"}), 400

    # Log the request with the authenticated user ID
    logging.info(f"Received analysis request for URL: {url} from User ID: {g.user['id']} (Google ID: {g.user['google_id']})")

    # --- Proceed with analysis ---
    result = analyze_article(url, article_text)
    
    # Log the result structure for debugging
    has_error = False
    if "textResult" in result and "error" in result.get("textResult", {}):
        has_error = True
        logging.error(f"Analysis returned error: {result['textResult'].get('error')}")
    else:
        logging.info(f"Analysis result keys: {list(result.keys())}")
        if "textResult" in result:
            logging.info(f"textResult keys: {list(result['textResult'].keys())}")

    # Determine status code
    status_code = 200
    if has_error:
        error_msg = result.get("textResult", {}).get("error", "")
        if "Analysis failed due to tool error" in error_msg:
            status_code = 502  # Bad Gateway if a downstream API failed
        elif "Model did not return valid JSON" in error_msg or "Model did not provide a final text analysis" in error_msg:
            status_code = 500  # Internal server error for model issues
        elif "URL and article text must be provided" in error_msg:
            status_code = 400  # Bad request
        else:
            status_code = 500  # Default to internal server error

    return jsonify(result), status_code

@app.route('/')
def index():
    gemini_status = "Initialized" if gemini_model else "Not Initialized (Check Logs)"
    connector_status = "Initialized" if connector else "Not Initialized (Check Logs)"
    return jsonify({
        "message": "TruthScope Analysis Backend (GCP-Native)",
        "gemini_model_status": gemini_status,
        "cloud_sql_connector_status": connector_status,
        "gcp_project": GCP_PROJECT_ID,
        "location": GCP_LOCATION
    })


if __name__ == "__main__":
    logging.info("Starting Flask development server...")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    logging.info("Flask server stopping...")
    close_cloud_sql_connector()
    logging.info("Script finished.")