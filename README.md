# NextGen Meeting AI Agent

**NextGen Meeting AI Agent** is an intelligent assistant that automates meeting scheduling. It connects to your Gmail and Google Calendar to detect meeting requests, check availability, and draft responses automatically. It can also finalize the booking by scheduling the slot in your calendar once the requester confirms their choice.

Built with **FastAPI**, **LangGraph**, and **Fireworks AI**.

## ✨ Key Features

- 📧 **Email Analysis**: Automatically processes incoming emails to identify meeting requests.
- 📅 **Smart Scheduling**: Checks calendar availability and proposes suitable time slots.
- 🤖 **Agentic Workflow**: Uses LLMs to understand context and make decisions.
- 🔒 **Secure Integration**: Runs locally with your own Google Cloud credentials.

## 🚀 Getting Started

### Prerequisites
- Python 3.11.9
- Google Cloud Project (Gmail & Calendar APIs enabled) download the file `client_secrets.json`
- Fireworks AI API Key or the API Key to your LLM provider (You can modify the function tools.custom_tools.create_llm() to use other SDK for LLM)

### Installation

1. **Clone & Install**
   ```bash
   git clone <repository-url>
   cd NextGen-MeetingAI-Agent
   pip install -r requirements.txt
   ```

2. **Configuration**
   Create a `.env` file:
   ```env
   FIREWORKS_API_KEY=your_key
   CLIENT_SECRETS_FILE=client_secrets.json
   TOKEN_FILE=token.json
   MYEMAIL=your_email@example.com
   ```

## ⚡ Usage

Start the server:
```bash
fastapi dev api.py
```

Simulate a new email event:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/new_email" \
     -H "Content-Type: application/json" \
     -d '{"message_id": "GMAIL_MESSAGE_ID"}'
```

## 📂 Structure

- `api.py`: FastAPI entry point.
- `models/`: Gmail & Calendar logic.
- `tools/`: LangGraph tools.
- `agent.ipynb`: Development notebook.
- `client_secrets.json`: Google Credentials (Gmail & Calendar).

## License

This project is open source and available under the [MIT License](LICENSE).
