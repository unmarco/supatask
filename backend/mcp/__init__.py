"""MCP (Model Context Protocol) module - HTTP Streamable Transport implementation."""

from .jsonrpc import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
    JSONRPCErrorResponse,
    ErrorCode,
)
from .handler import (
    handle_jsonrpc,
    create_response,
    create_error,
    MethodNotFoundError,
)
from .sessions import Session, SessionManager, session_manager

__all__ = [
    # JSON-RPC models
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCError",
    "JSONRPCErrorResponse",
    "ErrorCode",
    # Handlers
    "handle_jsonrpc",
    "create_response",
    "create_error",
    "MethodNotFoundError",
    # Sessions
    "Session",
    "SessionManager",
    "session_manager",
]
