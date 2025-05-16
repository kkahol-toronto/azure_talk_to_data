import os
import json
import glob
import sqlite3
import re
from dotenv import load_dotenv
from data_2_phone.preprocessing.process_excel import call_llm

# Load environment variables
load_dotenv()

# Constants
DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "database.sqlite"))
TABLE_NAME = "applications"

def load_column_descriptions(max_tokens=900000):
    """Load column descriptions from formatted output, optionally filtering to stay under token limit."""
    descriptions_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "column_summaries", 
        "formatted_output"
    )
    
    descriptions = {}
    total_tokens = 0
    token_exceeded = False
    
    # Load all JSON files from the formatted output directory
    json_files = glob.glob(os.path.join(descriptions_path, "*.json"))
    
    for file_path in json_files:
        with open(file_path, 'r') as f:
            try:
                data = json.load(f)
                column_name = data.get('name', os.path.basename(file_path).replace('.json', ''))
                
                # Create a compact description without histograms if we're approaching token limit
                description = {
                    "name": column_name,
                    "purpose": data.get('Purpose', ''),
                    "unique_values": data.get('Unique Values', '')
                }
                
                # Only include full data if we're not close to the token limit
                if not token_exceeded:
                    description["histogram"] = data.get('Histogram', '')
                    description["insights"] = data.get('Insights', '')
                
                # Estimate tokens (rough approximation: 1 token ~= 4 chars)
                description_str = json.dumps(description)
                est_tokens = len(description_str) // 4
                total_tokens += est_tokens
                
                # If we're getting close to the limit, skip histograms for future entries
                if total_tokens > max_tokens * 0.8:
                    token_exceeded = True
                
                descriptions[column_name] = description
                
            except json.JSONDecodeError:
                print(f"Error loading {file_path}")
    
    print(f"Loaded {len(descriptions)} column descriptions. Estimated tokens: {total_tokens}")
    return descriptions

def get_database_schema():
    """Get the schema of the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
    schema = cursor.fetchall()
    conn.close()
    
    # Format schema information
    schema_info = []
    for col in schema:
        col_id, col_name, col_type, not_null, default_value, is_pk = col
        schema_info.append(f"{col_name} ({col_type})")
    
    return schema_info

def execute_query(query):
    """Execute the SQL query against the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute(query)
        columns = [description[0] for description in cursor.description]
        results = cursor.fetchall()
        
        # Format results as a list of dictionaries
        formatted_results = [dict(zip(columns, row)) for row in results]
        return {"success": True, "results": formatted_results, "count": len(formatted_results)}
    
    except Exception as e:
        return {"success": False, "results": None, "error": str(e)}
    
    finally:
        conn.close()

def process_natural_language_query(nl_query):
    """Process a natural language query and return the results."""
    # Load column descriptions
    column_descriptions = load_column_descriptions()
    
    # Get database schema
    schema_info = get_database_schema()
    
    # Get environmental variable containing the prompt template
    sql_query_prompt = os.getenv("SQL_QUERY_PROMPT")
    
    # Fill the prompt template with our data
    prompt = sql_query_prompt.format(
        nl_query=nl_query,
        table_name=TABLE_NAME,
        schema=", ".join(schema_info),
        column_descriptions=json.dumps(column_descriptions, indent=2)
    )
    
    # Call the LLM
    response = call_llm(prompt)
    
    # Extract SQL query from the response
    sql_match = re.search(r"```sql\n(.*?)\n```", response, re.DOTALL)
    if sql_match:
        sql_query = sql_match.group(1)
        # Execute the SQL query
        results = execute_query(sql_query)
        return {
            "query": nl_query,
            "sql": sql_query,
            "results": results
        }
    else:
        return {
            "query": nl_query,
            "error": "Could not extract SQL query from LLM response",
            "full_response": response
        }

def get_sql_and_answer(nl_query):
    print("[DEBUG] >>> ENTERED get_sql_and_answer (query_engine.py)")
    result = process_natural_language_query(nl_query)
    sql_query = None
    def clean_sql(sql):
        sql = sql.strip()
        sql = re.sub(r'(_END|SQL_END)\s*$', '', sql, flags=re.IGNORECASE).strip()
        return sql
    if 'full_response' in result:
        import re
        content = result['full_response']
        content = re.sub(r"(?im)^\s*sql\s*\n?", "", content)
        content = content.replace('\xa0', ' ').replace('\r\n', '\n').replace('\r', '\n')
        content = content.strip()
        print("[DEBUG] Content before SQL extraction (query_engine):", repr(content))
        match = re.search(r"\s*SQL_START\s*(.*?)\s*SQL_END", content, re.DOTALL | re.IGNORECASE)
        if match:
            sql_query = clean_sql(match.group(1))
            print("[DEBUG] Extracted SQL from SQL_START ... SQL_END (query_engine):", sql_query)
        else:
            match = re.search(r"<SQL>\s*(.*?)\s*</SQL>", content, re.DOTALL | re.IGNORECASE)
            if match:
                sql_query = clean_sql(match.group(1))
                print("[DEBUG] Extracted SQL from <SQL> ... </SQL> (query_engine):", sql_query)
            else:
                match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
                if match:
                    sql_query = clean_sql(match.group(1))
                    print("[DEBUG] Extracted SQL from code block (query_engine):", sql_query)
                else:
                    match = re.search(r"(SELECT[\s\S]+?;)", content, re.IGNORECASE)
                    if match:
                        sql_query = clean_sql(match.group(1))
                        print("[DEBUG] Extracted SQL from SELECT fallback (query_engine):", sql_query)
                    else:
                        match = re.search(r"(SELECT[\s\S]+)", content, re.IGNORECASE)
                        if match:
                            sql_query = clean_sql(match.group(1))
                            print("[DEBUG] Extracted SQL from SELECT fallback (no semicolon, query_engine):", sql_query)
                        else:
                            print("[DEBUG] Could not extract SQL from LLM response. (query_engine)")
                            sql_query = ""
    elif 'sql' in result:
        print("[DEBUG] Extraction path: 'sql' in result")
        sql_query = clean_sql(result['sql'])
    else:
        print("[DEBUG] Extraction path: no sql or full_response in result")
        sql_query = ""
    print("[DEBUG] SQL Query (from get_sql_and_answer):\n", sql_query)

    if not sql_query or not sql_query.strip():
        print("[DEBUG] No SQL query extracted. Returning error from get_sql_and_answer.")
        return "", "Error: No SQL query could be extracted from the LLM response."

    results = execute_query(sql_query)

    if results and results.get('success'):
        if results['results']:
            sql_answer = json.dumps(results['results'], indent=2)
            print("[DEBUG] Generated SQL Query:\n", sql_query)
            print("[DEBUG] SQL Answer/Response:\n", sql_answer)
            print("[DEBUG] Returning successful SQL and answer from get_sql_and_answer.")
            return sql_query, sql_answer
        else:
            print("[DEBUG] SQL executed but returned no results. Returning from get_sql_and_answer.")
            return sql_query, "Error: SQL executed but returned no results."
    else:
        print("[DEBUG] SQL generation or execution failed. Returning from get_sql_and_answer:", results.get('error', 'Unknown error') if results else 'No results')
        return sql_query or "", f"Error: {results.get('error', 'Unknown error') if results else 'No results'}"

if __name__ == "__main__":
    # Check if database exists, if not suggest running excel_to_sqlite.py first
    if not os.path.exists(DB_FILE):
        print(f"Database file not found: {DB_FILE}")
        print("Please run 'python preprocessing/excel_to_sqlite.py' first to create the database.")
        exit(1)
        
    # Sample queries to demonstrate the system
    sample_queries = [
        "Tell me for ISIT COTS apps, how many of them have Oracle database",
        "Which department has the most applications?",
        "give me Infra. Decommission Status histogram",
        "Show me applications developed in the last 5 years that are using Java technology"
    ]
    
    # Let user choose a query or enter their own
    print("\nNatural Language to SQL Query Engine")
    print("------------------------------------")
    print("Sample queries:")
    for i, query in enumerate(sample_queries):
        print(f"{i+1}. {query}")
    print("0. Enter your own query")
    
    choice = input("\nSelect a query (0-4): ")
    
    if choice == "0":
        user_query = input("Enter your query: ")
    else:
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(sample_queries):
                user_query = sample_queries[choice_idx]
            else:
                user_query = input("Invalid choice. Enter your query: ")
        except ValueError:
            user_query = input("Invalid choice. Enter your query: ")
    
    print(f"\nProcessing query: {user_query}")
    result = process_natural_language_query(user_query)
    
    if "error" in result:
        print(f"Error: {result['error']}")
        if "full_response" in result:
            print("\nLLM Full Response:")
            print(result["full_response"])
    else:
        print("\nGenerated SQL Query:")
        print(result["sql"])
        
        print("\nQuery Results:")
        if result["results"]["success"]:
            print(f"Found {result['results']['count']} results")
            for i, row in enumerate(result["results"]["results"]):
                if i < 10:  # Limit to first 10 results for readability
                    print(row)
                elif i == 10:
                    print("... (more results available)")
        else:
            print(f"Query execution failed: {result['results']['error']}")
