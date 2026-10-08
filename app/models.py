from datetime import datetime, timezone
from enum import Enum
from pydantic import Field
from typing import Optional
from beanie import Document, PydanticObjectId

class StatusEnum(str, Enum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    error = "error"

class Student(Document):
    school_name: str
    student_name: str
    student_class: int = Field(alias="class")
    status: StatusEnum
    # True once the task has been pushed to Redis; the sweeper re-queues the rest
    queued: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "students"
        indexes = [
            "status",
        ]

class IncompleteStudent(Document):
    school_name: Optional[str] = None
    student_name: Optional[str] = None
    student_class: Optional[int] = Field(default=None, alias="class")
    

    class Settings:
        name = "incomplete_students"

class Certificate(Document):
    student_id: PydanticObjectId
    certificate_link: str

    class Settings:
        name = "certificates"
