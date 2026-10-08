import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/Assignment")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "template.jpg")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
CERTIFICATES_DIR = os.path.join(PUBLIC_DIR, "certificates")
CERTIFICATES_URL_PREFIX = "/public/certificates"

# Sweeper: re-queues pending students and watches Redis health
SWEEPER_INTERVAL_SECONDS = int(os.getenv("SWEEPER_INTERVAL_SECONDS", "10"))
# Only students older than this are picked up, so a fresh upload is not double-queued
SWEEPER_MIN_AGE_SECONDS = int(os.getenv("SWEEPER_MIN_AGE_SECONDS", "30"))
SWEEPER_BATCH_SIZE = int(os.getenv("SWEEPER_BATCH_SIZE", "500"))
STALE_PROCESSING_SECONDS = int(os.getenv("STALE_PROCESSING_SECONDS", "600"))
# Minimum gap between repeated "Redis is down" emails
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "900"))

# Email alerts (optional)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "onboarding@resend.dev")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

