# NextGen Meeting AI Agent

**NextGen Meeting AI Agent** is an intelligent assistant that automates meeting scheduling. It connects to your Gmail and Google Calendar to detect meeting requests, check availability, and draft responses automatically. It can also finalize the booking by scheduling the slot in your calendar once the requester confirms their choice.

I gratefully acknowledge the guidance and supervision of [Professor Pierre‑Marc Jodoin](https://jodoin.github.io/) throughout this project.

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
   NOTIFICATION_EMAIL=your_notification_email@example.com
   LANGSMITH_PROJECT=your_project_name
   # Optional: LangSmith tracing
   LANGSMITH_API_KEY=your_langsmith_key
   LANGSMITH_TRACING=true
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
- `client_secrets.json`: Google Credentials (Gmail & Calendar).
- `syn_env_to_gcp.sh`: Script to sync environment variables to Google Manager Secret.
- `deploy.ps1`: Deployment script for Google Cloud Run.

## ☁️ Deployment

To deploy to Google Cloud Run using the provided PowerShell script:

> ⚠️ **Important**: Before deploying, run the `agent.ipynb` notebook locally. This step is crucial to initialize the Google API connection and generate the necessary authentication tokens (`token.json`) required for the application to function correctly.

1. Ensure you have the Google Cloud SDK installed and authenticated.
2. Run the environment script to send files and variables to google manager secret.
   ```bash
   ./syn_env_to_gcp.sh
   ```
3. Run the deployment script:
   ```powershell
   ./deploy.ps1
   ```

## License

This project is open source and available under the [MIT License](LICENSE).


