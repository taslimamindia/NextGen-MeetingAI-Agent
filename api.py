import logging
import os
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from models.gmail_manager import GmailManager
from models.calendar_manager import CalendarManager
from tools.custum_tools import (
    collect_tools, 
    get_time_now, 
    system_prompt,
    open_llm_connection,
    create_graph,
    call_graph_without_logs,
)
from langsmith import traceable
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv



load_dotenv()


raw_client_secrets = os.getenv("GOOGLE_CLIENT_SECRETS_PATH", os.getenv("CLIENT_SECRETS_FILE", "./client_secrets.json"))
raw_token_path = os.getenv("GOOGLE_TOKEN_PATH", os.getenv("TOKEN_FILE", "./token.json"))


def get_writable_path(source_path, filename):
    if source_path.startswith("/secrets"):
        writable_dest = f"/tmp/{filename}"
        # Copy the secret file to /tmp to be able to read AND modify it
        if os.path.exists(source_path):
            shutil.copy(source_path, writable_dest)
            return writable_dest
    return source_path

CLIENT_SECRETS_FILE = raw_client_secrets 
TOKEN_FILE = get_writable_path(raw_token_path, "token.json")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
MYEMAIL = os.getenv("MYEMAIL")


logging.basicConfig(level=logging.INFO)
logging.info(f"FIREWORKS_API_KEY: {FIREWORKS_API_KEY}")
logging.info(f"CLIENT_SECRETS_FILE: {CLIENT_SECRETS_FILE}")
logging.info(f"TOKEN_FILE: {TOKEN_FILE}")
logging.info(f"MYEMAIL: {MYEMAIL}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Managers and LLM
    gm = GmailManager(client_secrets_file=CLIENT_SECRETS_FILE, token_file=TOKEN_FILE)
    cm = CalendarManager(client_secrets_file=CLIENT_SECRETS_FILE, token_file=TOKEN_FILE)
    llm = open_llm_connection(api_key=FIREWORKS_API_KEY)
    tools = collect_tools(gm) + collect_tools(cm) + [get_time_now]
    
    # Create graph for this request
    app.state.graph = create_graph(tools, llm, memory=MemorySaver())
    yield

app = FastAPI(lifespan=lifespan)

class DataRequest(BaseModel):
    message_id: str

@app.post("/api/v1/new_email")
def process_new_email(request: DataRequest):
    message_id = request.message_id
    logging.info(f"Received request to process email with ID: {message_id}")
    
    try:
        query = f"A new email has arrived with message_id={message_id}"
        prompt = system_prompt()
        
        # Call the graph
        config = {'configurable': {'thread_id': message_id}}
        @traceable(project_name=os.getenv("LANGSMITH_PROJECT"))
        def call_graph_with_logs(graph, query: str, prompt: str, config: dict):
            return call_graph_without_logs(graph, query, prompt, config)
        result = call_graph_with_logs(app.state.graph, query=query, prompt=prompt, config=config)
        
        return {"status": "success", "message_id": message_id, "result": result}
        
    except Exception as e:
        logging.error(f"Error processing email {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
