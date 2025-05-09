# data_2_phone

This module provides tools and scripts for automating phone-based AI interactions and data-driven responses, primarily for Ford's PLM applications. It includes code for making outbound calls, processing and summarizing data, and integrating with Azure OpenAI.

## Main Features

- **Automated Outbound Calls:**  
  `main.py` demonstrates how to initiate a call using the Bland.ai API, with a detailed prompt for the AI assistant (Falcon) to answer project-lifecycle and dashboard questions.
- **Prompt Engineering:**  
  `call_prompt.txt` contains a detailed, structured prompt for the Falcon AI assistant, guiding its conversational style and data usage.
- **Azure OpenAI Integration:**  
  `sample_openai_client.py` shows how to connect to Azure OpenAI and make chat completion requests.
- **Data Preprocessing:**  
  The `preprocessing/` folder contains scripts for:
  - Converting Excel data to SQLite (`excel_to_sqlite.py`)
  - Generating and formatting column summaries with LLMs (`process_excel.py`, `reformat_json.py`)
  - Querying and summarizing data (`query_engine.py`)
- **Utilities:**  
  - `list_files.py` for listing files in a directory.
  - `reformat_json.py` for cleaning and structuring JSON outputs.

## Data

- The `data/` folder contains:
  - Raw and processed data files (Excel, SQLite, JSON, vectorizer, etc.)
  - Example: `PLMDashboardDataFeedFile-03212025.xlsx`, `database.sqlite`, `data.json`

## Usage

1. **Environment Setup:**  
   - Copy `.env.example` to `.env` and fill in your API keys and endpoints.
   - Install dependencies (see below).

2. **Run a Call Example:**  
   - Edit `main.py` with your API key and desired phone number.
   - Run:  
     ```bash
     python main.py
     ```

3. **OpenAI Client Example:**  
   - Edit `sample_openai_client.py` with your Azure OpenAI credentials.
   - Run:  
     ```bash
     python sample_openai_client.py
     ```

4. **Data Preprocessing:**  
   - Use scripts in `preprocessing/` to process Excel data, generate summaries, and prepare data for querying.

## Dependencies

- Python 3.8+
- `requests`
- `python-dotenv`
- `openai`
- `pandas` (for Excel processing)
- `azure-openai` (for Azure LLM integration)

Install with:
```bash
pip install -r requirements.txt
```
*(Create this file as needed with the above packages.)*

## Folder Structure

```
data_2_phone/
├── main.py
├── sample_openai_client.py
├── reformat_json.py
├── list_files.py
├── call_prompt.txt
├── data/
└── preprocessing/
```

## Notes

- Prompts and data are tailored for Ford PLM dashboard use cases, but the structure is adaptable.
- See each script for more details and usage instructions. 