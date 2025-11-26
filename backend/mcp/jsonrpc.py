"""JSON-RPC 2.0 models for MCP protocol."""

from typing import Any, Optional, Union, Literal
from pydantic import BaseModel


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 Request."""

    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Optional[dict[str, Any]] = None
    id: Optional[Union[str, int]] = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 Success Response."""

    jsonrpc: Literal["2.0"] = "2.0"
    result: Any
    id: Union[str, int, None]


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 Error object."""

    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCErrorResponse(BaseModel):
    """JSON-RPC 2.0 Error Response."""

    jsonrpc: Literal["2.0"] = "2.0"
    error: JSONRPCError
    id: Union[str, int, None]


class ErrorCode:
    """JSON-RPC 2.0 standard error codes and MCP extensions."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
