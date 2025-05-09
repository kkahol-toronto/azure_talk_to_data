import os
import pandas as pd
import sqlite3
from pathlib import Path

# File paths
EXCEL_FILE = "data_2_phone/data/PLMDashboardDataFeedFile-03212025.xlsx"
DB_FILE = "data_2_phone/data/database.sqlite"
TABLE_NAME = "applications"

def excel_to_sqlite():
    """Convert Excel file to SQLite database."""
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    print(f"Reading Excel file: {EXCEL_FILE}")
    # Read the Excel file
    df = pd.read_excel(EXCEL_FILE)
    
    # Clean column names for SQL (remove special characters, spaces)
    df.columns = [col.replace(" ", "_").replace("-", "_").replace(".", "_") for col in df.columns]
    
    print(f"Creating SQLite database: {DB_FILE}")
    # Connect to SQLite database (creates file if it doesn't exist)
    conn = sqlite3.connect(DB_FILE)
    
    # Write DataFrame to SQLite
    print(f"Writing data to table: {TABLE_NAME}")
    df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
    
    # Get and print table info
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
    columns = cursor.fetchall()
    
    print(f"\nDatabase created successfully with {len(df)} rows and {len(columns)} columns.")
    print("Column information:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    # Close connection
    conn.close()
    
    return len(df), len(columns)

def query_database(sql_query):
    """Execute a test query on the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute(sql_query)
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        
        # Format and return results
        results = []
        for row in rows:
            results.append(dict(zip(columns, row)))
        
        return {"success": True, "results": results, "count": len(results)}
    
    except Exception as e:
        return {"success": False, "error": str(e)}
    
    finally:
        conn.close()

if __name__ == "__main__":
    # Convert Excel to SQLite
    num_rows, num_cols = excel_to_sqlite()
    
    # Test a simple query
    test_query = f"SELECT * FROM {TABLE_NAME} LIMIT 5"
    print(f"\nExecuting test query: {test_query}")
    
    result = query_database(test_query)
    if result["success"]:
        print(f"Query successful! Sample of {len(result['results'])} rows:")
        for row in result["results"]:
            print(row)
    else:
        print(f"Query failed: {result['error']}")
