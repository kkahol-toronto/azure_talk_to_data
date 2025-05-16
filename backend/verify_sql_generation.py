import os
import re
import sqlite3
from data_processing import SQL_QUERY_PROMPT as DEFAULT_SQL_QUERY_PROMPT, format_conversation_history, get_last_n_pairs, client
import importlib.util
import sys
from dotenv import load_dotenv
from cosmodb_manager import add_request_response

# Dynamically import query_engine.py from data_2_phone/preprocessing
QUERY_ENGINE_PATH = os.path.join(os.path.dirname(__file__), '../data_2_phone/preprocessing/query_engine.py')
spec = importlib.util.spec_from_file_location("query_engine", QUERY_ENGINE_PATH)
query_engine = importlib.util.module_from_spec(spec)
sys.modules["query_engine"] = query_engine
spec.loader.exec_module(query_engine)

def get_sql_from_llm(prompt, deployment_name):
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful assistant that generates SQL."},
            {"role": "user", "content": prompt}
        ],
        model=deployment_name,
        temperature=0.0,
        top_p=1.0
    )
    content = response.choices[0].message.content
    # Try to extract SQL from code block
    match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: extract first SELECT statement
    match = re.search(r'(SELECT[\s\S]+?;)', content, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return content.strip()

def main():
    session_id = input("Enter session ID: ").strip()
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    # Get table name, schema, and column descriptions from query_engine
    table_name = query_engine.TABLE_NAME
    schema = ', '.join(query_engine.get_database_schema())
    column_descriptions = str(query_engine.load_column_descriptions())
    db_path = query_engine.DB_FILE

    print(f"Using table: {table_name}")
    print(f"Schema: {schema}")
    print(f"Column descriptions loaded.")
    print(f"Using database file: {db_path}")

    while True:
        nl_query = input("\nEnter your natural language query (or 'quit' to exit): ").strip()
        if nl_query.lower() == "quit":
            break

        # Always reload .env and override before each query
        load_dotenv(override=True)
        sql_query_prompt = os.getenv("SQL_QUERY_PROMPT", DEFAULT_SQL_QUERY_PROMPT)
        print("\n[DEBUG] Loaded SQL_QUERY_PROMPT from .env:\n", sql_query_prompt)

        # Get conversation history
        history_pairs = get_last_n_pairs(session_id, n=10)
        conversation_history = format_conversation_history(history_pairs)

        print("\n--- Conversation History (most recent last) ---\n")
        print(conversation_history if conversation_history else "(No history yet)")
        input("\nPress Enter to see the generated prompt...")

        # Build prompt
        prompt = sql_query_prompt.format(
            table_name=table_name,
            schema=schema,
            column_descriptions=column_descriptions,
            conversation_history=conversation_history,
            nl_query=nl_query
        )
        print("\n--- Generated Prompt ---\n")
        print(prompt)
        input("\nPress Enter to proceed to SQL Generation...")

        print("\n--- LLM SQL Output ---\n")
        sql = get_sql_from_llm(prompt, deployment_name)
        print(sql)
        input("\nPress Enter to execute the SQL query...")

        # Optionally, execute SQL (example for SQLite)
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            print("\n--- SQL Result ---")
            for row in rows:
                print(row)
            conn.close()
        except Exception as e:
            print(f"Error executing SQL: {e}")

        # Store Q&A pair in CosmosDB
        add_request_response(
            session_id,
            {"text": nl_query},
            {"text": sql}
        )

if __name__ == "__main__":
    main() 