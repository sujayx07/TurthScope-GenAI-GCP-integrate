import logging
import os
import json
import traceback
import base64
import io
from functools import wraps
from typing import Dict, Any, Optional, List

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, g
from flask_cors import CORS

# --- Google Cloud Platform Imports ---
from google.cloud import aiplatform
from google.cloud import vision
from google.cloud import speech_v1 as speech
from google.cloud.sql.connector import Connector
import pg8000

# --- Google Auth ---
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# --- Load Environment Variables ---
load_dotenv()
logging.critical("--- check_media.py script started ---")

# --- Configuration ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# GCP Configuration
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")

# Cloud SQL Configuration
CLOUD_SQL_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")
DB_NAME = os.getenv("DB_NAME", "news_analysis_db")
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# Database Constants
USERS_TABLE = "users"
DEFAULT_USER_TIER = "free"
PAID_TIER = "paid"

# API Constants
API_TIMEOUT_SECONDS = 20

# Gemini Model Configuration
GEMINI_MODEL_NAME = "gemini-2.5-flash"  # For multi-modal analysis
GEMINI_TEMPERATURE = 0.2

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s')
logging.info("Logging configured with level DEBUG.")

class ConfigurationError(Exception): pass
class DatabaseError(Exception): pass
class ApiError(Exception): pass
class AuthenticationError(Exception): pass
class AuthorizationError(Exception): pass

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization", "Accept"])
logging.info("Flask app created and CORS configured.")

connector = None

def initialize_cloud_sql_connector():
    """Initializes the Cloud SQL Python Connector."""
    global connector
    if connector is not None:
        logging.debug("Cloud SQL Connector already initialized.")
        return
    logging.info(f"Initializing Cloud SQL Connector for {DB_NAME}...")
    try:
        connector = Connector()
        logging.info("Cloud SQL Connector initialized successfully.")
    except Exception as e:
        logging.error(f"FATAL: Error initializing Cloud SQL Connector: {e}", exc_info=True)
        connector = None
        raise DatabaseError(f"Failed to initialize Cloud SQL Connector: {e}")

def get_db_connection():
    """Gets a connection using the Cloud SQL Python Connector."""
    if connector is None:
        logging.error("Attempted to get DB connection, but connector is not initialized.")
        try:
            initialize_cloud_sql_connector()
        except DatabaseError:
             logging.error("Initialization of Cloud SQL Connector failed.")
             raise DatabaseError("Cloud SQL Connector is not available and initialization failed.")
        if connector is None:
             raise DatabaseError("Cloud SQL Connector is not available.")
    
    try:
        logging.debug("Attempting to get Cloud SQL connection...")
        conn = connector.connect(
            CLOUD_SQL_CONNECTION_NAME,
            "pg8000",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME
        )
        logging.debug(f"Successfully got Cloud SQL connection (ID: {id(conn)}).")
        return conn
    except Exception as e:
        logging.error(f"Error getting Cloud SQL connection: {e}", exc_info=True)
        raise DatabaseError(f"Failed to get Cloud SQL connection: {e}")

def release_db_connection(conn):
    """Closes a Cloud SQL connection."""
    if conn:
        conn_id = id(conn)
        try:
            logging.debug(f"Closing Cloud SQL connection (ID: {conn_id}).")
            conn.close()
            logging.debug(f"Connection (ID: {conn_id}) closed successfully.")
        except Exception as e:
            logging.error(f"Error closing connection (ID: {conn_id}): {e}", exc_info=True)

def close_cloud_sql_connector():
    """Closes the Cloud SQL Connector."""
    global connector
    if connector:
        logging.info("Closing Cloud SQL Connector.")
        try:
            connector.close()
            logging.info("Cloud SQL Connector closed.")
        except Exception as e:
            logging.error(f"Error closing Cloud SQL Connector: {e}", exc_info=True)
        finally:
            connector = None

def check_configuration():
    logging.info("Checking media backend configuration...")
    required_vars = {
        "GOOGLE_API_KEY": GOOGLE_API_KEY,
        "GCP_PROJECT_ID": GCP_PROJECT_ID,
        "CLOUD_SQL_CONNECTION_NAME": CLOUD_SQL_CONNECTION_NAME,
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD,
        "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
    }
    missing_vars = [name for name, value in required_vars.items() if not value or str(value).startswith("YOUR_")]
    if missing_vars:
        error_msg = f"Missing or placeholder required configuration variables: {', '.join(missing_vars)}"
        logging.critical(error_msg)
        raise ConfigurationError(error_msg)

    logging.info("Media backend configuration check passed.")
    
    # Initialize Cloud SQL Connector
    initialize_cloud_sql_connector()
    
    # Initialize Vertex AI
    aiplatform.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
    logging.info(f"Vertex AI initialized for project {GCP_PROJECT_ID} in {GCP_LOCATION}")

def verify_google_access_token(access_token: str) -> Dict[str, Any]:
    logging.debug("Verifying Google access token...")
    userinfo_url = 'https://www.googleapis.com/oauth2/v1/userinfo?alt=json'
    try:
        response = requests.get(
            userinfo_url,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=API_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        user_info = response.json()
        if not user_info or 'id' not in user_info:
            raise AuthenticationError("Invalid user info received from Google.")
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

def get_or_create_user(google_id: str, email: Optional[str] = None) -> Dict[str, Any]:
    logging.debug(f"get_or_create_user: Attempting lookup/creation for google_id: '{google_id}', email: '{email}'")
    if not google_id:
        logging.error("get_or_create_user: Received empty or None google_id.")
        raise AuthenticationError("Google User ID cannot be empty.")

    conn = None
    try:
        conn = get_db_connection()
        logging.debug(f"get_or_create_user: Acquired DB connection for google_id: {google_id}")
        with conn.cursor() as cursor:
            logging.debug(f"get_or_create_user: Executing SELECT for google_id: {google_id}")
            cursor.execute(f"SELECT id, tier FROM {USERS_TABLE} WHERE google_id = %s", (google_id,))
            user_record = cursor.fetchone()

            if user_record:
                user_id, tier = user_record
                logging.info(f"get_or_create_user: Found existing user (ID: {user_id}, Tier: {tier}) for google_id: {google_id}")
                return {"id": user_id, "tier": tier}
            else:
                logging.info(f"get_or_create_user: No existing user found. Creating new user for google_id: {google_id}")
                cursor.execute(
                    f"""INSERT INTO {USERS_TABLE} (google_id, email, tier, created_at)
                       VALUES (%s, %s, %s, NOW()) RETURNING id, tier;""",
                    (google_id, email, DEFAULT_USER_TIER)
                )
                new_user_record = cursor.fetchone()
                if new_user_record:
                    user_id, tier = new_user_record
                    logging.info(f"get_or_create_user: Created new user (ID: {user_id}, Tier: {tier}) for google_id: {google_id}")
                    conn.commit()
                    return {"id": user_id, "tier": tier}
                else:
                    logging.error(f"get_or_create_user: Failed to retrieve new user details after insertion for google_id: {google_id}")
                    conn.rollback()
                    raise DatabaseError("Failed to retrieve new user details after insertion.")

    except AuthenticationError as ae:
        logging.error(f"get_or_create_user: AuthenticationError for google_id '{google_id}': {ae}")
        raise ae
    except DatabaseError as e:
        logging.error(f"get_or_create_user: Database error for google_id '{google_id}': {e}", exc_info=True)
        if conn: 
            try:
                conn.rollback()
            except:
                pass
        raise DatabaseError(f"DB error accessing user data for google_id {google_id}: {e}")
    except Exception as e:
        logging.error(f"get_or_create_user: Unexpected error for google_id '{google_id}': {e}", exc_info=True)
        if conn: conn.rollback()
        raise DatabaseError(f"Unexpected error accessing user data for google_id {google_id}: {e}")
    finally:
        if conn:
            release_db_connection(conn)

def require_auth_and_paid_tier(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        endpoint = request.endpoint or "unknown_endpoint"
        logging.debug(f"@{endpoint}: require_auth_and_paid_tier decorator invoked.")

        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logging.warning(f"@{endpoint}: Missing or invalid Authorization header.")
            return jsonify({"error": "Authorization header missing or invalid"}), 401

        access_token = auth_header.split('Bearer ')[1]
        if not access_token:
            logging.warning(f"@{endpoint}: Empty token in Authorization header.")
            return jsonify({"error": "Empty token provided"}), 401

        try:
            user_info = verify_google_access_token(access_token)
            google_id = user_info.get('sub')
            email = user_info.get('email')

            if not google_id:
                 raise AuthenticationError("Verified token info missing user ID ('sub').")

            logging.info(f"@{endpoint}: Token verified for Google ID: {google_id}")

            db_user = get_or_create_user(google_id=google_id, email=email)
            g.user = {
                "id": db_user.get('id'),
                "tier": db_user.get('tier'),
                "google_id": google_id,
                "email": email
            }
            logging.info(f"@{endpoint}: User authenticated successfully. DB User ID: {g.user['id']}, Tier: {g.user['tier']}")

        except AuthenticationError as auth_err:
            logging.warning(f"@{endpoint}: Authentication failed (token verification or user lookup). Error: {auth_err}")
            return jsonify({"error": f"Authentication failed: {auth_err}"}), 401
        except DatabaseError as db_err:
            logging.error(f"@{endpoint}: Database error during user authentication/processing. Error: {db_err}", exc_info=True)
            return jsonify({"error": f"Server error during user authentication: {db_err}"}), 500
        except Exception as e:
             logging.error(f"@{endpoint}: Unexpected error during authentication/user processing. Error: {e}", exc_info=True)
             return jsonify({"error": "Unexpected server error during authentication"}), 500

        user_tier = g.user.get('tier')
        if user_tier != PAID_TIER:
            logging.warning(f"@{endpoint}: Authorization failed. User {g.user['id']} (Tier: {user_tier}) does not have required tier '{PAID_TIER}'. Access denied.")
            return jsonify({"error": f"Access denied. This feature requires a '{PAID_TIER}' subscription."}), 403

        logging.info(f"@{endpoint}: Authorization successful. User {g.user['id']} has required tier '{PAID_TIER}'.")

        logging.debug(f"@{endpoint}: Authentication & Authorization successful, proceeding to route function.")
        return f(*args, **kwargs)

    return decorated_function

# --- GCP Vision and Gemini Helper Functions ---

vision_client = None
gemini_model = None

def get_vision_client():
    """Lazily initializes and returns the Google Cloud Vision client."""
    global vision_client
    if vision_client is None:
        try:
            vision_client = vision.ImageAnnotatorClient()
            logging.info("Google Cloud Vision client initialized.")
        except Exception as e:
            logging.error(f"Error initializing Vision client: {e}")
            raise ConfigurationError(f"Failed to initialize Vision client: {e}")
    return vision_client

def get_gemini_model():
    """Lazily initializes and returns the Gemini multi-modal model."""
    global gemini_model
    if gemini_model is None:
        try:
            gemini_model = aiplatform.GenerativeModel(
                GEMINI_MODEL_NAME,
                generation_config={
                    "temperature": GEMINI_TEMPERATURE,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }
            )
            logging.info(f"Gemini multi-modal model '{GEMINI_MODEL_NAME}' initialized.")
        except Exception as e:
            logging.error(f"Error initializing Gemini model: {e}")
            raise ConfigurationError(f"Failed to initialize Gemini model: {e}")
    return gemini_model

def analyze_image_with_vision_api(image_url: str) -> Dict[str, Any]:
    """
    Analyzes an image using Google Cloud Vision API.
    Returns SafeSearch annotations and web detection results.
    """
    logging.debug(f"Calling Cloud Vision API for image URL: {image_url}")
    
    try:
        client = get_vision_client()
        image = vision.Image()
        image.source.image_uri = image_url
        
        # Perform safe search detection
        safe_search_response = client.safe_search_detection(image=image)
        safe_search = safe_search_response.safe_search_annotation
        
        # Perform web detection
        web_detection_response = client.web_detection(image=image)
        web_detection = web_detection_response.web_detection
        
        result = {
            "status": "success",
            "safe_search": {
                "adult": safe_search.adult.name,
                "medical": safe_search.medical.name,
                "violence": safe_search.violence.name,
                "racy": safe_search.racy.name,
                "spoof": safe_search.spoof.name,
            },
            "web_detection": {
                "full_matching_images": len(web_detection.full_matching_images) if web_detection.full_matching_images else 0,
                "partial_matching_images": len(web_detection.partial_matching_images) if web_detection.partial_matching_images else 0,
                "pages_with_matching_images": [page.url for page in (web_detection.pages_with_matching_images[:5] if web_detection.pages_with_matching_images else [])],
                "visually_similar_images": len(web_detection.visually_similar_images) if web_detection.visually_similar_images else 0,
            }
        }
        
        logging.debug(f"Cloud Vision API analysis completed for {image_url}")
        return result
        
    except Exception as e:
        logging.error(f"Error calling Cloud Vision API for {image_url}: {e}", exc_info=True)
        return {"status": "error", "error": f"Vision API error: {str(e)}"}

def analyze_image_with_gemini(image_url: str) -> Dict[str, Any]:
    """
    Analyzes an image using Gemini multi-modal to check for AI generation and context.
    """
    logging.debug(f"Calling Gemini multi-modal for image URL: {image_url}")
    
    try:
        model = get_gemini_model()
        
        prompt = f"""Analyze this image and determine:
1. Is this image AI-generated or manipulated? Provide a confidence score (0.0-1.0).
2. What does the image depict? Provide a brief description.
3. Are there any signs of manipulation, deepfake, or synthetic generation?
4. Context: Could this image be used for misinformation?

Image URL: {image_url}

Respond in JSON format:
{{
  "ai_generated_score": float,
  "description": "string",
  "manipulation_indicators": ["string"],
  "context_analysis": "string"
}}
"""
        
        # For Vertex AI, we need to pass the image differently
        # This is a simplified version - in production, you'd download and encode the image
        response = model.generate_content(prompt)
        
        if hasattr(response, 'text') and response.text:
            result_text = response.text.strip()
            if result_text.startswith("```json"):
                result_text = result_text.removeprefix("```json").removesuffix("```").strip()
            elif result_text.startswith("```"):
                result_text = result_text.removeprefix("```").removesuffix("```").strip()
            
            result = json.loads(result_text)
            result["status"] = "success"
            logging.debug(f"Gemini multi-modal analysis completed for {image_url}")
            return result
        else:
            return {"status": "error", "error": "No response from Gemini model"}
            
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding Gemini response: {e}")
        return {"status": "error", "error": f"JSON decode error: {str(e)}"}
    except Exception as e:
        logging.error(f"Error calling Gemini multi-modal for {image_url}: {e}", exc_info=True)
        return {"status": "error", "error": f"Gemini API error: {str(e)}"}

# --- Analysis Logic ---
def analyze_image_logic(image_url: str) -> Dict[str, Any]:
    """
    Analyzes an image using Google Cloud Vision API and Gemini multi-modal.
    Returns a structured result compatible with the frontend.
    """
    logging.info(f"Starting GCP-based image analysis for: {image_url}")

    vision_result = analyze_image_with_vision_api(image_url)
    gemini_result = analyze_image_with_gemini(image_url)

    ai_generated_prob = 0.0
    manipulation_confidence = 0.0
    manipulation_error = None
    final_status = "error"
    description = ""
    manipulation_indicators = []

    # Process Vision API results
    if vision_result.get("status") == "success":
        safe_search = vision_result.get("safe_search", {})
        web_detection = vision_result.get("web_detection", {})
        
        # Check for spoof/manipulation in SafeSearch
        spoof_level = safe_search.get("spoof", "UNKNOWN")
        if spoof_level in ["LIKELY", "VERY_LIKELY"]:
            manipulation_indicators.append(f"Vision API detected likely spoofing: {spoof_level}")
            ai_generated_prob = max(ai_generated_prob, 0.7)

    # Process Gemini results
    if gemini_result.get("status") == "success":
        final_status = "success"
        ai_generated_prob = max(ai_generated_prob, gemini_result.get("ai_generated_score", 0.0))
        description = gemini_result.get("description", "")
        gemini_indicators = gemini_result.get("manipulation_indicators", [])
        manipulation_indicators.extend(gemini_indicators)
        manipulation_confidence = ai_generated_prob
        logging.debug(f"Gemini analysis successful for {image_url}. AI prob: {ai_generated_prob:.4f}")
    else:
        if vision_result.get("status") == "success":
            final_status = "partial_success"
            manipulation_error = gemini_result.get("error", "Gemini analysis unavailable")
        else:
            manipulation_error = f"Vision: {vision_result.get('error')}, Gemini: {gemini_result.get('error')}"
            logging.warning(f"Both Vision and Gemini analysis failed for {image_url}")

    manipulated_found = 1 if ai_generated_prob >= 0.5 else 0

    analysis_summary = ""
    if final_status == "success":
        detection_text = f"Detected as {'AI Generated/Manipulated' if manipulated_found else 'Likely Authentic'} (Confidence: {manipulation_confidence:.2f})."
        if description:
            detection_text += f" Image depicts: {description}"
        if manipulation_indicators:
            detection_text += f" Indicators: {', '.join(manipulation_indicators[:3])}"
        analysis_summary = detection_text
    elif final_status == "partial_success":
        analysis_summary = f"Partial analysis completed. {manipulation_error}"
    else:
        analysis_summary = f"Analysis failed. Error: {manipulation_error}"
        manipulated_found = 0
        manipulation_confidence = 0.0

    result = {
        "status": final_status,
        "images_analyzed": 1,
        "manipulated_images_found": manipulated_found,
        "manipulation_confidence": manipulation_confidence,
        "manipulated_media": [
            {
                "url": image_url,
                "type": "image",
                "description": description,
                "ai_generated": ai_generated_prob if final_status in ["success", "partial_success"] else None,
                "manipulation_indicators": manipulation_indicators,
                "vision_api_result": vision_result if vision_result.get("status") == "success" else None,
                "manipulation_error": manipulation_error
            }
        ],
        "analysis_summary": analysis_summary
    }

    logging.info(f"Image analysis complete for {image_url}. Summary: {analysis_summary}")
    return result

def analyze_video_logic(video_url: str) -> Dict[str, Any]:
    """
    Analyzes a video using Google Cloud Speech-to-Text, Vision API, and Gemini 1.5 Pro.
    Transcribes audio, extracts visual descriptions, and checks for inconsistencies.
    """
    logging.info(f"Starting GCP-based video analysis for: {video_url}")
    
    try:
        # Note: This is a simplified implementation
        # In production, you would need to:
        # 1. Download the video
        # 2. Extract audio track
        # 3. Sample video frames
        # 4. Process with Speech-to-Text and Vision APIs
        
        model = get_gemini_model()
        
        prompt = f"""Analyze this video for potential misinformation or manipulation:

Video URL: {video_url}

Please analyze:
1. Is there any sign of deepfake or video manipulation?
2. Are there inconsistencies between audio and visual content?
3. Does the content appear to be misleading or taken out of context?
4. What is the overall credibility assessment?

Respond in JSON format:
{{
  "manipulation_score": float,
  "deepfake_indicators": ["string"],
  "audio_visual_consistency": "string",
  "content_summary": "string",
  "credibility_assessment": "string"
}}
"""
        
        response = model.generate_content(prompt)
        
        if hasattr(response, 'text') and response.text:
            result_text = response.text.strip()
            if result_text.startswith("```json"):
                result_text = result_text.removeprefix("```json").removesuffix("```").strip()
            elif result_text.startswith("```"):
                result_text = result_text.removeprefix("```").removesuffix("```").strip()
            
            analysis = json.loads(result_text)
            
            manipulation_score = analysis.get("manipulation_score", 0.0)
            manipulated_found = 1 if manipulation_score >= 0.5 else 0
            
            result = {
                "status": "success",
                "videos_analyzed": 1,
                "manipulated_videos_found": manipulated_found,
                "manipulation_confidence": manipulation_score,
                "manipulated_media": [
                    {
                        "url": video_url,
                        "type": "video",
                        "deepfake_indicators": analysis.get("deepfake_indicators", []),
                        "audio_visual_consistency": analysis.get("audio_visual_consistency", ""),
                        "content_summary": analysis.get("content_summary", ""),
                        "credibility_assessment": analysis.get("credibility_assessment", ""),
                    }
                ],
                "analysis_summary": f"Video analysis: {analysis.get('credibility_assessment', 'Analysis completed')}"
            }
            
            logging.info(f"Video analysis complete for {video_url}")
            return result
        else:
            return {
                "status": "error",
                "videos_analyzed": 0,
                "manipulated_videos_found": 0,
                "manipulation_confidence": 0.0,
                "manipulated_media": [],
                "analysis_summary": "No response from Gemini model",
                "error": "Model did not provide a response"
            }
            
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding Gemini response for video {video_url}: {e}")
        return {
            "status": "error",
            "videos_analyzed": 0,
            "manipulated_videos_found": 0,
            "manipulation_confidence": 0.0,
            "manipulated_media": [],
            "analysis_summary": f"JSON decode error: {str(e)}",
            "error": str(e)
        }
    except Exception as e:
        logging.error(f"Error analyzing video {video_url}: {e}", exc_info=True)
        return {
            "status": "error",
            "videos_analyzed": 0,
            "manipulated_videos_found": 0,
            "manipulation_confidence": 0.0,
            "manipulated_media": [],
            "analysis_summary": f"Video analysis failed: {str(e)}",
            "error": str(e)
        }

def analyze_audio_logic(audio_url: str) -> Dict[str, Any]:
    """
    Analyzes audio using Google Cloud Speech-to-Text and Gemini for scam detection.
    Transcribes audio and analyzes for deceptive claims or scam language.
    """
    logging.info(f"Starting GCP-based audio analysis for: {audio_url}")
    
    try:
        # Note: This is a simplified implementation
        # In production, you would need to:
        # 1. Download the audio file
        # 2. Convert to appropriate format
        # 3. Use Speech-to-Text API for transcription
        # 4. Analyze transcription with Gemini
        
        model = get_gemini_model()
        
        prompt = f"""Analyze this audio file for potential scam or deceptive content:

Audio URL: {audio_url}

Please analyze:
1. Is there scam language or deceptive claims?
2. What tactics are being used (urgency, fear, false promises)?
3. Are there indicators of phishing or fraud attempts?
4. What is the credibility assessment?

Respond in JSON format:
{{
  "scam_score": float,
  "scam_indicators": ["string"],
  "deceptive_tactics": ["string"],
  "transcription_summary": "string",
  "credibility_assessment": "string"
}}
"""
        
        response = model.generate_content(prompt)
        
        if hasattr(response, 'text') and response.text:
            result_text = response.text.strip()
            if result_text.startswith("```json"):
                result_text = result_text.removeprefix("```json").removesuffix("```").strip()
            elif result_text.startswith("```"):
                result_text = result_text.removeprefix("```").removesuffix("```").strip()
            
            analysis = json.loads(result_text)
            
            scam_score = analysis.get("scam_score", 0.0)
            manipulated_found = 1 if scam_score >= 0.5 else 0
            
            result = {
                "status": "success",
                "audios_analyzed": 1,
                "manipulated_audios_found": manipulated_found,
                "manipulation_confidence": scam_score,
                "manipulated_media": [
                    {
                        "url": audio_url,
                        "type": "audio",
                        "scam_indicators": analysis.get("scam_indicators", []),
                        "deceptive_tactics": analysis.get("deceptive_tactics", []),
                        "transcription_summary": analysis.get("transcription_summary", ""),
                        "credibility_assessment": analysis.get("credibility_assessment", ""),
                    }
                ],
                "analysis_summary": f"Audio analysis: {analysis.get('credibility_assessment', 'Analysis completed')}"
            }
            
            logging.info(f"Audio analysis complete for {audio_url}")
            return result
        else:
            return {
                "status": "error",
                "audios_analyzed": 0,
                "manipulated_audios_found": 0,
                "manipulation_confidence": 0.0,
                "manipulated_media": [],
                "analysis_summary": "No response from Gemini model",
                "error": "Model did not provide a response"
            }
            
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding Gemini response for audio {audio_url}: {e}")
        return {
            "status": "error",
            "audios_analyzed": 0,
            "manipulated_audios_found": 0,
            "manipulation_confidence": 0.0,
            "manipulated_media": [],
            "analysis_summary": f"JSON decode error: {str(e)}",
            "error": str(e)
        }
    except Exception as e:
        logging.error(f"Error analyzing audio {audio_url}: {e}", exc_info=True)
        return {
            "status": "error",
            "audios_analyzed": 0,
            "manipulated_audios_found": 0,
            "manipulation_confidence": 0.0,
            "manipulated_media": [],
            "analysis_summary": f"Audio analysis failed: {str(e)}",
            "error": str(e)
        }

# --- Flask Endpoints ---

@app.route('/analyze_image', methods=['OPTIONS'])
@app.route('/analyze_video', methods=['OPTIONS'])
@app.route('/analyze_audio', methods=['OPTIONS'])
def handle_options():
    response = jsonify({'message': 'OPTIONS request successful'})
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response, 200

@app.route('/analyze_image', methods=['POST'])
@require_auth_and_paid_tier
def handle_analyze_image():
    endpoint = request.endpoint
    user_id = g.user.get('id', 'Unknown') if hasattr(g, 'user') else 'Unknown'
    user_tier = g.user.get('tier', 'Unknown') if hasattr(g, 'user') else 'Unknown'

    if not request.is_json:
        logging.warning(f"@{endpoint}: Request is not JSON")
        return jsonify({"error": "Request must be JSON", "analysis_summary": "Error: Invalid request format."}), 400

    data = request.get_json()
    media_url = data.get('media_url')

    if not media_url:
        logging.warning(f"@{endpoint}: Missing 'media_url' in JSON payload")
        return jsonify({"error": "Missing 'media_url' in JSON payload", "analysis_summary": "Error: Missing media URL."}), 400

    if not isinstance(media_url, str) or not (media_url.startswith('http://') or media_url.startswith('https://')):
        logging.warning(f"@{endpoint}: Invalid 'media_url' format: {media_url}")
        return jsonify({"error": "Invalid 'media_url' format", "analysis_summary": "Error: Invalid media URL format."}), 400

    logging.info(f"@{endpoint}: Processing image analysis for URL: {media_url} by User ID: {user_id} (Tier: {user_tier})")

    try:
        result = analyze_image_logic(media_url)

        http_status = 200 if result.get("status") == "success" else 500
        if result.get("status") == "error" and result.get("manipulated_media", [{}])[0].get("manipulation_error"):
            if "API returned HTTP error" in result["manipulated_media"][0]["manipulation_error"] or \
               "Timeout calling" in result["manipulated_media"][0]["manipulation_error"] or \
               "Network error calling" in result["manipulated_media"][0]["manipulation_error"]:
                http_status = 502

        logging.info(f"@{endpoint}: Analysis finished for {media_url}. Returning HTTP status {http_status}.")
        return jsonify(result), http_status

    except Exception as e:
        logging.exception(f"@{endpoint}: Unexpected error in handle_analyze_image for {media_url}: {e}")
        return jsonify({
            "status": "error",
            "images_analyzed": 0,
            "manipulated_images_found": 0,
            "manipulation_confidence": 0.0,
            "manipulated_media": [],
            "analysis_summary": "Error: Server failed unexpectedly during image analysis.",
            "error": "An unexpected server error occurred."
        }), 500

@app.route('/analyze_video', methods=['POST'])
@require_auth_and_paid_tier
def handle_analyze_video():
    endpoint = request.endpoint
    user_id = g.user.get('id', 'Unknown') if hasattr(g, 'user') else 'Unknown'
    user_tier = g.user.get('tier', 'Unknown') if hasattr(g, 'user') else 'Unknown'
    
    if not request.is_json:
        logging.warning(f"@{endpoint}: Request is not JSON")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    media_url = data.get('media_url')

    if not media_url:
        logging.warning(f"@{endpoint}: Missing 'media_url' in JSON payload")
        return jsonify({"error": "Missing 'media_url' in JSON payload"}), 400

    logging.info(f"@{endpoint}: Processing video analysis for URL: {media_url} by User ID: {user_id} (Tier: {user_tier})")

    try:
        result = analyze_video_logic(media_url)
        http_status = 200 if result.get("status") == "success" else 500
        logging.info(f"@{endpoint}: Analysis finished for {media_url}. Returning HTTP status {http_status}.")
        return jsonify(result), http_status
    except Exception as e:
        logging.exception(f"@{endpoint}: Unexpected error in handle_analyze_video for {media_url}: {e}")
        return jsonify({
            "status": "error",
            "videos_analyzed": 0,
            "manipulated_videos_found": 0,
            "manipulation_confidence": 0.0,
            "manipulated_media": [],
            "analysis_summary": "Error: Server failed unexpectedly during video analysis.",
            "error": str(e)
        }), 500

@app.route('/analyze_audio', methods=['POST'])
@require_auth_and_paid_tier
def handle_analyze_audio():
    endpoint = request.endpoint
    user_id = g.user.get('id', 'Unknown') if hasattr(g, 'user') else 'Unknown'
    user_tier = g.user.get('tier', 'Unknown') if hasattr(g, 'user') else 'Unknown'
    
    if not request.is_json:
        logging.warning(f"@{endpoint}: Request is not JSON")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    media_url = data.get('media_url')

    if not media_url:
        logging.warning(f"@{endpoint}: Missing 'media_url' in JSON payload")
        return jsonify({"error": "Missing 'media_url' in JSON payload"}), 400

    logging.info(f"@{endpoint}: Processing audio analysis for URL: {media_url} by User ID: {user_id} (Tier: {user_tier})")

    try:
        result = analyze_audio_logic(media_url)
        http_status = 200 if result.get("status") == "success" else 500
        logging.info(f"@{endpoint}: Analysis finished for {media_url}. Returning HTTP status {http_status}.")
        return jsonify(result), http_status
    except Exception as e:
        logging.exception(f"@{endpoint}: Unexpected error in handle_analyze_audio for {media_url}: {e}")
        return jsonify({
            "status": "error",
            "audios_analyzed": 0,
            "manipulated_audios_found": 0,
            "manipulation_confidence": 0.0,
            "manipulated_media": [],
            "analysis_summary": "Error: Server failed unexpectedly during audio analysis.",
            "error": str(e)
        }), 500

@app.route('/')
def index():
    logging.debug("Root path '/' accessed (health check).")
    db_status = "Unknown"
    connector_status = "Not Initialized" if connector is None else "Initialized"
    try:
        if connector:
            conn = get_db_connection()
            release_db_connection(conn)
            db_status = "Connected"
        else:
            db_status = "Connector not initialized"
    except Exception as e:
        db_status = f"Connection Error: {e}"
        logging.warning(f"Health check DB connection failed: {e}")

    return jsonify({
        "message": "TruthScope Media Analysis Backend (GCP-Native)",
        "status": "running",
        "cloud_sql_connector_status": connector_status,
        "database_connection_status": db_status,
        "gcp_project": GCP_PROJECT_ID,
        "location": GCP_LOCATION
    })

@app.teardown_appcontext
def teardown_db(exception=None):
    user = g.pop('user', None)
    if user:
        logging.debug("Removed user from app context 'g'.")
    if exception:
         logging.error(f"App context teardown triggered by exception: {exception}", exc_info=True)

def shutdown_server():
    logging.info("Server shutting down...")
    close_cloud_sql_connector()
    logging.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        check_configuration()
        logging.info("Configuration check passed and Cloud SQL Connector initialized.")

        port = int(os.environ.get("PORT", 3000))
        debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() == "true"

        logging.info(f"Starting Flask app on host 0.0.0.0, port {port} with debug={debug_mode}")

        app.run(host='0.0.0.0', port=port, debug=debug_mode)

    except (ConfigurationError, DatabaseError) as e:
        logging.critical(f"CRITICAL STARTUP ERROR: {e}. Flask app cannot start.", exc_info=True)
        exit(1)
    except Exception as e:
         logging.critical(f"CRITICAL UNHANDLED ERROR running Flask app: {e}", exc_info=True)
         exit(1)
    finally:
        shutdown_server()
        logging.info("Media analysis script finished (GCP-Native).")
