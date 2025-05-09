import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from backend.cosmodb_manager import get_last_n_pairs
import sys
import importlib.util
import re

load_dotenv()

# Dynamically import query_engine.py from data_2_phone/preprocessing
QUERY_ENGINE_PATH = os.path.join(os.path.dirname(__file__), '../data_2_phone/preprocessing/query_engine.py')
spec = importlib.util.spec_from_file_location("query_engine", QUERY_ENGINE_PATH)
query_engine = importlib.util.module_from_spec(spec)
sys.modules["query_engine"] = query_engine
spec.loader.exec_module(query_engine)

# Azure OpenAI config
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
API_VERSION = "2025-03-01-preview"

# Prompt template for summary
DEFAULT_PROMPT = (
    "Given the following conversation history, user query, generated SQL, and SQL answer, "
    "generate a helpful, spoken summary for the user.\n\n"
    "Conversation History:\n{{conversation_history}}\n\n"
    "User Query:\n{{user_query}}\n\n"
    "Generated SQL:\n{{sql}}\n\n"
    "SQL Answer:\n{{answer}}"
)
PROMPT_TEMPLATE = os.getenv("SPOKEN_ANSWER_SUMMARY_GENERATION_PROMPT", DEFAULT_PROMPT)

# Initialize OpenAI client
client = AzureOpenAI(
    api_version=API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
)

def get_summary_response(user_query, session_id):
    """
    1. Use query_engine to get SQL and SQL answer for the user query.
    2. Retrieve last 10 Q&A pairs from CosmosDB.
    3. Build prompt with all context.
    4. Call Azure OpenAI to get summary response.
    5. Return summary response (text).
    """
    # Step 1: Get SQL and SQL answer
    sql, sql_answer = query_engine.get_sql_and_answer(user_query)

    # Step 2: Get last 10 Q&A pairs
    history_pairs = get_last_n_pairs(session_id, n=10)
    history_str = "\n".join([
        f"User: {q['text']}\nAssistant: {a['text']}" for q, a in history_pairs
    ])

    # Step 3: Build prompt using double curly braces
    prompt = PROMPT_TEMPLATE
    prompt = re.sub(r"{{conversation_history}}", history_str, prompt)
    prompt = re.sub(r"{{user_query}}", user_query, prompt)
    prompt = re.sub(r"{{sql}}", sql, prompt)
    prompt = re.sub(r"{{answer}}", sql_answer, prompt)

    # Step 4: Call LLM
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful assistant that summarizes SQL answers for users."},
            {"role": "user", "content": prompt}
        ],
        model=AZURE_OPENAI_DEPLOYMENT_NAME,
        temperature=0.7,
        top_p=1.0
    )
    summary = response.choices[0].message.content
    return summary 