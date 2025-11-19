"""Task router for CRUD operations."""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import redis.asyncio as redis

from models import Task, TaskCreate, TaskUpdate, TaskWithTime, TaskFilter, TimeEntry
from database import get_redis
from services.task_service import TaskService
from services.log_service import LogService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=Task, status_code=201)
async def create_task(
    task_data: TaskCreate,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Create a new task."""
    task_service = TaskService(redis_client)
    log_service = LogService(redis_client)
    
    task = await task_service.create_task(task_data)
    
    # Log activity
    await log_service.log_activity(
        f"Task created: {task.title}",
        task_id=task.id,
        metadata={"tags": task.tags}
    )
    
    return task


@router.get("", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = Query(None, pattern="^(pending|in_progress|completed|archived)$"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    redis_client: redis.Redis = Depends(get_redis)
):
    """List all tasks with optional filtering."""
    task_service = TaskService(redis_client)
    
    # Parse tags
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    
    # Build filter
    filters = TaskFilter(
        status=status,
        tags=tag_list,
        created_after=created_after,
        created_before=created_before
    )
    
    tasks = await task_service.list_tasks(filters)
    return tasks


@router.get("/{task_id}", response_model=TaskWithTime)
async def get_task(
    task_id: int,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Get a specific task with time tracking data."""
    task_service = TaskService(redis_client)
    task = await task_service.get_task_with_time(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task


@router.put("/{task_id}", response_model=Task)
async def update_task(
    task_id: int,
    task_data: TaskUpdate,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Update a task."""
    task_service = TaskService(redis_client)
    log_service = LogService(redis_client)
    
    task = await task_service.update_task(task_id, task_data)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Log activity
    changes = []
    if task_data.title:
        changes.append("title")
    if task_data.status:
        changes.append("status")
    if task_data.tags is not None:
        changes.append("tags")
    
    await log_service.log_activity(
        f"Task updated: {', '.join(changes)}",
        task_id=task.id
    )
    
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Delete a task."""
    task_service = TaskService(redis_client)
    log_service = LogService(redis_client)
    
    # Get task title before deletion
    task = await task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    success = await task_service.delete_task(task_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Log activity
    await log_service.log_activity(
        f"Task deleted: {task.title}",
        task_id=task_id
    )


@router.post("/{task_id}/start", response_model=TimeEntry)
async def start_time_tracking(
    task_id: int,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Start time tracking for a task."""
    task_service = TaskService(redis_client)
    log_service = LogService(redis_client)
    
    entry = await task_service.start_time_tracking(task_id)
    
    if not entry:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Log activity
    await log_service.log_activity(
        "Time tracking started",
        task_id=task_id
    )
    
    return entry


@router.post("/{task_id}/stop", response_model=TimeEntry)
async def stop_time_tracking(
    task_id: int,
    redis_client: redis.Redis = Depends(get_redis)
):
    """Stop time tracking for a task."""
    task_service = TaskService(redis_client)
    log_service = LogService(redis_client)
    
    entry = await task_service.stop_time_tracking(task_id)
    
    if not entry:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Log activity
    duration_str = f"{entry.duration:.2f}s" if entry.duration else "N/A"
    await log_service.log_activity(
        f"Time tracking stopped (duration: {duration_str})",
        task_id=task_id,
        metadata={"duration": entry.duration}
    )
    
    return entry
