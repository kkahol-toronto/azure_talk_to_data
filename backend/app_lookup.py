import os
import pandas as pd
from rapidfuzz import process, fuzz

EXCEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data/PLM_Dashboard_Data_Feed_File-03212025.xlsx'))

# Load the Excel data once at startup
try:
    df = pd.read_excel(EXCEL_PATH)
    df.columns = [str(col).strip() for col in df.columns]
    print(f"[app_lookup] DataFrame columns: {df.columns.tolist()}")
    print(f"[app_lookup] Sample APP NAMEs: {df['APP NAME'].head(10).tolist()}")
except Exception as e:
    print(f"[app_lookup] Error loading Excel file: {e}")
    df = pd.DataFrame()

# Normalize app names for matching
APP_NAMES = df['APP NAME'].dropna().unique().tolist() if not df.empty else []


def fuzzy_match_app_name(name, threshold=80):
    if not name or not APP_NAMES:
        return None
    match, score, _ = process.extractOne(name, APP_NAMES, scorer=fuzz.token_sort_ratio)
    if score >= threshold:
        return match
    return None


def lookup_property(app_name, prop):
    """Look up a property (e.g., 'App ID') for a given app name (fuzzy match, robust contains match)."""
    canonical = fuzzy_match_app_name(app_name)
    print(f"[app_lookup] Looking up property '{prop}' for app name '{app_name}' (canonical: '{canonical}')")
    if not canonical:
        raise KeyError(f"App name '{app_name}' not found.")
    # Use contains match for robustness
    matches = df[df['APP NAME'].str.lower().str.contains(canonical.lower().strip())]
    print(f"[app_lookup] Found {len(matches)} matching rows for '{canonical}'.")
    if not matches.empty:
        try:
            print(f"[app_lookup] Matched rows:\n{matches[['APP NAME', prop]]}")
        except Exception as e:
            print(f"[app_lookup] Could not print matched rows: {e}")
    if matches.empty:
        raise KeyError(f"App '{canonical}' not found in data.")
    if prop not in df.columns:
        print(f"[app_lookup] Property '{prop}' not found in columns: {df.columns.tolist()}")
        raise KeyError(f"Property '{prop}' not found in data.")
    # Return all unique values for the property for this app
    values = matches[prop].dropna().unique().tolist()
    print(f"[app_lookup] Property values found: {values}")
    return values if len(values) > 1 else values[0] if values else None 