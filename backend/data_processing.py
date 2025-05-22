import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from cosmodb_manager import get_last_n_pairs, add_request_response, add_interaction, get_session
import sys
import importlib.util
import re
from prompt import SQL_QUERY_PROMPT, SPOKEN_ANSWER_SUMMARY_GENERATION_PROMPT

load_dotenv()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Dynamically import query_engine.py from backend/data_2_phone/preprocessing
QUERY_ENGINE_PATH = os.path.join(os.path.dirname(__file__), 'data_2_phone/preprocessing/query_engine.py')
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
        # Handle new response structure: dict with 'sql' and 'spoken'
        if isinstance(assistant['text'], dict):
            if 'sql' in assistant['text']:
                lines.append(f"Assistant (SQL): {assistant['text']['sql']}")
            if 'spoken' in assistant['text']:
                lines.append(f"Assistant (spoken): {assistant['text']['spoken']}")
        else:
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

def get_summary_response(user_query, session_id, sql, sql_answer):
    last_user_query = ''
    last_assistant_answer = ''
    last_sql_where_clause = ''
    """
    1. Use the provided SQL and SQL answer for the user query.
    2. Retrieve last 10 Q&A pairs from CosmosDB.
    3. Build prompt with all context.
    4. Call Azure OpenAI to get summary response.
    5. Return summary response (text).
    """
    # Step 2: Get last 10 Q&A pairs
    history_pairs = get_last_n_pairs(session_id, n=10)
    if history_pairs:
        last_user_query = history_pairs[-1][0]['text']['text']
        last_assistant_answer = history_pairs[-1][1]['text'].get('spoken', '')
        last_sql = history_pairs[-1][1]['text'].get('sql', '')
        import re
        match = re.search(r'WHERE\s+(.*?)(?:\s+GROUP BY|\s+ORDER BY|\s+LIMIT|;|$)', last_sql, re.IGNORECASE | re.DOTALL)
        if match:
            last_sql_where_clause = match.group(1).strip()
    history_str = "\n".join([
        f"User: {q['text']}\nAssistant: {a['text']}" for q, a in history_pairs
    ])

    # Step 3: Always reload .env and fetch prompt template
    load_dotenv(override=True)
    prompt_template = SPOKEN_ANSWER_SUMMARY_GENERATION_PROMPT
    # Use str.format for prompt substitution to avoid regex escape issues
    prompt = prompt_template.format(
        conversation_history=history_str,
        user_query=user_query,
        sql=sql,
        answer=sql_answer,
        last_user_query=last_user_query,
        last_assistant_answer=last_assistant_answer,
        last_sql_where_clause=last_sql_where_clause
    )

    if estimate_tokens(prompt) > MAX_PROMPT_TOKENS:
        # Remove conversation history
        prompt = prompt_template.format(
            conversation_history="",
            user_query=user_query,
            sql=sql,
            answer=sql_answer,
            last_user_query=last_user_query,
            last_assistant_answer=last_assistant_answer,
            last_sql_where_clause=last_sql_where_clause
        )
    if estimate_tokens(prompt) > MAX_PROMPT_TOKENS:
        # Truncate SQL answer if still too long
        allowed_answer_len = MAX_PROMPT_TOKENS * 4 - len(prompt_template.format(
            conversation_history="",
            user_query=user_query,
            sql=sql,
            answer="",
            last_user_query=last_user_query,
            last_assistant_answer=last_assistant_answer,
            last_sql_where_clause=last_sql_where_clause
        ))
        truncated_answer = sql_answer[:allowed_answer_len]
        prompt = prompt_template.format(
            conversation_history="",
            user_query=user_query,
            sql=sql,
            answer=truncated_answer,
            last_user_query=last_user_query,
            last_assistant_answer=last_assistant_answer,
            last_sql_where_clause=last_sql_where_clause
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

    # normalize spaces & line-endings
    content = (
        content
        .replace('\xa0', ' ')
        .replace('\r\n', '\n')
        .replace('\r',   '\n')
        .strip()
    )
    print("[DEBUG] Before stripping markers:", repr(content))

    # strip ANY of these: SQL_START, _START, SQL_END, END (case-insensitive)
    content = re.sub(r'^(?:SQL_START|_START)\s*',     '', content, flags=re.IGNORECASE)
    content = re.sub(r'\s*(?:SQL_END|END)\s*$',       '', content, flags=re.IGNORECASE)

    print("[DEBUG] After stripping markers:", repr(content))
    return content

def format_conversation_history_from_interactions(interactions, n=5):
    """
    Format the last n interactions for the LLM prompt, most recent first.
    Each interaction is formatted as:
      Here was the query: {USER_REQUEST}
      The LLM responded with the following query: {LLM_SQL_RESPONSE}
      The query was executed on DB and gave: {SQL_DB_RESPONSE}
      This led to the following Summary Request: {SUMMARY_REQUEST}
      And this was the Summary Response read out: {SUMMARY_RESPONSE}
    Each interaction is separated by a blank line.
    """
    lines = []
    for interaction in reversed(interactions[-n:]):
        lines.append(
            f"Here was the query: {interaction.get('USER_REQUEST', '')}\n"
            f"The LLM responded with the following query: {interaction.get('LLM_SQL_RESPONSE', '')}\n"
            f"The query was executed on DB and gave: {interaction.get('SQL_DB_RESPONSE', '')}\n"
            f"This led to the following Summary Request: {interaction.get('SUMMARY_REQUEST', '')}\n"
            f"And this was the Summary Response read out: {interaction.get('SUMMARY_RESPONSE', '')}"
        )
    return "\n\n".join(lines)

def conversational_sql_query(session_id, nl_query):
    last_user_query = ''
    last_assistant_answer = ''
    last_sql_where_clause = ''
    print(f"[DEBUG] conversational_sql_query called with session_id: {session_id}")
    print("[DEBUG] Conversational SQL query started")
    from dotenv import load_dotenv
    load_dotenv(override=True)
    sql_query_prompt = SQL_QUERY_PROMPT
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    # Get table name, schema, and column descriptions from query_engine
    table_name = query_engine.TABLE_NAME
    schema = ', '.join(query_engine.get_database_schema()).replace('{', '{{').replace('}', '}}')
    column_descriptions_dict = query_engine.load_column_descriptions()
    if isinstance(column_descriptions_dict, dict):
        if 'App_Acronym' in column_descriptions_dict and 'Example values' not in column_descriptions_dict['App_Acronym']:
            column_descriptions_dict['App_Acronym'] += ' Example values: ISIT, COTS, ...'
        column_descriptions = '\n'.join(f"{k}: {v}" for k, v in column_descriptions_dict.items())
    else:
        column_descriptions = str(column_descriptions_dict)
    column_descriptions = column_descriptions.replace('{', '{{').replace('}', '}}')
    db_path = query_engine.DB_FILE

    # Fetch the session document and interactions
    session = get_session(session_id)
    interactions = session.get('interactions', []) if session else []
    conversation_history = format_conversation_history_from_interactions(interactions, n=5)

    # Apply correction to the user query before LLM prompt
    nl_query = correct_transcription_terms(nl_query)

    # Build the SQL generation prompt
    prompt = sql_query_prompt.format(
        table_name=table_name,
        schema=schema,
        column_descriptions=column_descriptions,
        conversation_history=conversation_history,
        last_user_query=last_user_query,
        last_assistant_answer=last_assistant_answer,
        last_sql_where_clause=last_sql_where_clause,
        nl_query=nl_query
    )

    # Call LLM to get SQL
    sql = get_sql_from_llm(prompt, deployment_name)
    print("[DEBUG] SQL to execute (pre-correction):", repr(sql))
    sql = correct_sql_terms(sql)
    print("[DEBUG] SQL to execute (post-correction):", repr(sql))

    # Execute SQL and get result
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        print("[DEBUG] SQL execution result:", rows)
        conn.close()
        sql_db_response = str(rows)
        print("[DEBUG] Converting SQL response to string:", repr(sql_db_response))
        
        # Build the summary prompt (as a string)
        print("[DEBUG] Building summary prompt...")
        summary_prompt = SPOKEN_ANSWER_SUMMARY_GENERATION_PROMPT.format(
            conversation_history=conversation_history,
            user_query=nl_query,
            sql=sql,
            answer=sql_db_response,
            last_user_query=last_user_query,
            last_assistant_answer=last_assistant_answer,
            last_sql_where_clause=last_sql_where_clause
        )
        print("[DEBUG] Summary prompt built successfully")
        
        # Generate spoken summary
        print("[DEBUG] Generating summary response...")
        summary_response = get_summary_response(nl_query, session_id, sql, sql_db_response)
        print("[DEBUG] Summary response generated:", repr(summary_response))
        
        # Store the full interaction in CosmosDB
        print("[DEBUG] Storing interaction in CosmosDB...")
        add_interaction(
            session_id,
            user_request=nl_query,
            llm_sql_response=sql,
            sql_db_response=sql_db_response,
            summary_request=summary_prompt,
            summary_response=summary_response
        )
        print("[DEBUG] Interaction stored successfully")
        
        if rows:
            return {
                "status": "success",
                "sql": sql,
                "answer": rows,
                "spoken": summary_response
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
        # Build the summary prompt (as a string)
        summary_prompt = SPOKEN_ANSWER_SUMMARY_GENERATION_PROMPT.format(
            conversation_history=conversation_history,
            user_query=nl_query,
            sql=sql,
            answer=f"Error executing SQL: {e}",
            last_user_query=last_user_query,
            last_assistant_answer=last_assistant_answer,
            last_sql_where_clause=last_sql_where_clause
        )
        summary_response = get_summary_response(nl_query, session_id, sql, f"Error executing SQL: {e}")
        add_interaction(
            session_id,
            user_request=nl_query,
            llm_sql_response=sql,
            sql_db_response=f"Error executing SQL: {e}",
            summary_request=summary_prompt,
            summary_response=summary_response
        )
        return {
            "status": "error",
            "error_type": "sql_execution",
            "message": f"Error executing SQL: {e}",
            "sql": sql,
            "answer": None
        } 