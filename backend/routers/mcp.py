"""MCP (Model Context Protocol) router - HTTP Streamable Transport (2025-06-18 spec)."""

import asyncio
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Request, Response, Header
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as redis

from models import TaskCreate, TaskUpdate, LogFilter, TaskFilter
from database import get_redis
from services.task_service import TaskService
from services.log_service import LogService

# Import MCP modules
from mcp.jsonrpc import JSONRPCRequest, JSONRPCErrorResponse, ErrorCode
from mcp.handler import (
    handle_jsonrpc,
    create_response,
    create_error,
    MethodNotFoundError,
)
from mcp.sessions import session_manager

router = APIRouter(prefix="/mcp", tags=["mcp"])

SUPPORTED_PROTOCOL_VERSION = "2025-06-18"


class MCPServer:
    """MCP Server implementation."""

    def __init__(self, redis_client: redis.Redis):
        self.task_service = TaskService(redis_client)
        self.log_service = LogService(redis_client)

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Get MCP tools schema."""
        return [
            {
                "name": "create_task",
                "description": "Create a new task with optional tags",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "archived"],
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "read_task",
                "description": "Read a task by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "integer"}},
                    "required": ["task_id"],
                },
            },
            {
                "name": "list_tasks",
                "description": "List tasks with optional filters",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "archived"],
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "created_after": {"type": "string", "format": "date-time"},
                        "created_before": {"type": "string", "format": "date-time"},
                    },
                },
            },
            {
                "name": "update_task",
                "description": "Update a task",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "archived"],
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["task_id"],
                },
            },
            {
                "name": "delete_task",
                "description": "Delete a task",
                "inputSchema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "integer"}},
                    "required": ["task_id"],
                },
            },
            {
                "name": "get_logs",
                "description": "Get activity or system logs",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "log_type": {"type": "string", "enum": ["activity", "system"]},
                        "start_time": {"type": "string", "format": "date-time"},
                        "end_time": {"type": "string", "format": "date-time"},
                        "limit": {"type": "integer", "maximum": 1000},
                    },
                },
            },
        ]

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an MCP tool."""
        try:
            if tool_name == "create_task":
                task_data = TaskCreate(**arguments)
                task = await self.task_service.create_task(task_data)
                await self.log_service.log_activity(
                    f"Task created via MCP: {task.title}", task_id=task.id
                )
                return {"success": True, "task": task.model_dump(mode="json")}

            elif tool_name == "read_task":
                task = await self.task_service.get_task_with_time(arguments["task_id"])
                if not task:
                    return {"success": False, "error": "Task not found"}
                return {"success": True, "task": task.model_dump(mode="json")}

            elif tool_name == "list_tasks":
                # Parse datetime strings
                if "created_after" in arguments:
                    arguments["created_after"] = datetime.fromisoformat(
                        arguments["created_after"]
                    )
                if "created_before" in arguments:
                    arguments["created_before"] = datetime.fromisoformat(
                        arguments["created_before"]
                    )

                filters = TaskFilter(**arguments)
                tasks = await self.task_service.list_tasks(filters)
                return {
                    "success": True,
                    "tasks": [task.model_dump(mode="json") for task in tasks],
                }

            elif tool_name == "update_task":
                task_id = arguments.pop("task_id")
                update_data = TaskUpdate(**arguments)
                task = await self.task_service.update_task(task_id, update_data)
                if not task:
                    return {"success": False, "error": "Task not found"}
                await self.log_service.log_activity(
                    "Task updated via MCP", task_id=task.id
                )
                return {"success": True, "task": task.model_dump(mode="json")}

            elif tool_name == "delete_task":
                success = await self.task_service.delete_task(arguments["task_id"])
                if not success:
                    return {"success": False, "error": "Task not found"}
                await self.log_service.log_activity(
                    "Task deleted via MCP", task_id=arguments["task_id"]
                )
                return {"success": True}

            elif tool_name == "get_logs":
                # Parse datetime strings
                if "start_time" in arguments:
                    arguments["start_time"] = datetime.fromisoformat(
                        arguments["start_time"]
                    )
                if "end_time" in arguments:
                    arguments["end_time"] = datetime.fromisoformat(
                        arguments["end_time"]
                    )

                filters = LogFilter(**arguments)
                logs = await self.log_service.get_logs(filters)
                return {
                    "success": True,
                    "logs": [log.model_dump(mode="json") for log in logs],
                }

            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"success": False, "error": str(e)}


# =============================================================================
# MCP Streamable HTTP Transport (2025-06-18 spec)
# =============================================================================


@router.api_route("/", methods=["POST", "GET"])
async def mcp_endpoint(
    request: Request,
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    mcp_protocol_version: Optional[str] = Header(None, alias="MCP-Protocol-Version"),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    MCP Streamable HTTP endpoint (2025-06-18 spec).

    POST: Client sends JSON-RPC requests
    GET: Optional SSE stream for server-initiated messages
    """
    # Validate protocol version if provided (required after initialization)
    if mcp_protocol_version and mcp_protocol_version != SUPPORTED_PROTOCOL_VERSION:
        return JSONResponse(
            content={
                "error": f"Unsupported protocol version. Supported: {SUPPORTED_PROTOCOL_VERSION}"
            },
            status_code=400,
        )

    if request.method == "POST":
        return await handle_post(
            request, mcp_session_id, mcp_protocol_version, redis_client
        )
    else:  # GET
        return await handle_get(request, mcp_session_id, redis_client)


async def handle_post(
    request: Request,
    session_id: Optional[str],
    protocol_version: Optional[str],
    redis_client: redis.Redis,
) -> Response:
    """Handle POST request - JSON-RPC message from client."""
    body = None

    try:
        # Parse JSON body
        body = await request.json()

        # Check if this is a notification (no id field) vs request
        is_notification = "id" not in body

        # Session management
        session = None
        if session_id:
            session = session_manager.get_session(session_id)
            if not session:
                # Session was terminated or expired
                return JSONResponse(
                    content={"error": "Session not found or expired"}, status_code=404
                )

        method = body.get("method", "")

        # Handle notifications (no id field = no response expected)
        if is_notification:
            if method == "notifications/initialized":
                # Client confirms initialization is complete
                if session:
                    session.initialized = True
                return Response(status_code=202)  # Accepted
            elif method == "notifications/cancelled":
                # Client cancelled a request - acknowledge
                return Response(status_code=202)
            else:
                # Unknown notification - still return 202
                return Response(status_code=202)

        # Parse as JSON-RPC request
        rpc_request = JSONRPCRequest(**body)

        # Enforce session requirement for non-initialize requests
        if rpc_request.method != "initialize":
            if session and session.initialized:
                # Session exists and is initialized - check protocol version header
                if not protocol_version:
                    return JSONResponse(
                        content={
                            "error": "MCP-Protocol-Version header required after initialization"
                        },
                        status_code=400,
                    )
            # Note: We allow requests without session for tools/list etc. for flexibility

        # Create session if needed (on initialize)
        if rpc_request.method == "initialize" and not session:
            session = session_manager.create_session()

        # Initialize MCP server
        mcp_server = MCPServer(redis_client)

        # Handle the request
        result = await handle_jsonrpc(rpc_request, mcp_server)

        # Create response
        response_data = create_response(rpc_request.id, result)

        # Add headers
        headers = {}
        if session:
            headers["Mcp-Session-Id"] = session.session_id

        return JSONResponse(
            content=response_data.model_dump(mode="json"), headers=headers
        )

    except json.JSONDecodeError:
        # Parse error
        error = create_error(None, ErrorCode.PARSE_ERROR, "Invalid JSON")
        return JSONResponse(content=error.model_dump(mode="json"), status_code=400)

    except MethodNotFoundError as e:
        # Method not found - use correct error code
        error = create_error(
            body.get("id") if isinstance(body, dict) else None,
            ErrorCode.METHOD_NOT_FOUND,
            str(e),
        )
        return JSONResponse(content=error.model_dump(mode="json"), status_code=400)

    except ValueError as e:
        # Invalid request or params
        error = create_error(
            body.get("id") if isinstance(body, dict) else None,
            ErrorCode.INVALID_PARAMS,
            str(e),
        )
        return JSONResponse(content=error.model_dump(mode="json"), status_code=400)

    except Exception as e:
        # Internal error
        error = create_error(
            body.get("id") if isinstance(body, dict) else None,
            ErrorCode.INTERNAL_ERROR,
            "Internal server error",
            data={"detail": str(e)},
        )
        return JSONResponse(content=error.model_dump(mode="json"), status_code=500)


async def handle_get(
    request: Request, session_id: Optional[str], redis_client: redis.Redis
) -> EventSourceResponse:
    """
    Handle GET request - Optional SSE stream for server messages.

    NOTE: This is optional in the spec. Can be used for server-initiated
    notifications, but not required for basic tool execution.
    """

    async def event_generator():
        """Generate SSE events."""
        # Verify session
        if not session_id:
            yield {
                "event": "error",
                "data": json.dumps({"error": "Session ID required"}),
            }
            return

        session = session_manager.get_session(session_id)
        if not session or not session.initialized:
            yield {
                "event": "error",
                "data": json.dumps({"error": "Invalid or uninitialized session"}),
            }
            return

        # Send connected event
        yield {
            "event": "connected",
            "data": json.dumps({"timestamp": datetime.now().isoformat()}),
        }

        # Keep connection alive with heartbeat
        while True:
            if await request.is_disconnected():
                break

            # Heartbeat every 30 seconds
            await asyncio.sleep(30)
            yield {
                "event": "ping",
                "data": json.dumps({"timestamp": datetime.now().isoformat()}),
            }

    return EventSourceResponse(event_generator())


# =============================================================================
# Legacy endpoints (deprecated - HTTP 410 Gone)
# =============================================================================


@router.get("/tools")
async def get_tools_legacy(redis_client: redis.Redis = Depends(get_redis)):
    """Legacy endpoint - deprecated."""
    return JSONResponse(
        content={
            "deprecated": True,
            "message": "Use POST /mcp with method 'tools/list'",
            "migration_guide": "https://spec.modelcontextprotocol.io/specification/2025-06-18/basic/transports/",
        },
        status_code=410,  # Gone
    )


@router.post("/execute")
async def execute_tool_legacy(request: Request):
    """Legacy endpoint - deprecated."""
    return JSONResponse(
        content={
            "deprecated": True,
            "message": "Use POST /mcp with method 'tools/call'",
            "migration_guide": "https://spec.modelcontextprotocol.io/specification/2025-06-18/basic/transports/",
        },
        status_code=410,  # Gone
    )


@router.get("/sse")
async def mcp_sse_endpoint_legacy(request: Request):
    """Legacy SSE endpoint - deprecated."""
    return JSONResponse(
        content={
            "deprecated": True,
            "message": "Use GET /mcp with Mcp-Session-Id header for SSE streaming",
            "migration_guide": "https://spec.modelcontextprotocol.io/specification/2025-06-18/basic/transports/",
        },
        status_code=410,  # Gone
    )
