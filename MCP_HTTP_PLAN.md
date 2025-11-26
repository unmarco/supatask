# MCP HTTP Streamable Transport - Implementation Plan

## Problem Statement

Claude Code MCP client hangs when connecting to the current SSE-based MCP implementation. The deprecated HTTP+SSE transport needs to be replaced with the modern **Streamable HTTP** transport (MCP spec 2025-06-18).

## Current Implementation Issues

- **Endpoint**: `GET /mcp/sse` with continuous SSE heartbeat
- **Protocol**: Custom JSON format instead of JSON-RPC 2.0
- **Architecture**: Separate endpoints (`/mcp/tools`, `/mcp/execute`, `/mcp/sse`)
- **Problem**: SSE connection hangs with Claude Code MCP client

## Target Architecture

### MCP Streamable HTTP Specification (2025-06-18)

**Single Endpoint**: `/mcp`
- Supports both `POST` (client→server) and `GET` (server→client streaming)
- Uses JSON-RPC 2.0 message format
- Session management via `Mcp-Session-Id` headers
- Optional SSE for server-initiated messages

**Protocol**: JSON-RPC 2.0
- All messages use standard JSON-RPC 2.0 format
- Request/Response correlation via `id` field
- Notifications (no `id` field, no response expected)

**Required Headers**:
- `MCP-Protocol-Version`: Protocol version (e.g., `2025-06-18`) - required after initialization
- `Mcp-Session-Id`: Session identifier - required after initialization
- `Accept`: Must include `application/json` and optionally `text/event-stream`

## Implementation Plan

### Phase 1: JSON-RPC 2.0 Message Layer (2 hours)

#### 1.1 Create JSON-RPC Models

**File**: `backend/mcp/jsonrpc.py` (new)

```python
from typing import Any, Optional, Union, Literal
from pydantic import BaseModel, Field

class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 Request"""
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Optional[dict[str, Any]] = None
    id: Optional[Union[str, int]] = None

class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 Success Response"""
    jsonrpc: Literal["2.0"] = "2.0"
    result: Any
    id: Union[str, int, None]

class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 Error object"""
    code: int
    message: str
    data: Optional[Any] = None

class JSONRPCErrorResponse(BaseModel):
    """JSON-RPC 2.0 Error Response"""
    jsonrpc: Literal["2.0"] = "2.0"
    error: JSONRPCError
    id: Union[str, int, None]

# Error codes (JSON-RPC standard + MCP extensions)
class ErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
```

#### 1.2 Create JSON-RPC Handler

**File**: `backend/mcp/handler.py` (new)

```python
from typing import Any, Optional
from .jsonrpc import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    JSONRPCError,
    ErrorCode
)

def create_response(id: Any, result: Any) -> JSONRPCResponse:
    """Create a successful JSON-RPC response"""
    return JSONRPCResponse(jsonrpc="2.0", result=result, id=id)

def create_error(
    id: Any,
    code: int,
    message: str,
    data: Optional[Any] = None
) -> JSONRPCErrorResponse:
    """Create a JSON-RPC error response"""
    error = JSONRPCError(code=code, message=message, data=data)
    return JSONRPCErrorResponse(jsonrpc="2.0", error=error, id=id)

class MethodNotFoundError(Exception):
    """Raised when an unknown method is called"""
    pass

async def handle_jsonrpc(request: JSONRPCRequest, mcp_server) -> dict:
    """
    Handle JSON-RPC request and route to appropriate MCP method

    Returns dict (will be converted to JSONRPCResponse or JSONRPCErrorResponse)
    """
    try:
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

    except Exception as e:
        # Will be caught by router and converted to error response
        raise

async def handle_initialize(params: dict, mcp_server) -> dict:
    """Handle initialize request"""
    # MCP initialization handshake
    return {
        "protocolVersion": "2025-06-18",
        "capabilities": {
            "tools": {},
        },
        "serverInfo": {
            "name": "supatask-mcp",
            "version": "1.0.0"
        }
    }

async def handle_tools_list(mcp_server) -> dict:
    """Handle tools/list request"""
    tools = mcp_server.get_tools_schema()
    return {"tools": tools}

async def handle_tools_call(params: dict, mcp_server) -> dict:
    """
    Handle tools/call request

    Returns MCP CallToolResult format:
    {
        "content": [{"type": "text", "text": "..."}],
        "isError": false
    }
    """
    import json as _json

    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        raise ValueError("Missing tool name")

    result = await mcp_server.execute_tool(tool_name, arguments)

    # Wrap result in MCP CallToolResult format
    is_error = not result.get("success", True)
    text_content = _json.dumps(result, default=str)

    return {
        "content": [{"type": "text", "text": text_content}],
        "isError": is_error
    }
```

### Phase 2: Session Management (1 hour)

#### 2.1 Session Store

**File**: `backend/mcp/sessions.py` (new)

```python
from typing import Optional, Dict
from datetime import datetime, timedelta
import secrets

class Session:
    """MCP Session"""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.initialized = False

    def touch(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()

    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if session has expired"""
        expiry = self.last_activity + timedelta(minutes=timeout_minutes)
        return datetime.now() > expiry

class SessionManager:
    """Manage MCP sessions"""
    def __init__(self):
        self.sessions: Dict[str, Session] = {}

    def create_session(self) -> Session:
        """Create a new session"""
        session_id = secrets.token_urlsafe(32)
        session = Session(session_id)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        session = self.sessions.get(session_id)
        if session and not session.is_expired():
            session.touch()
            return session
        elif session:
            # Clean up expired session
            del self.sessions[session_id]
        return None

    def cleanup_expired(self):
        """Remove expired sessions"""
        expired = [
            sid for sid, session in self.sessions.items()
            if session.is_expired()
        ]
        for sid in expired:
            del self.sessions[sid]

# Global session manager
session_manager = SessionManager()
```

### Phase 3: New MCP Endpoint (2 hours)

#### 3.1 Refactor MCP Router

**File**: `backend/routers/mcp.py` (refactor)

```python
"""MCP (Model Context Protocol) router - HTTP Streamable Transport"""
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

# Import new MCP modules
from mcp.jsonrpc import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    ErrorCode
)
from mcp.handler import (
    handle_jsonrpc,
    create_response,
    create_error,
    MethodNotFoundError
)
from mcp.sessions import session_manager

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPServer:
    """MCP Server implementation (existing class - keep tools logic)"""

    def __init__(self, redis_client: redis.Redis):
        self.task_service = TaskService(redis_client)
        self.log_service = LogService(redis_client)

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Get MCP tools schema (existing method - keep as is)"""
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
                            "enum": ["pending", "in_progress", "completed", "archived"]
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["title"]
                }
            },
            # ... rest of tools (keep existing)
        ]

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool (existing method - keep logic, adjust logging)"""
        # Keep existing implementation
        # ... (all the tool execution logic)
        pass


SUPPORTED_PROTOCOL_VERSION = "2025-06-18"

@router.api_route("/", methods=["POST", "GET"])
async def mcp_endpoint(
    request: Request,
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    mcp_protocol_version: Optional[str] = Header(None, alias="MCP-Protocol-Version"),
    redis_client: redis.Redis = Depends(get_redis)
):
    """
    MCP Streamable HTTP endpoint (2025-06-18 spec)

    POST: Client sends JSON-RPC requests
    GET: Optional SSE stream for server-initiated messages
    """

    # Validate protocol version if provided (required after initialization)
    if mcp_protocol_version and mcp_protocol_version != SUPPORTED_PROTOCOL_VERSION:
        return JSONResponse(
            content={"error": f"Unsupported protocol version. Supported: {SUPPORTED_PROTOCOL_VERSION}"},
            status_code=400
        )

    if request.method == "POST":
        return await handle_post(request, mcp_session_id, mcp_protocol_version, redis_client)
    else:  # GET
        return await handle_get(request, mcp_session_id, redis_client)


async def handle_post(
    request: Request,
    session_id: Optional[str],
    protocol_version: Optional[str],
    redis_client: redis.Redis
) -> Response:
    """Handle POST request - JSON-RPC message from client"""

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
                    content={"error": "Session not found or expired"},
                    status_code=404
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
                        content={"error": "MCP-Protocol-Version header required after initialization"},
                        status_code=400
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
            content=response_data.model_dump(mode="json"),
            headers=headers
        )

    except json.JSONDecodeError:
        # Parse error
        error = create_error(
            None,
            ErrorCode.PARSE_ERROR,
            "Invalid JSON"
        )
        return JSONResponse(
            content=error.model_dump(mode="json"),
            status_code=400
        )

    except MethodNotFoundError as e:
        # Method not found - use correct error code
        error = create_error(
            body.get("id") if isinstance(body, dict) else None,
            ErrorCode.METHOD_NOT_FOUND,
            str(e)
        )
        return JSONResponse(
            content=error.model_dump(mode="json"),
            status_code=400
        )

    except ValueError as e:
        # Invalid request or params
        error = create_error(
            body.get("id") if isinstance(body, dict) else None,
            ErrorCode.INVALID_PARAMS,
            str(e)
        )
        return JSONResponse(
            content=error.model_dump(mode="json"),
            status_code=400
        )

    except Exception as e:
        # Internal error
        error = create_error(
            body.get("id") if isinstance(body, dict) else None,
            ErrorCode.INTERNAL_ERROR,
            "Internal server error",
            data={"detail": str(e)}
        )
        return JSONResponse(
            content=error.model_dump(mode="json"),
            status_code=500
        )


async def handle_get(
    request: Request,
    session_id: Optional[str],
    redis_client: redis.Redis
) -> EventSourceResponse:
    """
    Handle GET request - Optional SSE stream for server messages

    NOTE: This is optional in the spec. Can be used for server-initiated
    notifications, but not required for basic tool execution.
    """

    async def event_generator():
        """Generate SSE events"""

        # Verify session
        if not session_id:
            yield {
                "event": "error",
                "data": json.dumps({"error": "Session ID required"})
            }
            return

        session = session_manager.get_session(session_id)
        if not session or not session.initialized:
            yield {
                "event": "error",
                "data": json.dumps({"error": "Invalid or uninitialized session"})
            }
            return

        # Send connected event
        yield {
            "event": "connected",
            "data": json.dumps({"timestamp": datetime.now().isoformat()})
        }

        # Keep connection alive with heartbeat
        import asyncio
        while True:
            if await request.is_disconnected():
                break

            # Heartbeat every 30 seconds
            await asyncio.sleep(30)
            yield {
                "event": "ping",
                "data": json.dumps({"timestamp": datetime.now().isoformat()})
            }

    return EventSourceResponse(event_generator())


# Legacy endpoints (optional - for backward compatibility during transition)
@router.get("/tools")
async def get_tools_legacy(redis_client: redis.Redis = Depends(get_redis)):
    """Legacy endpoint - redirects to new format"""
    return JSONResponse(
        content={
            "deprecated": True,
            "message": "Use POST /mcp with method 'tools/list'",
            "migration_guide": "https://spec.modelcontextprotocol.io/specification/2025-06-18/basic/transports/"
        },
        status_code=410  # Gone
    )


@router.post("/execute")
async def execute_tool_legacy(request: Request):
    """Legacy endpoint - redirects to new format"""
    return JSONResponse(
        content={
            "deprecated": True,
            "message": "Use POST /mcp with method 'tools/call'",
            "migration_guide": "https://spec.modelcontextprotocol.io/specification/2025-06-18/basic/transports/"
        },
        status_code=410  # Gone
    )
```

### Phase 4: Directory Structure (15 minutes)

Create new MCP module structure:

```
backend/
├── mcp/                      # New MCP module
│   ├── __init__.py
│   ├── jsonrpc.py           # JSON-RPC 2.0 models
│   ├── handler.py           # Request handler
│   └── sessions.py          # Session management
├── routers/
│   └── mcp.py               # Refactored router
```

### Phase 5: Testing & Validation (2 hours)

#### 5.1 Unit Tests

**File**: `backend/tests/test_mcp_http.py` (new)

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_initialize():
    """Test MCP initialize handshake"""
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        },
        "id": 1
    })

    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert "result" in data
    assert data["result"]["protocolVersion"] == "2025-06-18"

    # Session ID should be in headers
    assert "Mcp-Session-Id" in response.headers

def test_tools_list():
    """Test tools/list method"""
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 2
    })

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "tools" in data["result"]
    assert len(data["result"]["tools"]) > 0

def test_tools_call_create_task():
    """Test tools/call with create_task - returns CallToolResult format"""
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "create_task",
            "arguments": {
                "title": "Test Task",
                "description": "Testing MCP HTTP",
                "tags": ["test"]
            }
        },
        "id": 3
    })

    assert response.status_code == 200
    data = response.json()
    assert "result" in data

    # Verify CallToolResult format
    result = data["result"]
    assert "content" in result
    assert "isError" in result
    assert result["isError"] == False
    assert len(result["content"]) > 0
    assert result["content"][0]["type"] == "text"

    # Parse the text content to verify task data
    import json
    content_data = json.loads(result["content"][0]["text"])
    assert content_data["success"] == True
    assert "task" in content_data

def test_notifications_initialized():
    """Test notifications/initialized returns 202 Accepted"""
    # First initialize to get session
    init_response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        },
        "id": 1
    })
    session_id = init_response.headers.get("Mcp-Session-Id")

    # Send initialized notification (no id field)
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
            # Note: no "id" field - this is a notification
        },
        headers={"Mcp-Session-Id": session_id}
    )

    assert response.status_code == 202

def test_invalid_json():
    """Test invalid JSON handling"""
    response = client.post(
        "/mcp",
        data="invalid json",
        headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32700  # Parse error

def test_method_not_found():
    """Test unknown method handling - returns METHOD_NOT_FOUND error"""
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "method": "unknown/method",
        "id": 4
    })

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32601  # METHOD_NOT_FOUND

def test_session_expired_returns_404():
    """Test that expired/invalid session returns 404"""
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 5
        },
        headers={"Mcp-Session-Id": "invalid-session-id"}
    )

    assert response.status_code == 404
```

#### 5.2 Manual Testing with Claude Code

**Test Configuration**: `~/.config/claude-code/mcp.json`

```json
{
  "mcpServers": {
    "supatask": {
      "url": "http://localhost:8000/mcp",
      "transport": "http"
    }
  }
}
```

**Test Commands**:
```bash
# 1. Start the server
docker compose up -d --build

# 2. Initialize and capture session ID
SESSION_ID=$(curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -D - \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-06-18",
      "capabilities": {},
      "clientInfo": {"name": "curl", "version": "1.0"}
    },
    "id": 1
  }' 2>&1 | grep -i "mcp-session-id" | cut -d: -f2 | tr -d ' \r')

echo "Session ID: $SESSION_ID"

# 3. Send initialized notification (required after initialize)
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "method": "notifications/initialized"
  }'
# Expected: HTTP 202 Accepted (no body)

# 4. List tools (with session and protocol version headers)
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -H "MCP-Protocol-Version: 2025-06-18" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 2
  }'

# 5. Call create_task tool
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -H "MCP-Protocol-Version: 2025-06-18" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "create_task",
      "arguments": {
        "title": "Test via MCP HTTP",
        "tags": ["mcp", "http"]
      }
    },
    "id": 3
  }'
# Expected response format (CallToolResult):
# {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"{...}"}],"isError":false}}
```

### Phase 6: Documentation Updates (30 minutes)

#### 6.1 Update WALKTHROUGH.md

Add section on new HTTP transport:

```markdown
### MCP Server - HTTP Streamable Transport ✅

Implements MCP specification 2025-06-18 with HTTP Streamable transport.

**Endpoint**: `POST /mcp` (single unified endpoint)

**Protocol**: JSON-RPC 2.0

**Features**:
- Session management via `Mcp-Session-Id` headers
- Standard JSON-RPC 2.0 request/response format
- Optional SSE streaming for server-initiated messages
- Compatible with Claude Code MCP client

**Example Usage**:

```bash
# Initialize connection
POST /mcp
{
  "jsonrpc": "2.0",
  "method": "initialize",
  "params": {"protocolVersion": "2025-06-18", ...},
  "id": 1
}

# List available tools
POST /mcp
{
  "jsonrpc": "2.0",
  "method": "tools/list",
  "id": 2
}

# Execute a tool
POST /mcp
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "create_task",
    "arguments": {"title": "My Task", "tags": ["work"]}
  },
  "id": 3
}
```
```

#### 6.2 Create MCP Integration Guide

**File**: `docs/MCP_INTEGRATION.md` (new)

```markdown
# MCP Integration Guide

## Connecting with Claude Code

1. Add to `~/.config/claude-code/mcp.json`:

```json
{
  "mcpServers": {
    "supatask": {
      "url": "http://localhost:8000/mcp",
      "transport": "http"
    }
  }
}
```

2. Restart Claude Code

3. Available tools will appear automatically

## Available Tools

- `create_task` - Create new tasks
- `read_task` - Get task details
- `list_tasks` - List tasks with filters
- `update_task` - Update task fields
- `delete_task` - Delete tasks
- `get_logs` - Retrieve activity logs

## Protocol Details

- **Specification**: MCP 2025-06-18
- **Transport**: HTTP Streamable
- **Message Format**: JSON-RPC 2.0
- **Session Management**: Via `Mcp-Session-Id` headers
```

## Timeline

| Phase | Task | Time | Total |
|-------|------|------|-------|
| 1 | JSON-RPC 2.0 Models & Handler | 2h | 2h |
| 2 | Session Management | 1h | 3h |
| 3 | Refactor MCP Router | 2h | 5h |
| 4 | Directory Structure | 15m | 5.25h |
| 5 | Testing & Validation | 2h | 7.25h |
| 6 | Documentation | 30m | **7.75h** |

**Total Estimated Time**: ~8 hours

## Migration Strategy

### Option A: Clean Cut (Recommended)
1. Implement new `/mcp` endpoint with HTTP transport
2. Mark old endpoints (`/mcp/tools`, `/mcp/execute`, `/mcp/sse`) as deprecated (HTTP 410)
3. Remove old endpoints in next version

### Option B: Parallel Support
1. Keep both old and new endpoints
2. Gradually migrate clients
3. Remove old endpoints after deprecation period

## Success Criteria

- ✅ Claude Code MCP client connects without hanging
- ✅ All 6 tools are discoverable and executable
- ✅ JSON-RPC 2.0 request/response format validated
- ✅ Session management working correctly
- ✅ Error handling returns proper JSON-RPC errors
- ✅ Unit tests pass with 100% coverage
- ✅ Manual testing with Claude Code successful

## Dependencies

**New Python Packages**: None (uses existing FastAPI, Pydantic)

**Existing Dependencies**:
- FastAPI
- Pydantic
- redis.asyncio
- sse-starlette (optional, for GET endpoint)

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing clients | High | Implement both endpoints during transition |
| Session management complexity | Medium | Simple in-memory store initially |
| JSON-RPC parsing errors | Low | Use Pydantic validation |
| SSE still needed for notifications | Low | Keep GET endpoint optional |

## Next Steps After Implementation

1. Monitor Claude Code connection stability
2. Add Prometheus metrics for MCP endpoint usage
3. Consider Redis-backed session store for multi-instance deployment
4. Add WebSocket transport option (future MCP spec)

---

## Spec Compliance Checklist

The following items ensure full compliance with MCP specification 2025-06-18:

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Single `/mcp` endpoint | ✅ | `@router.api_route("/", methods=["POST", "GET"])` |
| JSON-RPC 2.0 format | ✅ | `JSONRPCRequest`, `JSONRPCResponse` models |
| `Mcp-Session-Id` header | ✅ | Session management in `handle_post` |
| `MCP-Protocol-Version` header | ✅ | Validated in endpoint, required after init |
| `initialize` → response with capabilities | ✅ | `handle_initialize()` returns serverInfo |
| `notifications/initialized` handling | ✅ | Returns HTTP 202 Accepted |
| `tools/list` → ListToolsResult | ✅ | Returns `{"tools": [...]}` |
| `tools/call` → CallToolResult | ✅ | Returns `{"content": [...], "isError": bool}` |
| `ping` → empty result | ✅ | Returns `{}` |
| Error code `-32601` for unknown method | ✅ | `MethodNotFoundError` + `ErrorCode.METHOD_NOT_FOUND` |
| Error code `-32700` for parse error | ✅ | `ErrorCode.PARSE_ERROR` |
| Error code `-32602` for invalid params | ✅ | `ErrorCode.INVALID_PARAMS` |
| HTTP 404 for terminated session | ✅ | Returned when session not found |
| HTTP 400 for missing session after init | ✅ | Enforced for initialized sessions |
| HTTP 202 for accepted notifications | ✅ | All notifications return 202 |

---

**Status**: Ready for implementation
**Priority**: High (blocks Claude Code integration)
**Estimated Effort**: 1 development day
