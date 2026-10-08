"""
Standalone sweeper process (run separately from the API and the Celery worker):

    python -m app.sweeper

Every SWEEPER_INTERVAL_SECONDS it:
  1. pings Redis;
  2. if Redis is unreachable, emails an alert (rate limited) and tries again later;
  3. if reachable, pushes 'pending' students that never reached the queue.

It is deliberately NOT a Celery Beat task: Beat publishes through Redis, so it
would be down exactly when it is needed.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import redis
import resend
from pymongo import MongoClient

from app.config import (
    ALERT_COOLDOWN_SECONDS,
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_TO,
    CELERY_BROKER_URL,
    MONGO_URI,
    RESEND_API_KEY,
    SWEEPER_BATCH_SIZE,
    SWEEPER_INTERVAL_SECONDS,
    SWEEPER_MIN_AGE_SECONDS,
    STALE_PROCESSING_SECONDS,
)
from app.worker import generate_certificate_task

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sweeper")


def send_alert(subject: str, body: str) -> None:
    """Sends an email alert using Resend. Never raises: alerting must not kill the sweeper."""
    if not (RESEND_API_KEY and ALERT_EMAIL_TO):
        log.warning("Resend API key not configured, alert not emailed: %s", subject)
        return
    try:
        resend.api_key = RESEND_API_KEY
        params: resend.Emails.SendParams = {
            "from": ALERT_EMAIL_FROM,
            "to": [ALERT_EMAIL_TO],
            "subject": subject,
            "html": f"<p>{body}</p>",
        }
        resend.Emails.send(params)
        log.info("Alert emailed to %s: %s", ALERT_EMAIL_TO, subject)
    except Exception:
        log.exception("Failed to send alert email")


def redis_reachable() -> bool:
    try:
        client = redis.Redis.from_url(
            CELERY_BROKER_URL, socket_connect_timeout=3, socket_timeout=3
        )
        return bool(client.ping())
    except Exception:
        return False


def requeue_pending(db) -> int:
    """Pushes pending, never-queued students to Redis. Returns how many were queued."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SWEEPER_MIN_AGE_SECONDS)
    query = {
        "status": "pending",
        "queued": {"$ne": True},
        "$or": [{"created_at": {"$lte": cutoff}}, {"created_at": {"$exists": False}}],
    }
    queued = 0
    for student in db.students.find(query, {"_id": 1}).limit(SWEEPER_BATCH_SIZE):
        try:
            generate_certificate_task.delay(str(student["_id"]))
        except Exception:
            log.warning("Redis went away mid-sweep, will retry next cycle")
            break
        db.students.update_one({"_id": student["_id"]}, {"$set": {"queued": True}})
        queued += 1
    return queued


def reset_stale_processing(db) -> int:
    """Finds students stuck in 'processing' for > STALE_PROCESSING_SECONDS and reverts them to 'pending'."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_PROCESSING_SECONDS)
    query = {
        "status": "processing",
        "$or": [{"updated_at": {"$lte": cutoff}}, {"updated_at": {"$exists": False}}],
    }
    result = db.students.update_many(
        query, 
        {"$set": {"status": "pending", "queued": False, "updated_at": datetime.now(timezone.utc)}}
    )
    return result.modified_count


def main() -> None:
    db = MongoClient(MONGO_URI).get_default_database()
    redis_down = False
    last_alert = 0.0
    log.info("Sweeper started (interval=%ss)", SWEEPER_INTERVAL_SECONDS)

    while True:
        try:
            if not redis_reachable():
                log.error("Redis is NOT reachable")
                redis_down = True
                if time.time() - last_alert >= ALERT_COOLDOWN_SECONDS:
                    send_alert(
                        "[ALERT] Redis is not reachable",
                        "The certificate service cannot reach Redis. Pending students "
                        "are saved in MongoDB and will be queued automatically once "
                        "Redis is back.",
                    )
                    last_alert = time.time()
            else:
                if redis_down:
                    log.info("Redis is reachable again")
                    send_alert(
                        "[RECOVERED] Redis is reachable again",
                        "Redis is back. The sweeper is re-queuing pending students.",
                    )
                    redis_down = False
                    last_alert = 0.0
                
                # 1. Reset ghost tasks
                stale_count = reset_stale_processing(db)
                if stale_count:
                    log.warning("Reset %d stale processing student(s) to pending", stale_count)

                # 2. Re-queue pending tasks
                count = requeue_pending(db)
                if count:
                    log.info("Re-queued %d pending student(s)", count)
        except Exception:
            log.exception("Sweeper cycle failed")
        time.sleep(SWEEPER_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
