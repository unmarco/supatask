"""Redis database connection and helper functions."""
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
import redis.asyncio as redis
from config import settings


class RedisDB:
    """Redis database wrapper."""
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Connect to Redis."""
        self.client = await redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
    
    async def ping(self) -> bool:
        """Check Redis connection."""
        try:
            return await self.client.ping()
        except Exception:
            return False


# Global database instance
db = RedisDB()


async def get_redis() -> redis.Redis:
    """Dependency to get Redis client."""
    return db.client


# Key patterns for Redis
class RedisKeys:
    """Redis key patterns."""
    
    TASK_NEXT_ID = "task:next_id"
    
    @staticmethod
    def task(task_id: int) -> str:
        return f"task:{task_id}"
    
    @staticmethod
    def task_tags(task_id: int) -> str:
        return f"task:{task_id}:tags"
    
    @staticmethod
    def task_time(task_id: int) -> str:
        return f"task:{task_id}:time"
    
    @staticmethod
    def tasks_set() -> str:
        return "tasks"
    
    @staticmethod
    def tasks_by_status(status: str) -> str:
        return f"tasks:by_status:{status}"
    
    @staticmethod
    def logs_activity() -> str:
        return "logs:activity"
    
    @staticmethod
    def logs_system() -> str:
        return "logs:system"
