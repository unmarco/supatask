"""Logs router for retrieving activity and system logs."""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
import redis.asyncio as redis

from models import LogEntry, LogFilter
from database import get_redis
from services.log_service import LogService

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=List[LogEntry])
async def get_logs(
    log_type: str = Query("activity", pattern="^(activity|system)$"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(100, le=1000),
    redis_client: redis.Redis = Depends(get_redis)
):
    """Get logs with filtering."""
    log_service = LogService(redis_client)
    
    filters = LogFilter(
        log_type=log_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    logs = await log_service.get_logs(filters)
    return logs
