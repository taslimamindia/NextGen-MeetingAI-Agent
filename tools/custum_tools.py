from langchain.tools import tool
from typing import List
from datetime import datetime
from pathlib import Path
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition

from models.gmail_manager import GmailManager


def collect_tools(instance):
    collected = []
    derived_methods = [
        name for name in dir(instance)
        if not name.startswith("_") and callable(getattr(instance, name)) and name in instance.__class__.__dict__
    ]
    for attr_name in derived_methods:
        method = getattr(instance, attr_name)
        if callable(method):
            collected.append(tool(method, return_direct=False, parse_docstring=True))
    return collected

@tool(parse_docstring=True, return_direct=False)
def get_time_now():
    """Get the current time in ISO format.
        Returns: Current time in ISO format.
    
    Args:
        None
    """

    return datetime.now().isoformat()

def system_prompt() -> str:
    """Search for a file named 'prompt.txt' in the current directory and its parent directories."""

    try:
        base = Path(__file__).resolve()
    except Exception:
        base = Path.cwd()
    for parent in (base.parent, *base.parents):
        candidate = parent / "prompt.txt"
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except Exception:
                return ""
    cwd_candidate = Path.cwd() / "prompt.txt"
    if cwd_candidate.is_file():
        try:
            return cwd_candidate.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""

def open_llm_connection(model_name: str = "accounts/fireworks/models/gpt-oss-120b", 
    api_key: str = None, model_type: str = "fireworks", temperature: float = 0.5):
    """Initialize and return a language model based on the specified type."""
    if model_type == "fireworks":
        from langchain_fireworks import ChatFireworks
        model_name = "accounts/fireworks/models/gpt-oss-120b"
        llm = ChatFireworks(
            model=model_name,
            temperature=temperature,
            api_key=api_key
        )
        return llm
    else:
        from langchain.chat_models import init_chat_model 
        llm = init_chat_model("google_genai:gemini-2.0-flash")
        return llm
    
def create_graph(tools: List, llm, memory=None) -> StateGraph:
    """Create a state graph for the chat agent with the given tools and language model.
    
    Args:
        tools (List): A list of tools to be used by the agent.
        llm: The language model to be used by the agent.
        memory: Optional memory checkpointer for the graph.
    """

    builder = StateGraph(MessagesState)

    llm_with_tools = llm.bind_tools(tools)

    def chat_agent(state: MessagesState) -> MessagesState:
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    builder.add_node("Agent", chat_agent)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "Agent")
    builder.add_conditional_edges("Agent", tools_condition)
    builder.add_edge("tools", "Agent")
    if memory:
        graph = builder.compile(checkpointer=memory)
    else:
        graph = builder.compile()

    return graph

def call_graph_without_logs(graph, query: str = None, prompt: str = None, config: dict = None):
    """Invoke the state graph with the provided query and prompt, returning the final response.

    Args:
        graph: The state graph to be invoked.
        query (str): The user query to be processed.
        prompt (str): The system prompt to guide the agent.
        config (dict): Optional configuration for the graph invocation.
    """
    messages = []
    if not prompt and not query:
        return "No input provided."
    
    if prompt:
        messages.append(("system", prompt))
    if query:
        messages.append(("user", query))

    if config:
        state = graph.invoke({"messages": messages}, config=config)
    else:
        state = graph.invoke({"messages": messages})
    
    return state["messages"][-1].content


def get_last_n_email_ids(gm: GmailManager, n: int = 5) -> List[str]:
    """Retrieve the IDs of the last n emails from the user's inbox.

    Args:
        gm (GmailManager): An instance of GmailManager to interact with Gmail API.
        n (int): The number of recent email IDs to retrieve.

    Returns:
        List[str]: A list of email IDs.
    """
    email_ids = []
    try:
        results = gm.service.users().messages().list(userId='me', maxResults=n).execute()
        messages = results.get('messages', [])
        for message in messages:
            email_ids.append(message['id'])
    except Exception as e:
        print(f"An error occurred while fetching email IDs: {e}")
    
    return email_ids