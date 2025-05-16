import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from cosmodb_manager import get_last_n_pairs, add_request_response
import sys
import importlib.util
import re

load_dotenv()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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

MAX_PROMPT_TOKENS = 1_000_000

# New SQL query prompt with conversation history
SQL_QUERY_PROMPT = '''
You are an AI assistant that translates natural-language questions into SQL queries.
-- DATABASE INFORMATION --
- Table name: {table_name}
- Schema: {schema}
-- COLUMN DESCRIPTIONS (with example values) --
{column_descriptions}
-- CONVERSATION HISTORY (most-recent first) --
{conversation_history}
-- CURRENT USER QUERY --
{nl_query}
IMPORTANT: Use the exact column names and example values as shown above when generating SQL. If the user refers to a value that is similar to, but not exactly, an example value, map it to the closest valid value. Return only the SQL, inside a fenced code block: sql SELECT ... Do not include explanations, comments, or any text outside the SQL block.
'''

def estimate_tokens(text):
    return len(text) // 4

# Initialize OpenAI client
client = AzureOpenAI(
    api_version=API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
)

# Helper to format conversation history
def format_conversation_history(history_pairs):
    # Most recent first
    lines = []
    for user, assistant in reversed(history_pairs[-10:]):
        lines.append(f"User: {user['text']}")
        lines.append(f"Assistant: {assistant['text']}")
    return '\n'.join(lines)

def correct_transcription_terms(transcription: str) -> str:
    """
    Correct common mis-transcriptions for domain-specific terms and acronyms.
    Extend this mapping as needed for your use case.
    """
    corrections = {
        "iset": "isit",
        "icit": "isit",
        "i s i t": "isit",
        "i set": "isit",
        # Add more mappings as needed
    }
    for wrong, right in corrections.items():
        # Replace case-insensitively
        transcription = re.sub(rf"\\b{wrong}\\b", right, transcription, flags=re.IGNORECASE)
    return transcription

def correct_sql_terms(sql: str) -> str:
    """
    Correct common mis-transcriptions in SQL values (e.g., 'iset', 'icit' to 'isit').
    Uses the same mapping as correct_transcription_terms.
    """
    corrections = {
        "iset": "isit",
        "icit": "isit",
        "i s i t": "isit",
        "i set": "isit",
        # Add more mappings as needed
    }
    for wrong, right in corrections.items():
        sql = re.sub(rf"'\s*{wrong}\s*'", f"'{right}'", sql, flags=re.IGNORECASE)
    return sql

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

    # Step 3: Always reload .env and fetch prompt template
    load_dotenv(override=True)
    prompt_template = os.getenv("SPOKEN_ANSWER_SUMMARY_GENERATION_PROMPT", DEFAULT_PROMPT)
    # Use str.format for prompt substitution to avoid regex escape issues
    prompt = prompt_template.format(
        conversation_history=history_str,
        user_query=user_query,
        sql=sql,
        answer=sql_answer
    )

    if estimate_tokens(prompt) > MAX_PROMPT_TOKENS:
        # Remove conversation history
        prompt = prompt_template.format(
            conversation_history="",
            user_query=user_query,
            sql=sql,
            answer=sql_answer
        )
    if estimate_tokens(prompt) > MAX_PROMPT_TOKENS:
        # Truncate SQL answer if still too long
        allowed_answer_len = MAX_PROMPT_TOKENS * 4 - len(prompt_template.format(
            conversation_history="",
            user_query=user_query,
            sql=sql,
            answer=""
        ))
        truncated_answer = sql_answer[:allowed_answer_len]
        prompt = prompt_template.format(
            conversation_history="",
            user_query=user_query,
            sql=sql,
            answer=truncated_answer
        )

    # Write the final prompt to a file for debugging
    prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)

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

def get_sql_from_llm(prompt, deployment_name):
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful assistant that generates SQL for SQLITE."},
            {"role": "user", "content": prompt}
        ],
        model=deployment_name,
        temperature=1.0,
        top_p=1.0
    )
    content = response.choices[0].message.content

    content = re.sub(r"(?im)^\s*sql\s*\n?", "", content)
    # Normalize whitespace and line endings
    content = content.replace('\xa0', ' ').replace('\r\n', '\n').replace('\r', '\n')
    content = content.strip()
    print("[DEBUG] Content before SQL extraction:", repr(content))

    # Updated regex: allow for optional whitespace before SQL_START
    match = re.search(r"\s*SQL_START\s*(.*?)\s*SQL_END", content, re.DOTALL | re.IGNORECASE)
    if match:
        print("[DEBUG] Extracted SQL from SQL_START ... SQL_END")
        return match.group(1).strip()

    match = re.search(r"<SQL>\s*(.*?)\s*</SQL>", content, re.DOTALL | re.IGNORECASE)
    if match:
        print("[DEBUG] Extracted SQL from <SQL> ... </SQL>")
        return match.group(1).strip()

    match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if match:
        print("[DEBUG] Extracted SQL from code block")
        return match.group(1).strip()

    match = re.search(r'(SELECT[\s\S]+?;)', content, re.IGNORECASE)
    if match:
        print("[DEBUG] Extracted SQL from SELECT fallback")
        return match.group(1).strip()
    match = re.search(r'(SELECT[\s\S]+)', content, re.IGNORECASE)
    if match:
        print("[DEBUG] Extracted SQL from SELECT fallback (no semicolon)")
        return match.group(1).strip()

    print("[DEBUG] No SQL extracted, returning raw content")
    return content.strip()

def conversational_sql_query(session_id, nl_query):
    """
    Conversational SQL query flow using history, matching verify_sql_generation.py logic.
    Returns a structured result dict with status, error_type, message, sql, and answer fields.
    """
    print("[DEBUG] Conversational SQL query started")
    from dotenv import load_dotenv
    load_dotenv(override=True)
    sql_query_prompt = os.getenv("SQL_QUERY_PROMPT", SQL_QUERY_PROMPT)
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    # Get table name, schema, and column descriptions from query_engine
    table_name = query_engine.TABLE_NAME
    schema = ', '.join(query_engine.get_database_schema()).replace('{', '{{').replace('}', '}}')
    # Load column descriptions and append example values for key columns
    column_descriptions_dict = query_engine.load_column_descriptions()
    # Example: Add example values for App_Acronym if not present
    if isinstance(column_descriptions_dict, dict):
        if 'App_Acronym' in column_descriptions_dict and 'Example values' not in column_descriptions_dict['App_Acronym']:
            column_descriptions_dict['App_Acronym'] += ' Example values: ISIT, COTS, ...'
        column_descriptions = '\n'.join(f"{k}: {v}" for k, v in column_descriptions_dict.items())
    else:
        column_descriptions = str(column_descriptions_dict)
    column_descriptions = column_descriptions.replace('{', '{{').replace('}', '}}')
    db_path = query_engine.DB_FILE

    # Get conversation history
    history_pairs = get_last_n_pairs(session_id, n=10)
    conversation_history = format_conversation_history(history_pairs)

    # Apply correction to the user query before LLM prompt
    nl_query = correct_transcription_terms(nl_query)

    # Debug prints
    print("[DEBUG] Loaded SQL_QUERY_PROMPT:\n", sql_query_prompt)
    print("[DEBUG] Format keys:", {
        "table_name": table_name,
        "schema": schema,
        "column_descriptions": column_descriptions,
        "conversation_history": conversation_history,
        "nl_query": nl_query
    })

    # Build prompt
    prompt = sql_query_prompt.format(
        table_name=table_name,
        schema=schema,
        column_descriptions=column_descriptions,
        conversation_history=conversation_history,
        nl_query=nl_query
    )

    # Call LLM to get SQL
    sql = get_sql_from_llm(prompt, deployment_name)
    print("[DEBUG] SQL to execute (pre-correction):", repr(sql))

    # Post-process SQL to correct values
    sql = correct_sql_terms(sql)
    print("[DEBUG] SQL to execute (post-correction):", repr(sql))

    # Check for empty or None SQL
    if not sql or not sql.strip():
        print("[DEBUG] Extracted SQL is empty or None.")
        return {
            "status": "error",
            "error_type": "no_sql_extracted",
            "message": "Error: No SQL query could be extracted from the LLM response.",
            "sql": sql,
            "answer": None
        }

    # Execute SQL and get result
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        print("[DEBUG] SQL execution result:", rows)
        conn.close()
        if rows:
            # Store Q&A pair in CosmosDB
            add_request_response(
                session_id,
                {"text": nl_query},
                {"text": sql}
            )
            return {
                "status": "success",
                "sql": sql,
                "answer": rows
            }
        else:
            print("[DEBUG] SQL executed but returned no results.")
            return {
                "status": "error",
                "error_type": "no_results",
                "message": "Error: SQL executed but returned no results.",
                "sql": sql,
                "answer": None
            }
    except Exception as e:
        print("[DEBUG] SQL execution error:", e)
        return {
            "status": "error",
            "error_type": "sql_execution",
            "message": f"Error executing SQL: {e}",
            "sql": sql,
            "answer": None
        } 