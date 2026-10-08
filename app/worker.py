from datetime import datetime, timezone

from bson import ObjectId
from celery import Celery
from pymongo import MongoClient

from app.config import (
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    CERTIFICATES_URL_PREFIX,
    MONGO_URI,
)
from app.certificate import generate_certificate_pdf

# Celery broker: Redis (Celery needs its host and port, 6379 is the Redis default)
celery_app = Celery(
    "certificate_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Pool of 2 worker processes
    worker_concurrency=2,
    # Pick one task at a time so work is spread evenly across the 2 processes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# The worker is synchronous, so it uses pymongo (not Beanie/Motor).
# The client is created lazily so each forked worker process gets its own.
_client = None


def _db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client.get_default_database()


@celery_app.task(name="generate_certificate_task")
def generate_certificate_task(student_id: str):
    db = _db()
    oid = ObjectId(student_id)

    # Atomic claim: pending -> processing. If the student is missing or already
    # claimed by another task, this returns None and we skip (no duplicate work).
    student = db.students.find_one_and_update(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}},
    )
    if student is None:
        return {"student_id": student_id, "status": "skipped", "detail": "not pending"}

    try:
        generate_certificate_pdf(
            student_name=student["student_name"],
            school_name=student["school_name"],
            output_name=student_id,
        )
        link = f"{CERTIFICATES_URL_PREFIX}/{student_id}.pdf"

        # Store the certificate entry, then mark the student as processed
        db.certificates.update_one(
            {"student_id": oid},
            {"$set": {"certificate_link": link}},
            upsert=True,
        )
        db.students.update_one({"_id": oid}, {"$set": {"status": "processed"}})
        return {"student_id": student_id, "status": "processed", "link": link}

    except Exception as exc:
        # An error on one student never affects the other tasks in the queue
        db.students.update_one({"_id": oid}, {"$set": {"status": "error"}})
        return {"student_id": student_id, "status": "error", "detail": str(exc)}
