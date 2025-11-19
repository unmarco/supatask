"""Service layer for logging operations."""
import json
from datetime import datetime
from typing import List, Optional
import redis.asyncio as redis
from models import LogEntry, LogFilter
from database import RedisKeys


class LogService:
    """Service for logging operations."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def log_activity(
        self,
        message: str,
        task_id: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> LogEntry:
        """Log an activity event."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            message=message,
            task_id=task_id,
            metadata=metadata
        )
        
        # Store in Redis stream
        stream_data = {
            "timestamp": entry.timestamp.isoformat(),
            "level": entry.level,
            "message": entry.message,
        }
        
        if task_id is not None:
            stream_data["task_id"] = str(task_id)
        
        if metadata:
            stream_data["metadata"] = json.dumps(metadata)
        
        await self.redis.xadd(RedisKeys.logs_activity(), stream_data)
        
        return entry
    
    async def log_system(
        self,
        message: str,
        level: str = "INFO",
        metadata: Optional[dict] = None
    ) -> LogEntry:
        """Log a system/debug event."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            metadata=metadata
        )
        
        # Store in Redis stream
        stream_data = {
            "timestamp": entry.timestamp.isoformat(),
            "level": entry.level,
            "message": entry.message,
        }
        
        if metadata:
            stream_data["metadata"] = json.dumps(metadata)
        
        await self.redis.xadd(RedisKeys.logs_system(), stream_data)
        
        return entry
    
    async def get_logs(self, filters: LogFilter) -> List[LogEntry]:
        """Get logs with filtering."""
        # Determine which stream to read from
        stream_key = (
            RedisKeys.logs_activity()
            if filters.log_type == "activity"
            else RedisKeys.logs_system()
        )
        
        # Read from stream
        # Use xrevrange for reverse chronological order
        logs_data = await self.redis.xrevrange(
            stream_key,
            count=filters.limit
        )
        
        logs = []
        for _, log_data in logs_data:
            timestamp = datetime.fromisoformat(log_data["timestamp"])
            
            # Apply time filters
            if filters.start_time and timestamp < filters.start_time:
                continue
            if filters.end_time and timestamp > filters.end_time:
                continue
            
            entry = LogEntry(
                timestamp=timestamp,
                level=log_data["level"],
                message=log_data["message"],
                task_id=int(log_data["task_id"]) if "task_id" in log_data else None,
                metadata=json.loads(log_data["metadata"]) if "metadata" in log_data else None
            )
            logs.append(entry)
        
        return logs
