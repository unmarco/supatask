"""Pydantic models for request/response schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class TaskBase(BaseModel):
    """Base task schema."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = Field(default="pending", pattern="^(pending|in_progress|completed|archived)$")
    tags: List[str] = Field(default_factory=list)


class TaskCreate(TaskBase):
    """Schema for creating a task."""
    pass


class TaskUpdate(BaseModel):
    """Schema for updating a task."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(pending|in_progress|completed|archived)$")
    tags: Optional[List[str]] = None


class Task(TaskBase):
    """Full task schema with metadata."""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TimeEntry(BaseModel):
    """Time tracking entry."""
    task_id: int
    action: str  # "start" or "stop"
    timestamp: datetime
    duration: Optional[float] = None  # Duration in seconds (only for "stop")


class TaskWithTime(Task):
    """Task with time tracking information."""
    time_entries: List[TimeEntry] = []
    total_time: float = 0.0  # Total time in seconds


class LogEntry(BaseModel):
    """Log entry schema."""
    timestamp: datetime
    level: str
    message: str
    task_id: Optional[int] = None
    metadata: Optional[dict] = None


class TaskFilter(BaseModel):
    """Filter parameters for tasks."""
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class LogFilter(BaseModel):
    """Filter parameters for logs."""
    log_type: str = Field(default="activity", pattern="^(activity|system)$")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=100, le=1000)
