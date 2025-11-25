Write-Host "🚀 Starting deployment to Google Cloud Run (PowerShell)..." -ForegroundColor Green

# In PowerShell, the backtick (`) is used for line continuation
gcloud run deploy mon-agent-service `
    --source . `
    --region us-east1 `
    --allow-unauthenticated `
    --set-env-vars="GOOGLE_CLIENT_SECRETS_PATH=/secrets/auth/client_secrets.json,GOOGLE_TOKEN_PATH=/secrets/token/token.json" `
    --set-secrets="/secrets/auth/client_secrets.json=google-client-secret:latest" `
    --set-secrets="/secrets/token/token.json=google-token-json:latest" `
    --set-secrets="FIREWORKS_API_KEY=FIREWORKS_API_KEY:latest" `
    --set-secrets="TOKEN_FILE=TOKEN_FILE:latest" `
    --set-secrets="CLIENT_SECRETS_FILE=CLIENT_SECRETS_FILE:latest" `
    --set-secrets="NOTIFICATION_EMAIL=NOTIFICATION_EMAIL:latest" `
    --set-secrets="LANGSMITH_ENDPOINT=LANGSMITH_ENDPOINT:latest" `
    --set-secrets="LANGSMITH_API_KEY=LANGSMITH_API_KEY:latest" `
    --set-secrets="LANGSMITH_PROJECT=LANGSMITH_PROJECT:latest" `
    --set-secrets="LANGSMITH_TRACING=LANGSMITH_TRACING:latest" `
    --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest" `
    --set-secrets="MYEMAIL=MYEMAIL:latest"

if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Deployment finished!" -ForegroundColor Green
} else {
        Write-Host "❌ Deployment failed." -ForegroundColor Red
}