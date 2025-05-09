import json

def validate_json_format(filepath):
    required_keys = {"name", "Purpose", "Unique Values", "Histogram", "Insights"}
    try:
        with open(filepath, 'r') as file:
            data = json.load(file)
        
        # Check for missing keys
        missing_keys = required_keys - data.keys()
        if missing_keys:
            print(f"Missing keys: {missing_keys}")
            return False
        
        # Check for empty values
        for key in required_keys:
            if not data[key].strip():
                print(f"Empty value for key: {key}")
                return False
        
        print("JSON format is valid.")
        return True
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        return False

# Example usage
if __name__ == "__main__":
    filepath = "data_2_phone/preprocessing/column_summaries/formatted_output/App_Acronym.json"
    validate_json_format(filepath)
