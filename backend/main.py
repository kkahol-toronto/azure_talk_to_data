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

from fastapi import FastAPI, UploadFile, File, HTTPException
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
from backend.data_processing import get_summary_response
from backend.cosmodb_manager import add_request_response
import uuid

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

@app.post("/api/chat")
async def chat(audio: UploadFile = File(...), session_id: str = None):
    """Accepts an audio file, transcribes it, generates a summary response, and returns TTS audio."""
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
                transcription_path = save_to_temp(transcription, "transcription", "txt")
                logger.info(f"Saved transcription to: {transcription_path}")
                logger.info(f"Transcription successful: {transcription}")
            else:
                logger.error(f"Transcription failed with status {response.status_code}: {response.text}")
                raise Exception(f"Transcription failed: {response.text}")
            # Generate or use provided session_id
            if not session_id:
                session_id = str(uuid.uuid4())
            # Get summary response from data_processing
            summary_response = get_summary_response(transcription, session_id)
            # Store request/response in CosmosDB
            add_request_response(session_id, transcription, summary_response)
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
                "voice": "fable",
                "input": summary_response
            }
            tts_response = requests.post(tts_url, headers=tts_headers, json=tts_payload, stream=True, timeout=60)
            tts_response.raise_for_status()
            audio_data = tts_response.content
            tts_audio_path = save_to_temp(audio_data, "tts_response", "wav")
            # Clean up temporary files
            os.unlink(temp_audio_path)
            logger.info("Cleaned up temporary files")
            return {
                "session_id": session_id,
                "response": summary_response,
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