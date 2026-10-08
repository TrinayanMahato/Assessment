from pydantic import BaseModel, Field
from typing import Optional

class StudentUploadRow(BaseModel):
    School_name: Optional[str] = None
    student_name: Optional[str] = None
    student_class: Optional[int] = Field(default=None, alias="class")
