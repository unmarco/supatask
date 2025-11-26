"""MCP session management."""

from typing import Optional, Dict
from datetime import datetime, timedelta
import secrets


class Session:
    """MCP Session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.initialized = False

    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()

    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if session has expired."""
        expiry = self.last_activity + timedelta(minutes=timeout_minutes)
        return datetime.now() > expiry


class SessionManager:
    """Manage MCP sessions."""

    def __init__(self):
        self.sessions: Dict[str, Session] = {}

    def create_session(self) -> Session:
        """Create a new session."""
        session_id = secrets.token_urlsafe(32)
        session = Session(session_id)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        session = self.sessions.get(session_id)
        if session and not session.is_expired():
            session.touch()
            return session
        elif session:
            # Clean up expired session
            del self.sessions[session_id]
        return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def cleanup_expired(self):
        """Remove expired sessions."""
        expired = [
            sid for sid, session in self.sessions.items() if session.is_expired()
        ]
        for sid in expired:
            del self.sessions[sid]


# Global session manager
session_manager = SessionManager()
