# Conversational AI App

This project is a full-stack Conversational AI application that allows users to interact with a natural language interface, which translates queries into SQL, executes them on a database, and returns both text and synthesized speech responses. The backend is built with FastAPI (Python), and the frontend is a React app. The backend leverages Azure OpenAI for LLM, Whisper, and TTS services, but is designed to be cloud-agnostic and is deployable on Google Cloud Run.

---

## Directory Structure

```
/ (project root)
├── backend/
│   ├── main.py                # FastAPI backend
│   ├── data_processing.py     # SQL, LLM, and TTS logic
│   ├── cosmodb_manager.py     # CosmosDB history management
│   ├── requirements.txt       # Python dependencies
│   └── ...
├── data_2_phone/
│   └── preprocessing/
│       └── query_engine.py    # SQL query engine
├── frontend/
│   ├── src/                   # React app source
│   ├── public/
│   ├── package.json
│   └── ...
├── Dockerfile.backend         # Dockerfile for FastAPI backend
├── Dockerfile.frontend        # Dockerfile for React frontend
├── README.md                  # This file
└── ...
```

---

## Backend (FastAPI)
- **Language:** Python 3.11
- **Key dependencies:** FastAPI, Uvicorn, Azure OpenAI, Azure Cognitive Services Speech, CosmosDB, ffmpeg
- **Entrypoint:** `backend/main.py`
- **Container port:** 8080 (required by Cloud Run)

## Frontend (React)
- **Language:** JavaScript/TypeScript (React)
- **Build:** Static files served by Nginx
- **Container port:** 80

---

## Prerequisites
- Docker
- Node.js (for local frontend development)
- Python 3.11 (for local backend development)
- Azure OpenAI and Cognitive Services credentials
- (Optional) GCP account and gcloud CLI for deployment

---

## Environment Variables
Create a `.env` file in the `backend/` directory with the following (example values):

```
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_ENDPOINT=https://your-azure-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=your-azure-deployment-name
AZURE_OPENAI_SPEECH_API_KEY=your-azure-speech-api-key
AZURE_OPENAI_TTS_API_KEY=your-azure-tts-api-key
AZURE_OPENAI_TTS_DEPLOYMENT_NAME=your-tts-deployment-name
AZURE_OPENAI_TTS_ENDPOINT=https://your-azure-tts-endpoint.cognitiveservices.azure.com/
# Add any CosmosDB or database connection variables as needed
```

---

## Local Development

### Backend
```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### Frontend
```bash
cd frontend
npm install
npm start
```

---

## Building Docker Images

### Backend
```bash
docker build -f Dockerfile.backend -t conversationalai-backend .
```

### Frontend
```bash
docker build -f Dockerfile.frontend -t conversationalai-frontend ./frontend
```

---

## Deploying to Google Cloud Run

### 1. **Backend**
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/conversationalai-backend .
gcloud run deploy conversationalai-backend \
  --image gcr.io/YOUR_PROJECT_ID/conversationalai-backend \
  --platform managed \
  --region YOUR_REGION \
  --allow-unauthenticated \
  --set-env-vars AZURE_OPENAI_API_KEY=...,... # (repeat for all required env vars)
```

### 2. **Frontend**
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/conversationalai-frontend ./frontend
gcloud run deploy conversationalai-frontend \
  --image gcr.io/YOUR_PROJECT_ID/conversationalai-frontend \
  --platform managed \
  --region YOUR_REGION \
  --allow-unauthenticated
```

- You can also deploy the frontend as a static site to GCP Cloud Storage or Firebase Hosting if preferred.
- Update your frontend `.env` or config to point API calls to the backend Cloud Run URL.

---

## Example API Usage

**POST /api/chat**
- Uploads an audio file, returns transcription, SQL, answer, and TTS audio.

```bash
curl -X POST \
  -F "audio=@/path/to/audio.wav" \
  -F "session_id=your-session-id" \
  https://YOUR_BACKEND_CLOUD_RUN_URL/api/chat
```

**GET /api/env**
- Returns non-sensitive environment variable info for debugging.

---

## Notes
- The backend relies on Azure OpenAI and Cognitive Services for LLM, Whisper, and TTS. Ensure your Azure credentials are valid and accessible from GCP.
- The backend expects a SQLite database and CosmosDB for conversation history. Update connection strings as needed.
- Cloud Run requires your app to listen on port 8080 (backend) or 80 (frontend).
- For production, secure your endpoints and API keys appropriately.

---

## Contact & Support
For questions, issues, or contributions, please contact the project maintainer or open an issue in the repository. 