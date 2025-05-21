import os
from dotenv import load_dotenv
from azure.cosmos import CosmosClient, PartitionKey
from datetime import datetime

load_dotenv()

COSMOS_CONN_STR = os.getenv("COSMO_DB_CONNECTION_STRING")
COSMOS_DB_NAME = os.getenv("COSMO_DB_NAME", "talk2data")
COSMOS_CONTAINER_NAME = os.getenv("COSMO_DB_CONTAINER", "conversations")

client = CosmosClient.from_connection_string(COSMOS_CONN_STR)
database = client.create_database_if_not_exists(id=COSMOS_DB_NAME)
container = database.create_container_if_not_exists(
    id=COSMOS_CONTAINER_NAME,
    partition_key=PartitionKey(path="/sessionID")
)

def add_pair(session_id, user_msg, assistant_msg):
    """Add a (user, assistant) pair to the session in CosmosDB as a list of {role, content}."""
    session = get_session(session_id)
    if session is None:
        session = {
            "id": session_id,
            "sessionID": session_id,
            "history": []
        }
    # Only store user Q and assistant A
    session.setdefault("history", []).append({"role": "user", "content": user_msg})
    session["history"].append({"role": "assistant", "content": assistant_msg})
    # Trim to last 10 pairs (20 messages)
    session["history"] = session["history"][-20:]
    container.upsert_item(session)

def get_last_n_pairs(session_id, n=10):
    """Get the last n (user, assistant) pairs for a session as a list of (user_msg, assistant_msg) tuples."""
    session = get_session(session_id)
    if session is None:
        return []
    history = session.get("history", [])
    # Only return complete pairs
    pairs = []
    i = 0
    while i < len(history) - 1:
        if history[i]["role"] == "user" and history[i+1]["role"] == "assistant":
            pairs.append((history[i], history[i+1]))
            i += 2
        else:
            i += 1
    return pairs[-n:]

def get_session(session_id):
    """Fetch the session document by sessionID."""
    query = f"SELECT * FROM c WHERE c.sessionID = @sessionID"
    params = [{"name": "@sessionID", "value": session_id}]
    items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
    return items[0] if items else None

def save_subject(session_id: str, subject: str):
    """Store the primary entity name for this session."""
    container.upsert_item({
        "id": f"subject_{session_id}",
        "sessionID": session_id,
        "type": "subject",
        "value": subject
    })

def get_subject(session_id: str):
    """Retrieve the primary entity name for this session."""
    try:
        item = container.read_item(item=f"subject_{session_id}", partition_key=session_id)
        return item.get("value")
    except Exception:
        return None 