"""MCP (Model Context Protocol) router for AI assistant integration."""
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as redis

from models import TaskCreate, TaskUpdate, LogFilter, TaskFilter
from database import get_redis
from services.task_service import TaskService
from services.log_service import LogService

router = APIRouter(prefix="/mcp", tags=["mcp"])


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
            {
                "name": "read_task",
                "description": "Read a task by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"}
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "list_tasks",
                "description": "List tasks with optional filters",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "archived"]
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "created_after": {"type": "string", "format": "date-time"},
                        "created_before": {"type": "string", "format": "date-time"}
                    }
                }
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
                            "enum": ["pending", "in_progress", "completed", "archived"]
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "delete_task",
                "description": "Delete a task",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"}
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "get_logs",
                "description": "Get activity or system logs",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "log_type": {
                            "type": "string",
                            "enum": ["activity", "system"]
                        },
                        "start_time": {"type": "string", "format": "date-time"},
                        "end_time": {"type": "string", "format": "date-time"},
                        "limit": {"type": "integer", "maximum": 1000}
                    }
                }
            }
        ]
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool."""
        try:
            if tool_name == "create_task":
                task_data = TaskCreate(**arguments)
                task = await self.task_service.create_task(task_data)
                await self.log_service.log_activity(
                    f"Task created via MCP: {task.title}",
                    task_id=task.id
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
                    arguments["created_after"] = datetime.fromisoformat(arguments["created_after"])
                if "created_before" in arguments:
                    arguments["created_before"] = datetime.fromisoformat(arguments["created_before"])
                
                filters = TaskFilter(**arguments)
                tasks = await self.task_service.list_tasks(filters)
                return {
                    "success": True,
                    "tasks": [task.model_dump(mode="json") for task in tasks]
                }
            
            elif tool_name == "update_task":
                task_id = arguments.pop("task_id")
                update_data = TaskUpdate(**arguments)
                task = await self.task_service.update_task(task_id, update_data)
                if not task:
                    return {"success": False, "error": "Task not found"}
                await self.log_service.log_activity(
                    f"Task updated via MCP",
                    task_id=task.id
                )
                return {"success": True, "task": task.model_dump(mode="json")}
            
            elif tool_name == "delete_task":
                success = await self.task_service.delete_task(arguments["task_id"])
                if not success:
                    return {"success": False, "error": "Task not found"}
                await self.log_service.log_activity(
                    "Task deleted via MCP",
                    task_id=arguments["task_id"]
                )
                return {"success": True}
            
            elif tool_name == "get_logs":
                # Parse datetime strings
                if "start_time" in arguments:
                    arguments["start_time"] = datetime.fromisoformat(arguments["start_time"])
                if "end_time" in arguments:
                    arguments["end_time"] = datetime.fromisoformat(arguments["end_time"])
                
                filters = LogFilter(**arguments)
                logs = await self.log_service.get_logs(filters)
                return {
                    "success": True,
                    "logs": [log.model_dump(mode="json") for log in logs]
                }
            
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}


@router.get("/tools")
async def get_tools(redis_client: redis.Redis = Depends(get_redis)):
    """Get available MCP tools."""
    mcp = MCPServer(redis_client)
    return {"tools": mcp.get_tools_schema()}


@router.post("/execute")
async def execute_tool(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Execute an MCP tool."""
    data = await request.json()
    tool_name = data.get("tool")
    arguments = data.get("arguments", {})
    
    mcp = MCPServer(redis_client)
    result = await mcp.execute_tool(tool_name, arguments)
    
    return result


@router.get("/sse")
async def mcp_sse_endpoint(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis)
):
    """SSE endpoint for MCP protocol."""
    async def event_generator():
        mcp = MCPServer(redis_client)
        
        # Send initial tools list
        yield {
            "event": "tools",
            "data": json.dumps({"tools": mcp.get_tools_schema()})
        }
        
        # Keep connection alive with heartbeat
        while True:
            if await request.is_disconnected():
                break
            
            # Send heartbeat every 30 seconds
            import asyncio
            await asyncio.sleep(30)
            yield {
                "event": "heartbeat",
                "data": json.dumps({"timestamp": datetime.now().isoformat()})
            }
    
    return EventSourceResponse(event_generator())
