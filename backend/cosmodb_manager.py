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

def add_request_response(session_id, request_text, response_text, request_time=None, response_time=None):
    """Add a request/response pair to the session in CosmosDB."""
    request_time = request_time or datetime.utcnow().strftime("%H:%M:%S UTC")
    response_time = response_time or datetime.utcnow().strftime("%H:%M:%S UTC")
    # Try to fetch the session doc
    session = get_session(session_id)
    if session is None:
        session = {
            "id": session_id,
            "sessionID": session_id,
            "request": [],
            "response": []
        }
    session["request"].append({"text": request_text, "time": request_time})
    session["response"].append({"text": response_text, "time": response_time})
    container.upsert_item(session)


def get_last_n_pairs(session_id, n=10):
    """Get the last n request/response pairs for a session."""
    session = get_session(session_id)
    if session is None:
        return []
    reqs = session.get("request", [])[-n:]
    resps = session.get("response", [])[-n:]
    return list(zip(reqs, resps))


def get_session(session_id):
    """Fetch the session document by sessionID."""
    query = f"SELECT * FROM c WHERE c.sessionID = @sessionID"
    params = [{"name": "@sessionID", "value": session_id}]
    items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
    return items[0] if items else None 