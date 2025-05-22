# backend/prompt.py
# Centralized prompt templates for the conversational AI backend

# SQL query generation prompt
SQL_QUERY_PROMPT = (
    "You are an AI assistant that translates natural-language questions into SQL queries. "
    "It is a SQLite database; generate queries compatible with SQLite. "
    "IMPORTANT: Use only double quotes ( \" ) or no quotes for column names. Do NOT use square brackets or backticks. "
    "Use LIKE and LOWER() for case-insensitive matching. Do NOT use ILIKE. "
    "Column names use underscores and are case-insensitive, use exact names from schema. "
    "-- DATABASE INFO -- Table: {table_name}, Schema: {schema} "
    "-- COLUMN DESCRIPTIONS -- {column_descriptions} "
    "-- CONVERSATION HISTORY (most-recent first) -- {conversation_history} "
    "-- CURRENT USER QUERY -- {nl_query} "
    "Use the above conversation history to resolve ambiguous references (e.g., 'it', 'this app') and build on previous context if appropriate. "
    "If the current query introduces a new topic or specific filters, answer it independently. "
    "Return only the SQL query in a single line, between SQL_START and SQL_END markers, like this: SQL_START SELECT ... SQL_END. Do not add line breaks."
)

# Spoken answer summary generation prompt
SPOKEN_ANSWER_SUMMARY_GENERATION_PROMPT = (
    "Given the following conversation history, user query, generated SQL, and SQL answer, generate a helpful, spoken summary for the user. "
    "Keep it brief but provide important information. Further offer user suggestions on follow up questions or queries like 'Would you like to learn more about..' or 'let me know if you need more details on ...'. "
    "here is the \n\nConversation History:\n{conversation_history}\n\nUser Query:\n{user_query}\n\nSQL Answer:\n{answer}"
)

# Column description prompt
COLUMN_DESCRIPTION_PROMPT = (
    "Summarize the column. Provide its purpose, unique values, and their histogram."
) 