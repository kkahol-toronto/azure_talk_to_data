# Conversational AI App

A modern web application enabling natural, voice-based conversation with OpenAI through Azure services. The app features high-quality voice input, accurate transcription, natural language understanding, and AI-powered speech synthesis.

## Features

- Voice-based conversation interface (record, transcribe, and chat)
- Real-time, high-quality audio transcription using Azure OpenAI Whisper
- Natural language processing and chat with Azure OpenAI
- AI-powered speech synthesis using Azure OpenAI TTS endpoint
- Modern, responsive React UI
- Automatic audio playback of AI responses
- Only the last 10 audio and transcription files are retained on the backend
- Clean chat UI (no file paths or debug info shown to users)

## Prerequisites

- Node.js (v14 or later)
- Python 3.8 or later
- Azure account with OpenAI and Speech services enabled

## Setup

1. **Install frontend dependencies:**
   ```bash
   npm install
   ```

2. **Install backend dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   Create a `.env` file in the `backend` directory with the following variables:
   ```
   AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
   AZURE_OPENAI_API_KEY=your_azure_openai_api_key
   AZURE_OPENAI_DEPLOYMENT_NAME=your_chat_deployment_name
   AZURE_OPENAI_SPEECH_API_KEY=your_speech_api_key
   AZURE_OPENAI_TTS_API_KEY=your_tts_api_key
   AZURE_OPENAI_TTS_ENDPOINT=your_tts_endpoint
   AZURE_OPENAI_TTS_DEPLOYMENT_NAME=your_tts_deployment_name
   ```
   - You can find these values in your Azure Portal under the respective resource keys and endpoints.

4. **Start the backend server:**
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

5. **Start the frontend development server:**
   ```bash
   npm start
   ```

## Usage

1. Open the application in your web browser: [http://localhost:3000](http://localhost:3000)
2. Click the "Start Conversation" button and speak into your microphone
3. Click "Stop Conversation" when you're done
4. The AI will transcribe your speech, generate a response, and play it back
5. Only your message and its transcription are shown in the chat (no file paths)

## Architecture

- **Frontend:** React with TypeScript
- **Backend:** FastAPI (Python)
- **Transcription:** Azure OpenAI Whisper
- **Chat:** Azure OpenAI Chat Completions
- **Speech Synthesis:** Azure OpenAI TTS endpoint
- **Audio Processing:** Web Audio API (frontend)

## File Retention Policy

- The backend saves only the last 10 audio and transcription files for debugging and traceability.
- Older files are automatically deleted.
- File paths are not shown in the frontend UI.

## Security

- All API keys and sensitive information are stored in environment variables
- CORS is configured to only allow requests from the frontend

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request 