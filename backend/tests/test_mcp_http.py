"""Tests for MCP HTTP Streamable Transport."""

import json
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Import the app
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from mcp.sessions import session_manager


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear sessions before each test."""
    session_manager.sessions.clear()
    yield
    session_manager.sessions.clear()


class TestMCPInitialize:
    """Test MCP initialize endpoint."""

    def test_initialize_success(self, client):
        """Test successful MCP initialization."""
        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
                "id": 1,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2025-06-18"
        assert "serverInfo" in data["result"]
        assert data["result"]["serverInfo"]["name"] == "supatask-mcp"

        # Session ID should be in headers
        assert "mcp-session-id" in response.headers

    def test_initialize_creates_session(self, client):
        """Test that initialize creates a session."""
        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
                "id": 1,
            },
        )

        assert response.status_code == 200
        session_id = response.headers.get("mcp-session-id")
        assert session_id is not None
        assert session_id in session_manager.sessions


class TestMCPNotifications:
    """Test MCP notification handling."""

    def test_notifications_initialized_returns_202(self, client):
        """Test notifications/initialized returns 202 Accepted."""
        # First initialize to get session
        init_response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
                "id": 1,
            },
        )
        session_id = init_response.headers.get("mcp-session-id")

        # Send initialized notification (no id field)
        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                # Note: no "id" field - this is a notification
            },
            headers={"Mcp-Session-Id": session_id},
        )

        assert response.status_code == 202

    def test_unknown_notification_returns_202(self, client):
        """Test unknown notifications still return 202."""
        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/unknown",
                # No id field
            },
        )

        assert response.status_code == 202


class TestMCPToolsList:
    """Test tools/list method."""

    def test_tools_list_success(self, client):
        """Test tools/list returns available tools."""
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert "tools" in data["result"]
        assert len(data["result"]["tools"]) > 0

        # Verify tool structure
        tool_names = [t["name"] for t in data["result"]["tools"]]
        assert "create_task" in tool_names
        assert "read_task" in tool_names
        assert "list_tasks" in tool_names


class TestMCPToolsCall:
    """Test tools/call method."""

    @patch("routers.mcp.MCPServer.execute_tool")
    def test_tools_call_returns_call_tool_result_format(self, mock_execute, client):
        """Test tools/call returns CallToolResult format."""
        mock_execute.return_value = {"success": True, "task": {"id": 1, "title": "Test"}}

        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "create_task",
                    "arguments": {"title": "Test Task", "tags": ["test"]},
                },
                "id": 3,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data

        # Verify CallToolResult format
        result = data["result"]
        assert "content" in result
        assert "isError" in result
        assert result["isError"] is False
        assert len(result["content"]) > 0
        assert result["content"][0]["type"] == "text"

        # Parse the text content to verify task data
        content_data = json.loads(result["content"][0]["text"])
        assert content_data["success"] is True

    @patch("routers.mcp.MCPServer.execute_tool")
    def test_tools_call_error_sets_is_error_true(self, mock_execute, client):
        """Test tools/call sets isError=true on failure."""
        mock_execute.return_value = {"success": False, "error": "Task not found"}

        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "read_task", "arguments": {"task_id": 999}},
                "id": 4,
            },
        )

        assert response.status_code == 200
        data = response.json()
        result = data["result"]
        assert result["isError"] is True

    def test_tools_call_missing_name(self, client):
        """Test tools/call with missing tool name."""
        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"arguments": {}},
                "id": 5,
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32602  # INVALID_PARAMS


class TestMCPErrorHandling:
    """Test error handling."""

    def test_invalid_json_returns_parse_error(self, client):
        """Test invalid JSON returns parse error."""
        response = client.post(
            "/mcp/",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32700  # PARSE_ERROR

    def test_method_not_found(self, client):
        """Test unknown method returns METHOD_NOT_FOUND error."""
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "unknown/method", "id": 6},
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601  # METHOD_NOT_FOUND

    def test_ping_returns_empty_result(self, client):
        """Test ping method returns empty result."""
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "ping", "id": 7},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result"] == {}


class TestMCPSessionManagement:
    """Test session management."""

    def test_invalid_session_returns_404(self, client):
        """Test that invalid session returns 404."""
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 8},
            headers={"Mcp-Session-Id": "invalid-session-id"},
        )

        assert response.status_code == 404

    def test_unsupported_protocol_version_returns_400(self, client):
        """Test unsupported protocol version returns 400."""
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 9},
            headers={"MCP-Protocol-Version": "1999-01-01"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported protocol version" in data["error"]


class TestMCPLegacyEndpoints:
    """Test legacy endpoint deprecation."""

    def test_legacy_tools_returns_410(self, client):
        """Test legacy /tools endpoint returns 410 Gone."""
        response = client.get("/mcp/tools")

        assert response.status_code == 410
        data = response.json()
        assert data["deprecated"] is True

    def test_legacy_execute_returns_410(self, client):
        """Test legacy /execute endpoint returns 410 Gone."""
        response = client.post("/mcp/execute", json={})

        assert response.status_code == 410
        data = response.json()
        assert data["deprecated"] is True

    def test_legacy_sse_returns_410(self, client):
        """Test legacy /sse endpoint returns 410 Gone."""
        response = client.get("/mcp/sse")

        assert response.status_code == 410
        data = response.json()
        assert data["deprecated"] is True
