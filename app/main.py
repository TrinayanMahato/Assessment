import csv
import io
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import openpyxl
from beanie import init_beanie
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

from app.config import CERTIFICATES_DIR, MONGO_URI, PUBLIC_DIR
from app.models import Certificate, IncompleteStudent, Student, StatusEnum
from app.schemas import StudentUploadRow
from app.worker import generate_certificate_task

os.makedirs(CERTIFICATES_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(MONGO_URI)
    await init_beanie(
        database=client.get_default_database(),
        document_models=[Student, IncompleteStudent, Certificate],
    )
    yield
    client.close()


app = FastAPI(title="Bulk Certificate Generator", lifespan=lifespan)

# Generated certificates are publicly reachable at /public/certificates/<id>.pdf
app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")

REQUIRED_COLUMNS = ["School_name", "student_name", "class"]


def _clean(value: Any) -> Optional[Any]:
    """Blank cells become None so 'missing' is not mistaken for a wrong type."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value.strip() if isinstance(value, str) else value


def _read_rows(filename: str, content: bytes) -> List[Dict[str, Any]]:
    """Returns the file as a list of dicts keyed by the header names."""
    if filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        rows = []
        for raw in reader:
            rows.append({k.strip(): v for k, v in raw.items() if k is not None})
        return rows if headers else []

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    sheet = wb.active
    all_rows = list(sheet.iter_rows(values_only=True))
    if not all_rows:
        return []
    headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
    return [dict(zip(headers, r)) for r in all_rows[1:]]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload-students")
async def upload_students(file: UploadFile = File(...)):
    # Pydantic validates data, not files, so the file type is checked here
    filename = (file.filename or "").lower()
    if not (filename.endswith(".csv") or filename.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are supported")

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit
    
    # Check size from metadata if available (fast path)
    if getattr(file, "size", 0) and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size allowed is 10MB.")

    content = await file.read()
    
    # Check actual content length (fallback)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size allowed is 10MB.")

    try:
        rows = _read_rows(filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing file: {str(e)}")

    if not rows:
        raise HTTPException(status_code=400, detail="No data found in the file")

    complete: List[Student] = []
    incomplete: List[IncompleteStudent] = []
    errors = []

    for index, raw in enumerate(rows, start=1):
        row = {col: _clean(raw.get(col)) for col in REQUIRED_COLUMNS}

        # Fully empty row: skip it
        if all(v is None for v in row.values()):
            continue

        # Pydantic: only a wrong data type raises, missing values are allowed
        try:
            validated = StudentUploadRow(**row)
        except ValidationError as e:
            errors.append({"row": index, "error": e.errors()[0]["msg"]})
            continue

        if None in (validated.School_name, validated.student_name, validated.student_class):
            incomplete.append(
                IncompleteStudent(
                    school_name=validated.School_name,
                    student_name=validated.student_name,
                    **{"class": validated.student_class},
                )
            )
        else:
            complete.append(
                Student(
                    school_name=validated.School_name,
                    student_name=validated.student_name,
                    status=StatusEnum.pending,
                    **{"class": validated.student_class},
                )
            )

    if incomplete:
        await IncompleteStudent.insert_many(incomplete)

    queued_ids = []
    broker_down = False
    if complete:
        result = await Student.insert_many(complete)
        for student_id in result.inserted_ids:
            try:
                generate_certificate_task.delay(str(student_id))
                queued_ids.append(student_id)
            except Exception:
                # Redis unreachable: do not fail the request and do not mark error.
                # The students stay 'pending' with queued=False, and the sweeper
                # process pushes them to Redis once it is reachable again.
                broker_down = True
                break

        if queued_ids:
            await Student.find({"_id": {"$in": queued_ids}}).update(
                {"$set": {"queued": True}}
            )

    queued = len(queued_ids)
    return {
        "message": (
            "File processed. Queue is temporarily unavailable; remaining students "
            "are saved as pending and will be processed automatically."
            if broker_down
            else "File processed"
        ),
        "students_created": len(complete),
        "queued_for_generation": queued,
        "pending_retry": len(complete) - queued,
        "incomplete_students": len(incomplete),
        "errors_count": len(errors),
        "errors": errors[:10],
    }


@app.get("/students/pending")
async def get_pending_students(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return")
):
    """Retrieve students with a 'pending' status, with pagination."""
    total_pending = await Student.find({"status": StatusEnum.pending}).count()
    pending_students = await Student.find({"status": StatusEnum.pending}).skip(skip).limit(limit).to_list()
    
    return {
        "total_count": total_pending,
        "returned_count": len(pending_students),
        "skip": skip,
        "limit": limit,
        "students": pending_students
    }
