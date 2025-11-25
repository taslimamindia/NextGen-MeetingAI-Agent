from __future__ import annotations
from typing import Optional, List, Dict, Any
from models.authentication import Authenticator
from email.message import EmailMessage
from googleapiclient.errors import HttpError
import base64
import os


GmailMessage = Dict[str, Any]
DraftResource = Dict[str, Any]


class GmailManager(Authenticator):
    """Gmail helper for reading messages and creating reply drafts.

    This class wraps a minimal set of Gmail API operations used by an
    assistant/agent. It authenticates via :class:`Authenticator` at
    construction and exposes small, well-typed helper methods suitable for
    conversion into LangChain tool-decorated callables.

    Notes on design for tool decorators
    - Methods use simple built-in types and mapping aliases (e.g. ``GmailMessage``)
      to make signatures easy to serialize and inspect.
    - Docstrings contain parameter and return descriptions to improve
      generated tool metadata.

    Attributes:
        service: The underlying Gmail API service client (constructed via
            :meth:`Authenticator.build_service`). Treated opaquely here.
        user_id: The Gmail account user id; commonly 'me'.
    """

    def __init__(
        self,
        client_secrets_file: str = 'client_secrets.json',
        token_file: str = 'token.json',
        scopes: Optional[List[str]] = None,
        user_id: str = 'me'
    ) -> None:
        # Do not set scopes here; let Authenticator provide the application-wide defaults.
        super().__init__(client_secrets_file=client_secrets_file, token_file=token_file, scopes=scopes)
        # The concrete type of `service` is an API resource object returned
        # by googleapiclient.discovery.build; annotate as Any to avoid
        # importing the concrete resource type here.
        self.service: Any = self.build_service('gmail', 'v1')
        self.user_id: str = user_id

    def _get_message_text(self, message: GmailMessage) -> str:
        """Extract and return plain text content from a Gmail message.

        The method attempts to decode a ``text/plain`` MIME part from the
        message payload. If no plain-text part is found it falls back to the
        message ``snippet``. The decoding is performed using URL-safe
        base64 decoding and any invalid byte sequences are replaced.

        Args:
            message: A Gmail message resource (mapping) as returned by the
                Gmail API.

        Returns:
            A plain-text string containing the message body or an empty
            string if the input is falsy or nothing could be extracted.
        """
        if not message:
            return ''

        def _get_plain_from_part(part: Dict[str, Any]) -> Optional[str]:
            mime = part.get('mimeType', '')
            body = part.get('body', {})
            data = body.get('data')
            if mime == 'text/plain' and data:
                return base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8', errors='replace')
            for p in part.get('parts', []) or []:
                text = _get_plain_from_part(p)
                if text:
                    return text
            return None

        payload = message.get('payload', {})
        text = _get_plain_from_part(payload)
        if text:
            return text
        return message.get('snippet', '') or ''

    def _get_header(self, message: GmailMessage, name: str) -> Optional[str]:
        """Return the value for the header ``name`` from the message.

        Args:
            message: The Gmail message resource.
            name: Case-insensitive header name to look up (e.g. 'From',
                'Subject', 'Message-ID').

        Returns:
            The header value as a string, or ``None`` if not present.
        """
        for h in message.get('payload', {}).get('headers', []):
            if h.get('name', '').lower() == name.lower():
                return h.get('value')
        return None
    
    def _get_metadata(self, message: GmailMessage) -> Dict[str, str]:
        """Return metadata summary for the message as a mapping.

        Extracts common headers (From, To, Date) and includes the Gmail thread
        and message id if present. Returns a dict mapping field names to their
        string values.
        """
        if not message:
            return {}

        metadata: Dict[str, str] = {}
        for header in ('From', 'To', 'Date'):
            value = self._get_header(message, header)
            if value:
                metadata[header] = value

        thread_id = message.get('threadId')
        if thread_id:
            metadata['Thread-ID'] = thread_id

        return metadata
    
    def create_reply_draft(self,
        reply_text: str,
        original_message_id: str,
        from_email: Optional[str],
    ) -> Optional[DraftResource]:
        """Create a draft reply to an existing Gmail message.
        Returns: an success message on success or an error message on failure.
        
        Args:
            reply_text: The plain-text body of the reply message.
            original_message_id: The message ID of the original email to reply to.
            from_email: Optional email address to use in the From header.
        """

        try:            
            if original_message_id:
                try:
                    original_message = self.service.users().messages().get(
                        userId=self.user_id, 
                        id=original_message_id, 
                        format='full'
                    ).execute()
                except HttpError as e:
                    return f"Error fetching original message: {e}"

            if not original_message:
                return "Error: Original message missing for draft creation."

            subject = self._get_header(original_message, 'Subject') or ''
            from_header = self._get_header(original_message, 'From') or ''
            to_header = self._get_header(original_message, 'To') or ''
            thread_id = original_message.get('threadId')

            reply_subject = subject
            if subject and not subject.lower().startswith('re:'):
                reply_subject = 'Re: ' + subject

            mime_msg = EmailMessage()
            mime_msg['To'] = from_header
            mime_msg['From'] = from_email or to_header or 'me'
            mime_msg['Subject'] = reply_subject
            if original_message_id:
                mime_msg['In-Reply-To'] = original_message_id
                mime_msg['References'] = original_message_id
            mime_msg.set_content(reply_text)

            raw_str = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
            body = {'message': {'raw': raw_str}}

            if thread_id:
                body['message']['threadId'] = thread_id

            draft = self.service.users().drafts().create(userId=self.user_id, body=body).execute()
            if draft:
                return "Success: Draft created."
            else:
                return "Error: Draft creation failed."
        except HttpError as e:
            return f"Error creating draft: {e}"

    def get_email_by_id(self, message_id: str) -> Optional[GmailMessage]:
        """Retrieve all messages in a conversation (thread) given a message_id.
        Returns: a list of mappings {'id', 'subject', 'sender', 'text'} or an error string on failure.

        Args:
            message_id: The Gmail message ID of any message in the thread.
        """
        if not message_id:
            return "Error: No message id provided."

        try:
            # Get the message to obtain the threadId
            message = self.service.users().messages().get(
                userId=self.user_id,
                id=message_id,
                format='full'
            ).execute()
        except HttpError as e:
            return f"Error fetching message to determine threadId: {e}"

        thread_id = message.get('threadId')
        if not thread_id:
            return "Error: threadId not found for the provided message."

        try:
            # Retrieve the full thread
            thread = self.service.users().threads().get(
                userId=self.user_id,
                id=thread_id,
                format='full'
            ).execute()
            msgs = thread.get('messages', []) if thread else []
            results: List[GmailMessage] = []
            for m in msgs:
                results.append({
                    "id": m.get('id'),
                    "subject": self._get_header(m, 'Subject') or '(no subject)',
                    "sender": self._get_header(m, 'From') or '(unknown)',
                    "text": self._get_message_text(m),
                    "metadata": self._get_metadata(m)
                })
            return results
        except HttpError as e:
            return f"Error fetching thread messages: {e}"

    def mark_message_as_not_read(self, message_id: str) -> str:
        """Mark a message as unread by adding the 'UNREAD' label.
        Returns: Success message on success, error message on failure.

        Args:
            message_id: The Gmail message ID to mark as unread.
        """
        try:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=message_id,
                body={'addLabelIds': ['UNREAD']}
            ).execute()
            return "Message marked as unread."
        except HttpError as e:
            return f"Error marking message as unread: {e}"

    def send_email_error_notification(self, error_message: str) -> str:
        """Send an email notification about an error (sends immediately).
           Returns a success message on success or an error message on failure.

        Args:
            error_message: The error message to include in the notification email.
        """

        to_email = os.environ.get('NOTIFICATION_EMAIL')

        if not to_email:
            return "Error: Notification email address not configured."

        mime_msg = EmailMessage()
        mime_msg['To'] = to_email
        mime_msg['From'] = 'me'
        mime_msg['Subject'] = 'Error Notification'
        mime_msg.set_content(f"An error occurred: {error_message}")

        raw_str = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
        body = {'raw': raw_str}

        try:
            sent = self.service.users().messages().send(userId=self.user_id, body=body).execute()
            return "Error notification sent successfully."
        except HttpError as e:
            return f"Error sending error notification: {e}"
    
__all__ = ['GmailManager']