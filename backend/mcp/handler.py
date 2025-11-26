"""JSON-RPC request handlers for MCP protocol."""

import json
from typing import Any, Optional

from .jsonrpc import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    JSONRPCError,
    ErrorCode,
)


class MethodNotFoundError(Exception):
    """Raised when an unknown method is called."""

    pass


def create_response(id: Any, result: Any) -> JSONRPCResponse:
    """Create a successful JSON-RPC response."""
    return JSONRPCResponse(jsonrpc="2.0", result=result, id=id)


def create_error(
    id: Any, code: int, message: str, data: Optional[Any] = None
) -> JSONRPCErrorResponse:
    """Create a JSON-RPC error response."""
    error = JSONRPCError(code=code, message=message, data=data)
    return JSONRPCErrorResponse(jsonrpc="2.0", error=error, id=id)


async def handle_jsonrpc(request: JSONRPCRequest, mcp_server) -> dict:
    """
    Handle JSON-RPC request and route to appropriate MCP method.

    Returns dict (will be converted to JSONRPCResponse or JSONRPCErrorResponse)
    """
    method = request.method
    params = request.params or {}

    # Route to appropriate handler
    if method == "initialize":
        return await handle_initialize(params, mcp_server)
    elif method == "tools/list":
        return await handle_tools_list(mcp_server)
    elif method == "tools/call":
        return await handle_tools_call(params, mcp_server)
    elif method == "ping":
        return {}  # Empty response for ping
    else:
        raise MethodNotFoundError(f"Unknown method: {method}")


async def handle_initialize(params: dict, mcp_server) -> dict:
    """Handle initialize request."""
    # MCP initialization handshake
    return {
        "protocolVersion": "2025-06-18",
        "capabilities": {
            "tools": {},
        },
        "serverInfo": {"name": "supatask-mcp", "version": "1.0.0"},
    }


async def handle_tools_list(mcp_server) -> dict:
    """Handle tools/list request."""
    tools = mcp_server.get_tools_schema()
    return {"tools": tools}


async def handle_tools_call(params: dict, mcp_server) -> dict:
    """
    Handle tools/call request.

    Returns MCP CallToolResult format:
    {
        "content": [{"type": "text", "text": "..."}],
        "isError": false
    }
    """
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        raise ValueError("Missing tool name")

    result = await mcp_server.execute_tool(tool_name, arguments)

    # Wrap result in MCP CallToolResult format
    is_error = not result.get("success", True)
    text_content = json.dumps(result, default=str)

    return {"content": [{"type": "text", "text": text_content}], "isError": is_error}
