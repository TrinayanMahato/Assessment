# Bulk Certificate Generator API

This is a FastAPI-based service that accepts bulk student data via `.csv` or `.xlsx` files, queues the data using Celery and Redis, and asynchronously generates PDF certificates.

## Features
- **FastAPI** for robust and fast endpoints.
- **File Upload** support for CSV and XLSX files.
- **Data Validation** using Pydantic.
- **Asynchronous Processing** with Celery and Redis to handle bulk generation without blocking the API.
- **MongoDB** integration (using Motor/Beanie) for tracking student status and storing certificate links.
- **Auto-Recovery Sweeper**: A background process that safely recovers and requeues tasks if a worker crashes or Redis goes down.

## Setup Instructions

### Prerequisites
1. **Python 3.10+**
2. **MongoDB** (running locally on port 27017 or via remote URI)
3. **Redis** (running locally on port 6379)

### 1. Install Dependencies

Create a virtual environment and install the required packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the root directory and add the following configuration:

```env
MONGO_URI=mongodb://localhost:27017/certificates_db
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Optional: For sweeper email alerts
RESEND_API_KEY=your_resend_key
ALERT_EMAIL_TO=your_email@example.com
ALERT_EMAIL_FROM=alerts@yourdomain.com
```

### 3. Run the Services

You will need to open **three separate terminal windows** to run all components of the system. Make sure you activate your virtual environment (`source .venv/bin/activate`) in each one.

**Terminal 1: Start the FastAPI Server**
```bash
uvicorn app.main:app --reload
```

**Terminal 2: Start the Celery Worker**
```bash
celery -A app.worker.celery_app worker --loglevel=info
```

**Terminal 3: Start the Sweeper Process**
*(This handles stuck tasks and queue recovery if Redis goes down)*
```bash
python -m app.sweeper
```

## API Endpoints

### 1. Upload Students (`POST /upload-students`)
Uploads a CSV or Excel file to process bulk certificates.

```bash
curl -X POST -F "file=@test_students.csv" http://localhost:8000/upload-students
```

### 2. Get Pending Students (`GET /students/pending`)
Retrieves a paginated list of students whose certificates are still pending generation.

```bash
curl "http://localhost:8000/students/pending?skip=0&limit=100"
```

## Database Schema
The project uses `Beanie` ODM for MongoDB. The database stores:
- `students`: Tracks `pending`, `processing`, `processed`, and `error` status.
- `incomplete_students`: Tracks rows that were missing required data.
- `certificates`: Stores the final URLs of the generated PDFs.

Generated PDFs are currently saved in `public/certificates/` and served statically via FastAPI for local development and testing. 

> **Note on Production Storage:** In a true production environment, the generated PDFs will be uploaded directly to **AWS S3** (or a similar cloud storage provider), and the `certificate_link` stored in the database will be the public S3 URL. This ensures scalability, durability, and allows the frontend to seamlessly access the certificates regardless of where the backend containers are hosted.
