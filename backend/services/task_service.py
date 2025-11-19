"""Service layer for task operations."""
import json
from datetime import datetime
from typing import List, Optional
import redis.asyncio as redis
from models import Task, TaskCreate, TaskUpdate, TimeEntry, TaskWithTime, TaskFilter
from database import RedisKeys


class TaskService:
    """Service for task CRUD operations."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def create_task(self, task_data: TaskCreate) -> Task:
        """Create a new task."""
        # Get next task ID
        task_id = await self.redis.incr(RedisKeys.TASK_NEXT_ID)
        
        # Create timestamp
        now = datetime.now()
        
        # Store task data
        task_dict = {
            "id": task_id,
            "title": task_data.title,
            "description": task_data.description or "",
            "status": task_data.status,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        
        # Use pipeline for atomicity
        async with self.redis.pipeline() as pipe:
            # Store task hash
            await pipe.hset(RedisKeys.task(task_id), mapping=task_dict)
            
            # Add to tasks set
            await pipe.sadd(RedisKeys.tasks_set(), task_id)
            
            # Add to status index
            await pipe.sadd(RedisKeys.tasks_by_status(task_data.status), task_id)
            
            # Store tags
            if task_data.tags:
                await pipe.sadd(RedisKeys.task_tags(task_id), *task_data.tags)
            
            await pipe.execute()
        
        return Task(**task_dict, tags=task_data.tags)
    
    async def get_task(self, task_id: int) -> Optional[Task]:
        """Get a task by ID."""
        task_data = await self.redis.hgetall(RedisKeys.task(task_id))
        
        if not task_data:
            return None
        
        # Get tags
        tags = list(await self.redis.smembers(RedisKeys.task_tags(task_id)))
        
        return Task(
            id=int(task_data["id"]),
            title=task_data["title"],
            description=task_data.get("description", ""),
            status=task_data["status"],
            tags=tags,
            created_at=datetime.fromisoformat(task_data["created_at"]),
            updated_at=datetime.fromisoformat(task_data["updated_at"]),
        )
    
    async def list_tasks(self, filters: Optional[TaskFilter] = None) -> List[Task]:
        """List all tasks with optional filtering."""
        # Get base set of task IDs
        if filters and filters.status:
            task_ids = await self.redis.smembers(RedisKeys.tasks_by_status(filters.status))
        else:
            task_ids = await self.redis.smembers(RedisKeys.tasks_set())
        
        tasks = []
        for task_id in task_ids:
            task = await self.get_task(int(task_id))
            if task:
                # Apply filters
                if filters:
                    # Tag filter
                    if filters.tags and not any(tag in task.tags for tag in filters.tags):
                        continue
                    
                    # Date range filters
                    if filters.created_after and task.created_at < filters.created_after:
                        continue
                    if filters.created_before and task.created_at > filters.created_before:
                        continue
                
                tasks.append(task)
        
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)
    
    async def update_task(self, task_id: int, task_data: TaskUpdate) -> Optional[Task]:
        """Update a task."""
        # Get existing task
        existing = await self.get_task(task_id)
        if not existing:
            return None
        
        # Prepare update data
        update_dict = {}
        old_status = existing.status
        
        if task_data.title is not None:
            update_dict["title"] = task_data.title
        if task_data.description is not None:
            update_dict["description"] = task_data.description
        if task_data.status is not None:
            update_dict["status"] = task_data.status
        
        update_dict["updated_at"] = datetime.now().isoformat()
        
        async with self.redis.pipeline() as pipe:
            # Update task hash
            if update_dict:
                await pipe.hset(RedisKeys.task(task_id), mapping=update_dict)
            
            # Update status index if status changed
            if task_data.status and task_data.status != old_status:
                await pipe.srem(RedisKeys.tasks_by_status(old_status), task_id)
                await pipe.sadd(RedisKeys.tasks_by_status(task_data.status), task_id)
            
            # Update tags if provided
            if task_data.tags is not None:
                await pipe.delete(RedisKeys.task_tags(task_id))
                if task_data.tags:
                    await pipe.sadd(RedisKeys.task_tags(task_id), *task_data.tags)
            
            await pipe.execute()
        
        return await self.get_task(task_id)
    
    async def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        task = await self.get_task(task_id)
        if not task:
            return False
        
        async with self.redis.pipeline() as pipe:
            # Remove from all sets and indices
            await pipe.srem(RedisKeys.tasks_set(), task_id)
            await pipe.srem(RedisKeys.tasks_by_status(task.status), task_id)
            
            # Delete task data
            await pipe.delete(RedisKeys.task(task_id))
            await pipe.delete(RedisKeys.task_tags(task_id))
            await pipe.delete(RedisKeys.task_time(task_id))
            
            await pipe.execute()
        
        return True
    
    async def start_time_tracking(self, task_id: int) -> Optional[TimeEntry]:
        """Start time tracking for a task."""
        task = await self.get_task(task_id)
        if not task:
            return None
        
        entry = TimeEntry(
            task_id=task_id,
            action="start",
            timestamp=datetime.now()
        )
        
        # Store in Redis stream
        await self.redis.xadd(
            RedisKeys.task_time(task_id),
            {"action": "start", "timestamp": entry.timestamp.isoformat()}
        )
        
        return entry
    
    async def stop_time_tracking(self, task_id: int) -> Optional[TimeEntry]:
        """Stop time tracking for a task."""
        task = await self.get_task(task_id)
        if not task:
            return None
        
        # Get last entry
        entries = await self.redis.xrevrange(RedisKeys.task_time(task_id), count=1)
        
        duration = None
        if entries:
            last_entry = entries[0][1]
            if last_entry.get("action") == "start":
                start_time = datetime.fromisoformat(last_entry["timestamp"])
                duration = (datetime.now() - start_time).total_seconds()
        
        entry = TimeEntry(
            task_id=task_id,
            action="stop",
            timestamp=datetime.now(),
            duration=duration
        )
        
        # Store in Redis stream
        await self.redis.xadd(
            RedisKeys.task_time(task_id),
            {
                "action": "stop",
                "timestamp": entry.timestamp.isoformat(),
                "duration": str(duration) if duration else "0"
            }
        )
        
        return entry
    
    async def get_task_with_time(self, task_id: int) -> Optional[TaskWithTime]:
        """Get task with time tracking data."""
        task = await self.get_task(task_id)
        if not task:
            return None
        
        # Get time entries
        time_data = await self.redis.xrange(RedisKeys.task_time(task_id))
        
        entries = []
        total_time = 0.0
        
        for _, entry_data in time_data:
            entry = TimeEntry(
                task_id=task_id,
                action=entry_data["action"],
                timestamp=datetime.fromisoformat(entry_data["timestamp"]),
                duration=float(entry_data.get("duration", 0))
            )
            entries.append(entry)
            
            if entry.action == "stop" and entry.duration:
                total_time += entry.duration
        
        return TaskWithTime(
            **task.model_dump(),
            time_entries=entries,
            total_time=total_time
        )
