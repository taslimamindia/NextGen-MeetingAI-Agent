import logging
import os
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

# Configuration
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE")
TOKEN_FILE = os.getenv("TOKEN_FILE")
MYEMAIL = os.getenv("MYEMAIL")

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
        query = f"Un nouveau email est arrivée avec message_id={message_id}"
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
