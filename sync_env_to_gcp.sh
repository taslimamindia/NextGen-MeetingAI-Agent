#!/bin/bash

# --- CONFIGURATION ---
ENV_FILE=".env"
CLIENT_SECRET_FILE="client_secrets.json"
TOKEN_FILE="token.json"

# Names to be used inside Google Secret Manager
CLIENT_SECRET_NAME="google-client-secret"
TOKEN_SECRET_NAME="google-token-json"

# --- FUNCTION TO UPLOAD SECRETS ---
update_secret() {
    local name=$1
    local source=$2
    local is_file=$3 # "true" or "false"

    # 1. VALIDATION: Check for invalid characters (spaces, special chars)
    if [[ ! "$name" =~ ^[a-zA-Z_0-9]+$ ]]; then
        echo "   ⚠️  SKIPPING '$name': Invalid characters. Secret IDs must be alphanumeric."
        return
    fi

    echo -n "   Processing: $name ... "

    # 2. CHECK EXISTENCE (Silently)
    # Added --quiet to prevent interactive prompts
    if gcloud secrets describe "$name" --quiet > /dev/null 2>&1; then
        # --- SECRET EXISTS: ADD NEW VERSION ---
        if [ "$is_file" == "true" ]; then
            gcloud secrets versions add "$name" --data-file="$source" --quiet > /dev/null 2>&1
        else
            printf "%s" "$source" | gcloud secrets versions add "$name" --data-file=- --quiet > /dev/null 2>&1
        fi
        echo "✅ Updated (New Version)"
    else
        # --- SECRET MISSING: CREATE NEW ---
        if [ "$is_file" == "true" ]; then
            gcloud secrets create "$name" --data-file="$source" --quiet > /dev/null 2>&1
        else
            printf "%s" "$source" | gcloud secrets create "$name" --data-file=- --quiet > /dev/null 2>&1
        fi
        echo "✨ Created"
    fi
}

echo ""
echo "🚀 STARTING SECRET SYNCHRONIZATION"
echo "-------------------------------------"

# --- 1. PROCESS .ENV FILE ---
if [ -f "$ENV_FILE" ]; then
    echo "📂 Reading $ENV_FILE..."
    
    # Read line by line
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip comments (#) and empty lines
        if [[ "$line" =~ ^\s*# ]] || [[ -z "$line" ]]; then
            continue
        fi

        # Remove 'export ' if present
        line=${line#export }

        # Extract Key and Value (split by first =)
        key=$(echo "$line" | cut -d '=' -f 1)
        value=$(echo "$line" | cut -d '=' -f 2-)

        # TRIM WHITESPACE (Fixes the "Invalid Format" error)
        key=$(echo "$key" | xargs) 
        value=$(echo "$value" | xargs)

        # Remove quotes around value if they exist
        value=${value%\"}
        value=${value#\"}
        value=${value%\'}
        value=${value#\'}

        if [[ -n "$key" ]]; then
            update_secret "$key" "$value" "false"
        fi

    done < "$ENV_FILE"
else
    echo "⚠️  File $ENV_FILE not found."
fi

echo "-------------------------------------"

# --- 2. PROCESS JSON FILES ---

# Client Secrets
if [ -f "$CLIENT_SECRET_FILE" ]; then
    update_secret "$CLIENT_SECRET_NAME" "$CLIENT_SECRET_FILE" "true"
else
    echo "⚠️  File $CLIENT_SECRET_FILE not found."
fi

# Token File
if [ -f "$TOKEN_FILE" ]; then
    update_secret "$TOKEN_SECRET_NAME" "$TOKEN_FILE" "true"
else
    echo "⚠️  File $TOKEN_FILE not found."
fi

echo "-------------------------------------"
echo "🎉 SYNC COMPLETED!"