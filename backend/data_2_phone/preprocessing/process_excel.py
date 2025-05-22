import os
import pandas as pd
import json
import time
import re  # Import regex module for sanitizing filenames
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables
load_dotenv()

# Constants from .env
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
COLUMN_DESCRIPTION_PROMPT = os.getenv("COLUMN_DESCRIPTION_PROMPT", "Describe the column and its unique values.")
API_VERSION = "2025-03-01-preview"

# File paths
EXCEL_FILE = "data_2_phone/data/PLMDashboardDataFeedFile-03212025.xlsx"
OUTPUT_JSON = "data_2_phone/preprocessing/column_description.json"

# Initialize Azure OpenAI client
client = AzureOpenAI(
    api_version=API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
)

def read_excel(file_path):
    """Read the Excel file into a Pandas DataFrame."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Excel file not found at path: {file_path}")
    return pd.read_excel(file_path)

def truncate_input(unique_values, histogram):
    """Truncate input to reduce size."""
    max_items = 100  # Adjust as needed
    truncated_values = unique_values[:max_items]
    truncated_histogram = {k: histogram[k] for k in list(histogram)[:max_items]}
    return truncated_values, truncated_histogram

def generate_column_summary(column_name, column_data):
    """Generate a summary for a column using the Azure OpenAI client with retry logic."""
    unique_values = column_data.dropna().unique().tolist()
    histogram = column_data.value_counts().to_dict()

    # Truncate input to reduce size
    truncated_values, truncated_histogram = truncate_input(unique_values, histogram)

    # Prepare the prompt
    prompt = f"{COLUMN_DESCRIPTION_PROMPT}\n\nColumn Name: {column_name}\nUnique Values: {truncated_values}\nHistogram: {truncated_histogram}"

    # Retry logic with exponential backoff
    max_retries = 5
    retry_delay = 1  # Initial delay in seconds

    for attempt in range(max_retries):
        try:
            # Query the LLM endpoint
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                model=AZURE_OPENAI_DEPLOYMENT_NAME
            )
            # Return the LLM response if successful
            return response.choices[0].message.content

        except Exception as e:
            if "429" in str(e):
                print(f"Rate limit exceeded. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                raise e  # Raise other exceptions immediately

    # If all retries fail, raise an exception
    raise Exception("Failed to generate column summary after multiple retries due to rate limit.")

def sanitize_filename(column_name):
    """Sanitize column name to create a valid filename."""
    return re.sub(r'[\w\-_\. ]', '_', column_name)

def is_column_summary_done(column_name):
    """Check if a column summary JSON file already exists."""
    sanitized_column_name = sanitize_filename(column_name)
    column_file = f"preprocessing/{sanitized_column_name}.json"
    return os.path.exists(column_file)

def process_columns(df):
    """Process each column in the DataFrame and generate summaries."""
    column_descriptions = {}
    for column in df.columns:
        # Skip columns that already have summaries
        if is_column_summary_done(column):
            print(f"Skipping column '{column}' as its summary already exists.")
            continue

        print(f"Processing column: {column}...")  # Indicate column processing start

        # Generate summary for the column
        summary = generate_column_summary(column, df[column])
        column_descriptions[column] = summary

        # Sanitize column name for filename
        sanitized_column_name = sanitize_filename(column)
        column_file = f"preprocessing/{sanitized_column_name}.json"

        # Write individual column summary to a JSON file
        os.makedirs("preprocessing", exist_ok=True)
        with open(column_file, "w") as f:
            json.dump({column: summary}, f, indent=4)

        print(f"Summary for column '{column}' generated and stored in {column_file}.")  # Indicate completion

    return column_descriptions

def call_llm(prompt, temperature=0.0):
    """General function to call the LLM with any prompt using Azure OpenAI client."""
    try:
        # Query the LLM endpoint using the existing Azure OpenAI client
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            model=AZURE_OPENAI_DEPLOYMENT_NAME
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling LLM: {e}")
        raise e

def main():
    try:
        # Read the Excel file
        df = read_excel(EXCEL_FILE)

        # Generate column descriptions and write individual JSON files
        column_descriptions = process_columns(df)

        # Write the master JSON file with all column summaries
        os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
        with open(OUTPUT_JSON, "w") as f:
            json.dump(column_descriptions, f, indent=4)

        print(f"Master JSON file with all column summaries stored in {OUTPUT_JSON}.")  # Indicate master file completion

    except FileNotFoundError as e:
        print(e)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
