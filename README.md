# FastAPI Attendance Service

An employee attendance and analytics API built with Python, FastAPI and MongoDB.
All code is in `app/main.py`.

## Features
- Employee create and list, with validation and pagination
- Punch-in and punch-out with IST attendance dates, overnight shifts, and late / overtime / work-hours / half-day calculation
- Manual corrections (PATCH) with an append-only audit trail in `history`
- Analytics built on MongoDB aggregation pipelines: employee monthly summary, department summary, late leaderboard, department daily trend
- `/admin/explain/{endpoint}` returns MongoDB `explain` output for each endpoint's main query

## Setup
Requires Python 3.11+ and MongoDB 6.0 or newer running locally.

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

Create a `.env` file (it is not committed):

    MONGO_URI=mongodb://localhost:27017
    MONGO_DB=attendance_db

## Run
    uvicorn app.main:app --port 8000

API docs: http://localhost:8000/docs

Indexes are created automatically at startup.

## Status
- Implemented: all endpoints listed above.
- Tested: (write what you actually tested)
- Not tested / known gaps: (write honestly, for example no automated tests)