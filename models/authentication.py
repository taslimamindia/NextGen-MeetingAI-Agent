"""Authentication helper.

Provides Authenticator, a small helper to obtain Google API credentials
and build API service clients. The implementation stores credentials in a
token file and refreshes them when needed.
"""
from __future__ import annotations
import os
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Default scopes requested by the application. These combine the Gmail
# and Calendar permissions commonly used by the managers in this repo.
# Put them here so child classes don't need to repeat scope lists.
DEFAULT_SCOPES: List[str] = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar',
]


class Authenticator:
    """Manage Google OAuth2 credentials and build API service clients.

    Example:
        auth = Authenticator('client_secrets.json', 'token.json', ['scope1', 'scope2'])
        service = auth.build_service('gmail', 'v1')
    """

    def __init__(
        self,
        client_secrets_file: str = 'client_secrets.json',
        token_file: str = 'token.json',
        scopes: Optional[List[str]] = None,
    ) -> None:
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        # Use the centrally defined default scopes when none are provided.
        self.scopes = scopes if scopes is not None else DEFAULT_SCOPES
        self.creds: Optional[Credentials] = None

    def authorize(self, extra_scopes: Optional[List[str]] = None) -> None:
        """Obtain or refresh Credentials for the requested scopes.

        If extra_scopes is provided, they are merged with the instance scopes.
        """
        scopes = list(self.scopes)
        if extra_scopes:
            for s in extra_scopes:
                if s not in scopes:
                    scopes.append(s)

        creds = None
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, scopes)
                # If the stored credentials do not include all requested scopes,
                # force a new authorization flow so the user can grant the missing scopes.
                stored_scopes = set(getattr(creds, 'scopes', []) or [])
                if not set(scopes).issubset(stored_scopes):
                    creds = None
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, scopes)
                creds = flow.run_local_server(port=0)

            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())

        self.creds = creds

    def build_service(self, api_name: str, api_version: str, extra_scopes: Optional[List[str]] = None):
        """Return a Google API service client for the given API name and version.

        If credentials are missing or invalid, authorize() is called.
        """
        if self.creds is None or not self.creds.valid:
            self.authorize(extra_scopes=extra_scopes)

        return build(api_name, api_version, credentials=self.creds, cache_discovery=False)


__all__ = ['Authenticator']
