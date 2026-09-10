"""Typed task schema. Nodes come from configuration, not a hardcoded roster."""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator

from config import get_config


class TaskAction(str, Enum):
    """The complete allowlist. Nothing outside this enum can ever execute."""

    TELEGRAM_NOTIFY = "telegram_notify"
    FLEET_HEALTH_PING = "fleet_health_ping"
    GPU_BATCH = "gpu_batch"


class TaskPriority(str, Enum):
    CRITICAL = "critical"
    NORMAL = "normal"
    LOW = "low"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class TaskSubmission(BaseModel):
    target: str = Field(..., description="Target node, must exist in FLEET_NODES")
    action: TaskAction = Field(..., description="Allowlisted action")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL)
    params: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    ttl_seconds: int = Field(default=86400, ge=60, le=604800)

    @field_validator("target")
    @classmethod
    def _known_node(cls, value: str) -> str:
        known = get_config().nodes
        if value not in known:
            raise ValueError(f"unknown node {value!r}; configured nodes: {', '.join(known)}")
        return value

    @field_validator("params")
    @classmethod
    def _valid_params(cls, params: Dict[str, Any], info) -> Dict[str, Any]:
        action = info.data.get("action")

        if action == TaskAction.TELEGRAM_NOTIFY:
            message = params.get("message")
            photo = params.get("photo_url")
            if not message and not photo:
                raise ValueError("telegram_notify requires 'message' and/or 'photo_url'")
            if message is not None and not isinstance(message, str):
                raise ValueError("'message' must be a string")
            if isinstance(message, str) and len(message) > 4000:
                raise ValueError("'message' exceeds the 4000 character Telegram limit")
            if photo is not None:
                if not isinstance(photo, str) or not photo.startswith(("http://", "https://")):
                    raise ValueError("'photo_url' must be an http(s) URL")

        return params


class TaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target: str
    action: TaskAction
    priority: TaskPriority
    params: Dict[str, Any]
    idempotency_key: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    lease_ttl: int = 300
    retry_count: int = 0
    max_retries: int = 5
