from langchain.tools import tool
from typing import List
from googleapiclient.errors import HttpError
from models.gmail_manager import GmailManager
from datetime import datetime
from pathlib import Path
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
# from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver


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

def get_last_n_email_ids(gm: GmailManager, me: str, n: int) -> List[str] | str:
    """Retourne les IDs des n messages récents de l'INBOX sans le label 'done'.
       Si un message est marqué 'inprogress', il n'est retourné que si le dernier
       message du thread est reçu (et non une réponse envoyée par nous).
    """
    
    if not isinstance(n, int) or n <= 0:
        return "Error: 'n' must be a positive integer."

    try:
        try:
            lbl_resp = gm.service.users().labels().list(userId=gm.user_id).execute()
            labels = (lbl_resp.get('labels') or [])
            done_label_id = next(
                (l.get('id') for l in labels if l.get('name', '').lower() == 'done'),
                None
            )
            inprogress_label_id = next(
                (l.get('id') for l in labels if l.get('name', '').lower() == 'inprogress'),
                None
            )
        except HttpError as e:
            done_label_id = None

        resp = gm.service.users().messages().list(
            userId=gm.user_id,
            labelIds=['INBOX'],
            maxResults=n
        ).execute()
        messages = resp.get('messages', []) if resp else []
        if not messages:
            return []

        result: List[str] = []
        for m in messages:
            mid = m.get('id')
            if not mid:
                continue
            try:
                msg = gm.service.users().messages().get(
                    userId=gm.user_id,
                    id=mid,
                    format='metadata'
                ).execute()
                label_ids = msg.get('labelIds', []) or []

                # Exclure si 'done'
                if done_label_id and done_label_id in label_ids:
                    continue

                # Ne pas utiliser les labels; déterminer via From/To si le dernier message est une réponse
                thread_id = msg.get('threadId')
                if thread_id:
                    try:
                        thread = gm.service.users().threads().get(
                            userId=gm.user_id,
                            id=thread_id,
                            format='metadata'
                        ).execute()
                        t_msgs = thread.get('messages', []) or []
                        if t_msgs:
                            last_msg = t_msgs[-1]
                            headers = (last_msg.get('payload') or {}).get('headers') or []
                            def _get_hdr(name: str) -> str:
                                for h in headers:
                                    if h.get('name', '').lower() == name.lower():
                                        return h.get('value', '')
                                return ''
                            from_h = (_get_hdr('From') or '').lower()
                            to_h = (_get_hdr('To') or '').lower()
                            # Si le dernier message vient de cette adresse, on le considère comme une réponse -> on exclut
                            if 'taslimamindiakassa80@gmail.com' in from_h:
                                continue
                    except HttpError as e:
                        print(f"Error fetching thread {thread_id}: {e}")
                        # En cas d'erreur, on ne filtre pas davantage

                # Cas normal (non 'inprogress' et non 'done')
                result.append(mid)
            except HttpError as e:
                print(f"Error fetching message {mid}: {e}")
                continue

        return result
    except HttpError as e:
        error = f"Error fetching last {n} emails: {e}"
        print(error)
        return error
    
def system_prompt() -> str:
    # Cherche prompt.txt en remontant depuis le dossier du module, puis dans le cwd.
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

def open_llm_connection(model_name: str = "accounts/fireworks/models/gpt-oss-120b", api_key: str = None, model_type: str = "fireworks", temperature: float = 0.5):
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