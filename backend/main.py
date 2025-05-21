"""
backend/main.py

This module implements the FastAPI backend for the Conversational AI App. It provides endpoints for:
- Accepting audio uploads from the frontend
- Transcribing audio using Azure OpenAI Whisper
- Generating chat responses using Azure OpenAI
- Synthesizing speech using Azure OpenAI TTS endpoint
- Saving only the last 10 audio and transcription files for traceability

Environment variables are loaded from a .env file. The backend is designed to work with a React frontend and uses CORS for security.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from openai import AzureOpenAI
from dotenv import load_dotenv
import os
import tempfile
import logging
import azure.cognitiveservices.speech as speechsdk
import json
import wave
import io
import requests
from datetime import datetime
import shutil
from data_processing import get_summary_response, conversational_sql_query, correct_transcription_terms, extract_app_name, get_subject, save_subject, get_last_n_pairs, resolve_pronouns
from cosmodb_manager import add_pair, get_last_n_pairs, save_subject, get_subject
import uuid
import subprocess
from app_lookup import lookup_property
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Create temp directory if it doesn't exist
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Azure OpenAI client for chat
try:
    chat_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2023-05-15",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT").rstrip('/')  # Remove trailing slash
    )
    logger.info("Azure OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Azure OpenAI client: {str(e)}")
    raise

# Initialize Speech Config for TTS only
try:
    tts_key = os.getenv("AZURE_OPENAI_TTS_API_KEY")
    if not tts_key:
        raise ValueError("AZURE_OPENAI_TTS_API_KEY is not set in environment variables")
    
    tts_config = speechsdk.SpeechConfig(
        subscription=tts_key,
        region="swedencentral"  # TTS Medical region
    )
    tts_config.speech_synthesis_voice_name = os.getenv("AZURE_OPENAI_TTS_DEPLOYMENT_NAME")
    logger.info("TTS config initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize TTS config: {str(e)}")
    raise

logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)

def save_to_temp(content, prefix, extension):
    """Save content to a file in the temp directory with timestamp and maintain only last 10 files"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.{extension}"
    filepath = os.path.join(TEMP_DIR, filename)
    
    with open(filepath, 'wb' if isinstance(content, bytes) else 'w') as f:
        f.write(content)
    
    # Clean up old files, keeping only the last 10
    pattern = f"{prefix}_*.{extension}"
    files = sorted(
        [f for f in os.listdir(TEMP_DIR) if f.startswith(f"{prefix}_") and f.endswith(f".{extension}")],
        key=lambda x: os.path.getmtime(os.path.join(TEMP_DIR, x)),
        reverse=True
    )
    
    # Remove files beyond the last 10
    for old_file in files[10:]:
        try:
            os.remove(os.path.join(TEMP_DIR, old_file))
            logger.info(f"Removed old file: {old_file}")
        except Exception as e:
            logger.error(f"Error removing old file {old_file}: {str(e)}")
    
    return filepath

PROPERTY_KEYWORDS = ['app id', 'lifecycle state', 'life cycle state', 'status', 'id']
def is_property_phrase(text):
    return any(kw in text.lower() for kw in PROPERTY_KEYWORDS)

def get_last_valid_subject(history_pairs):
    for user, assistant in reversed(history_pairs):
        for msg in [user, assistant]:
            # Always extract string content
            if isinstance(msg, dict) and 'content' in msg:
                candidate_text = msg['content']
            elif isinstance(msg, str):
                candidate_text = msg
            else:
                continue
            if not isinstance(candidate_text, str):
                continue
            candidate = extract_app_name(candidate_text)
            if candidate and not is_property_phrase(candidate) and candidate.lower() not in ['its', 'it', 'their', 'the', 'that', 'this']:
                return candidate
    return None

@app.post("/api/chat")
async def chat(audio: UploadFile = File(...), session_id: str = Form(None)):
    logger.info(f"[DEBUG] Received /api/chat request with session_id: {session_id}")
    try:
        logger.info("Received audio file for processing")
        # Read the uploaded audio file
        content = await audio.read()
        # Save original audio
        original_audio_path = save_to_temp(content, "original_audio", "wav")
        logger.info(f"Saved original audio to: {original_audio_path}")
        # Save the upload exactly as-is
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(content)
            temp_audio_path = tmp.name
        logger.info(f"Saved audio file to: {temp_audio_path}")
        try:
            # Transcribe audio using Azure OpenAI Whisper
            whisper_url = (
                "https://speechsupport.openai.azure.com/openai/deployments/whisper/"
                "audio/transcriptions?api-version=2024-02-15-preview"
            )
            headers = {
                "api-key": os.getenv("AZURE_OPENAI_SPEECH_API_KEY")
            }
            logger.info("Attempting to transcribe audio with Whisper")
            with open(temp_audio_path, 'rb') as audio_file:
                files = {
                    "file": ("audio.wav", audio_file, "audio/wav")
                }
                data = {
                    "model": "whisper",
                    "response_format": "text"
                }
                response = requests.post(
                    whisper_url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=60
                )
            if response.status_code == 200:
                transcription = response.text
                # Apply post-processing correction for domain-specific terms
                transcription = correct_transcription_terms(transcription)
                transcription_path = save_to_temp(transcription, "transcription", "txt")
                logger.info(f"Saved transcription to: {transcription_path}")
                logger.info(f"Transcription successful: {transcription}")
            else:
                logger.error(f"Transcription failed with status {response.status_code}: {response.text}")
                raise Exception(f"Transcription failed: {response.text}")
            # Generate or use provided session_id
            if not session_id:
                session_id = str(uuid.uuid4())
            # Use pronoun-resolved transcription for SQL and summary
            result = conversational_sql_query(session_id, transcription)
            sql = result.get("sql")
            sql_result = result.get("answer")
            sql_status = result.get("status")
            sql_error_type = result.get("error_type")
            sql_message = result.get("message")
            summary_response = get_summary_response(transcription, session_id)
            # 2. Try to extract a new subject from the resolved transcription
            subject = None
            extracted = extract_app_name(transcription)
            # Only update subject if extracted is a valid app name and does NOT contain property keywords
            if (
                extracted
                and not is_property_phrase(extracted)
                and extracted.lower() not in ['its', 'it', 'their', 'the', 'that', 'this']
                and not is_property_phrase(transcription)
            ):
                logger.info(f"[DEBUG] Extracted new subject from resolved transcription: {extracted}")
                subject = extracted
                save_subject(session_id, subject)
            else:
                # Fallback: scan history for last valid app name (not a property phrase)
                subject = get_last_valid_subject(get_last_n_pairs(session_id, n=10))
                logger.info(f"[DEBUG] Fallback to last valid subject from history: {subject}")
            logger.info(f"[DEBUG] FINAL subject for this turn: {subject}")
            # --- PROPERTY LOOKUP LOGIC ---
            property_match = re.search(r"\b(app id|lifecycle state)\b", transcription, re.IGNORECASE)
            if property_match and subject:
                column = property_match.group(1).title()
                column = "App ID" if column.lower() == "app id" else "Lifecycle State"
                try:
                    value = lookup_property(subject, column)
                    summary_response = f"The {subject}'s {column} is {value}."
                    logger.info(f"[DEBUG] Successfully looked up {column} for {subject}: {value}")
                except KeyError as e:
                    summary_response = f"Sorry, I can't find the {column} for '{subject}'."
                    logger.error(f"[DEBUG] Property lookup failed: {e}")
            # TTS via AOAI TTS endpoint (use summary_response)
            tts_url = (
                f"{os.getenv('AZURE_OPENAI_TTS_ENDPOINT').rstrip('/')}"
                f"/openai/deployments/{os.getenv('AZURE_OPENAI_TTS_DEPLOYMENT_NAME')}"
                "/audio/speech?api-version=2024-02-15-preview"
            )
            tts_headers = {
                "api-key": os.getenv("AZURE_OPENAI_TTS_API_KEY"),
                "Content-Type": "application/json",
                "Accept": "audio/wav"
            }
            tts_payload = {
                "model": "tts-1-hd",
                "voice": "alloy",          # or any other supported voice
                "input": summary_response,
                "speed": 1.3               # 0.25-4.0
            }
            tts_response = requests.post(tts_url, headers=tts_headers, json=tts_payload, stream=True, timeout=60)
            tts_response.raise_for_status()
            audio_data = tts_response.content
            tts_audio_path = save_to_temp(audio_data, "tts_response", "wav")

            # Check if the file is PCM WAV, and convert if not
            def is_pcm_wav(filepath):
                try:
                    with wave.open(filepath, 'rb') as wf:
                        return wf.getcomptype() == 'NONE'
                except Exception as e:
                    logger.warning(f"Could not check WAV type: {e}")
                    return False

            if not is_pcm_wav(tts_audio_path):
                logger.info(f"TTS file {tts_audio_path} is not PCM WAV. Converting with ffmpeg...")
                converted_path = tts_audio_path.replace('.wav', '_converted.wav')
                ffmpeg_cmd = [
                    'ffmpeg', '-y', '-i', tts_audio_path,
                    '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', converted_path
                ]
                try:
                    subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    with open(converted_path, 'rb') as f:
                        audio_data = f.read()
                    tts_audio_path = converted_path
                    logger.info(f"TTS file converted to PCM WAV: {converted_path}")
                except Exception as e:
                    logger.error(f"ffmpeg conversion failed: {e}")
                    # fallback: use original audio_data

            # Clean up temporary files
            os.unlink(temp_audio_path)
            logger.info("Cleaned up temporary files")

            return {
                "session_id": session_id,
                "response": summary_response,
                "sql": sql,
                "sql_result": sql_result,
                "sql_status": sql_status,
                "sql_error_type": sql_error_type,
                "sql_message": sql_message,
                "audio": audio_data.hex(),
                "transcription": transcription,
                "files": {
                    "original_audio": original_audio_path,
                    "transcription": transcription_path,
                    "tts_audio": tts_audio_path
                }
            }
        except Exception as e:
            logger.error(f"Error during processing: {str(e)}")
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
            raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/env")
async def get_env():
    """Safely display environment variables (excluding sensitive values)"""
    env_vars = {
        "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT", "Not set"),
        "AZURE_OPENAI_DEPLOYMENT_NAME": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "Not set"),
        "AZURE_OPENAI_SPEECH_API_KEY": "Set" if os.getenv("AZURE_OPENAI_SPEECH_API_KEY") else "Not set",
        "AZURE_OPENAI_TTS_API_KEY": "Set" if os.getenv("AZURE_OPENAI_TTS_API_KEY") else "Not set",
        "AZURE_OPENAI_TTS_DEPLOYMENT_NAME": os.getenv("AZURE_OPENAI_TTS_DEPLOYMENT_NAME", "Not set")
    }
    return env_vars

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 