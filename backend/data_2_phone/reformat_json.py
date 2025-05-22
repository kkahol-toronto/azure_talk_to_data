import os
import json
import re

# Paths
INPUT_FOLDER = os.path.join(
    "/Users/kanavkahol/work/data_2_phone", "preprocessing", "column_summaries"
)
OUTPUT_FOLDER = os.path.join(
    "/Users/kanavkahol/work/data_2_phone", "preprocessing", "column_summaries", "formatted_output"
)

def sanitize_filename(filename):
    """Sanitize filenames by removing extra spaces and replacing invalid characters."""
    sanitized = re.sub(r"[^\w\-.]", "_", filename.strip())  # Replace invalid characters with underscores
    sanitized = re.sub(r"_+", "_", sanitized)  # Replace multiple underscores with a single underscore
    return sanitized

def reformat_json(file_path):
    """Reformat the JSON structure."""
    with open(file_path, "r") as f:
        data = json.load(f)

    # Extract the column name (key) and its content
    column_name, content = next(iter(data.items()))

    # Define section boundaries and patterns
    section_markers = [
        r"\*\*Purpose:\*\*", 
        r"\*\*Unique Values:\*\*", 
        r"\*\*Histogram.*?:\*\*",
        r"\*\*Histogram Summary:\*\*",
        r"\*\*Conclusion:\*\*",
        r"\*\*Summary:\*\*",
        r"\*\*Insights:\*\*"
    ]
    
    # Find all section starts
    section_positions = []
    for marker in section_markers:
        matches = list(re.finditer(marker, content, re.DOTALL))
        for match in matches:
            section_positions.append((match.start(), match.group()))
    
    # Sort by position
    section_positions.sort()
    
    # Extract content between sections
    sections = {}
    for i, (pos, section_name) in enumerate(section_positions):
        start = pos + len(section_name)
        end = section_positions[i+1][0] if i+1 < len(section_positions) else len(content)
        section_content = content[start:end].strip()
        sections[section_name.strip('*: ')] = section_content
    
    # Extract and process specific sections
    purpose = sections.get('Purpose', "").strip()
    unique_values = sections.get('Unique Values', "").strip()
    
    # Process histogram - combine main histogram and summary if available
    histogram = sections.get('Histogram (Frequency of App IDs)', "") or sections.get('Histogram', "")
    histogram_summary = sections.get('Histogram Summary', "")
    if histogram_summary:
        histogram += f"\n\n{histogram_summary}"
    
    # Process insights - use Conclusion or Summary if available
    insights = sections.get('Conclusion', "") or sections.get('Summary', "") or sections.get('Insights', "")
    
    # Reformat the data
    reformatted_data = {
        "name": column_name,
        "Purpose": purpose,
        "Unique Values": unique_values,
        "Histogram": histogram.strip(),
        "Insights": insights.strip(),
    }

    return reformatted_data

def process_files(input_folder, output_folder):
    """Process all JSON files in the input folder and save reformatted files to the output folder."""
    absolute_input_folder = os.path.abspath(input_folder)
    print(f"Resolved absolute input folder path: {absolute_input_folder}")

    if not os.path.exists(absolute_input_folder):
        print(f"Input folder does not exist: {absolute_input_folder}")
        return
    else:
        print(f"Input folder exists: {absolute_input_folder}")
        print("Files in input folder:")
        for file_name in os.listdir(absolute_input_folder):
            print(file_name)

    os.makedirs(output_folder, exist_ok=True)

    files_processed = 0
    print(f"Scanning input folder: {absolute_input_folder}")
    for file_name in os.listdir(absolute_input_folder):
        input_file_path = os.path.join(absolute_input_folder, file_name)

        # Skip directories and non-JSON files
        if not os.path.isfile(input_file_path) or not file_name.endswith(".json"):
            print(f"Skipping: {file_name} (not a valid JSON file)")
            continue

        sanitized_file_name = sanitize_filename(file_name)
        output_file_path = os.path.join(output_folder, sanitized_file_name)

        print(f"Processing file: {file_name} (sanitized to {sanitized_file_name})...")

        try:
            # Reformat the JSON content
            reformatted_data = reformat_json(input_file_path)

            # Save the reformatted JSON
            with open(output_file_path, "w") as f:
                json.dump(reformatted_data, f, indent=4)

            print(f"Reformatted file saved to: {output_file_path}")
            files_processed += 1
        except Exception as e:
            print(f"Error processing file {file_name}: {e}")

    if files_processed == 0:
        print("No JSON files were processed. Ensure the input folder contains valid JSON files.")
    else:
        print(f"Total files processed: {files_processed}")

def main():
    print(f"Input folder: {os.path.abspath(INPUT_FOLDER)}")
    print(f"Output folder: {os.path.abspath(OUTPUT_FOLDER)}")
    process_files(INPUT_FOLDER, OUTPUT_FOLDER)

if __name__ == "__main__":
    main()
