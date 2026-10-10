"""
Employee Attendance & Analytics API
Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)
"""
import os
from contextlib import asynccontextmanager
from datetime import date as Date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional
 
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
 
load_dotenv()
 
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), tz_aware=True)
db = client[os.getenv("MONGO_DB", "attendance_db")]
 
IST = timezone(timedelta(hours=5, minutes=30))
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
 
 
@asynccontextmanager
async def lifespan(app):
    # Created at startup; create_index is idempotent.
    db.employees.create_index("emp_code", unique=True)
    db.attendance_logs.create_index([("emp_code", 1), ("date", 1)], unique=True)
    db.attendance_logs.create_index([("date", -1), ("emp_code", 1)])
    yield
 
 
app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0", lifespan=lifespan)
 
 
# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _aware(dt: datetime) -> datetime:
    # PyMongo can give naive datetimes (they are UTC). Make them timezone-aware.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
 
 
def compute_late_minutes(punch_in: datetime, shift_start: str, shift_end: str) -> int:
    local = _aware(punch_in).astimezone(IST).replace(microsecond=0)
    h, m = map(int, shift_start.split(":"))
    start = local.replace(hour=h, minute=m, second=0)
    if shift_end <= shift_start and local.strftime("%H:%M") < shift_end:
        start -= timedelta(days=1)  # overnight shift that started yesterday
    seconds = (local - start).total_seconds()
    return int(seconds // 60) if seconds > 600 else 0
 
 
def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    punch_in = _aware(punch_in).replace(microsecond=0)
    punch_out = _aware(punch_out).replace(microsecond=0)
    seconds = int((punch_out - punch_in).total_seconds())
    hours = (Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(hours)
 
 
def compute_overtime(punch_out: datetime, shift_start: str, shift_end: str, date_str: str) -> int:
    punch_out = _aware(punch_out).replace(microsecond=0)
    h, m = map(int, shift_end.split(":"))
    end = datetime.fromisoformat(date_str).replace(hour=h, minute=m, tzinfo=IST)
    if shift_end <= shift_start:  # overnight shift ends the next day
        end += timedelta(days=1)
    minutes = int((punch_out - end).total_seconds() // 60)
    return minutes if minutes >= 30 else 0
 
 
def to_ms(dt: datetime) -> int:
    return (_aware(dt) - EPOCH) // timedelta(milliseconds=1)
 
 
def _conv(v):
    return to_ms(v) if isinstance(v, datetime) else v
 
 
def employee_out(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    out["created_at"] = to_ms(out["created_at"])
    return out
 
 
def attendance_out(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("punch_in", "punch_out"):
        out[k] = to_ms(out[k]) if out.get(k) is not None else None
    out.setdefault("work_hours", None)
    out.setdefault("late_minutes", 0)
    out.setdefault("overtime_minutes", 0)
    out.setdefault("half_day", False)
    out["history"] = [
        {
            "at": to_ms(h["at"]),
            "by": h["by"],
            "reason": h["reason"],
            "changes": {f: {"from": _conv(c["from"]), "to": _conv(c["to"])} for f, c in h["changes"].items()},
        }
        for h in out.get("history") or []
    ]
    return out
 
 
def attendance_date(ts: datetime, shift_start: str, shift_end: str) -> str:
    local = _aware(ts).astimezone(IST)
    d = local.date()
    if shift_end <= shift_start and local.strftime("%H:%M") < shift_end:
        d -= timedelta(days=1)  # overnight shift that started yesterday (R1)
    return d.isoformat()
 
 
def parse_date_or_422(value: str, name: str) -> str:
    try:
        Date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, f"{name} must be a valid YYYY-MM-DD date")
    return value
 
 
# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
 
 
class EmployeeIn(BaseModel):
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field(default="09:30", pattern=HHMM)
    shift_end: str = Field(default="18:30", pattern=HHMM)
    joined_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
 
    @field_validator("joined_on")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        Date.fromisoformat(v)  # ValueError becomes a 422
        return v
 
    @model_validator(mode="after")
    def _shift_differs(self):
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start must differ from shift_end")
        return self
 
 
class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[StrictInt] = Field(default=None, ge=100_000_000_000, le=4_102_444_800_000)
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"
 
 
# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    try:
        client.admin.command("ping")
    except Exception:
        raise HTTPException(503, "database unavailable")
    return {"status": "ok"}
 
 
@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")
    return employee_out(doc)
 
 
@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = {}
    if department:
        q["department"] = department
    total = db.employees.count_documents(q)
    cursor = db.employees.find(q).sort("emp_code", 1).skip((page - 1) * page_size).limit(page_size)
    return {"items": [employee_out(d) for d in cursor], "total": total, "page": page, "page_size": page_size}
 
 
@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if emp is None:
        raise HTTPException(404, "employee not found")
    if body.punched_at is not None:
        ts = datetime.fromtimestamp(body.punched_at // 1000, tz=timezone.utc)  # whole seconds (R1)
    else:
        ts = datetime.now(timezone.utc).replace(microsecond=0)
    doc = {
        "emp_code": body.emp_code,
        "date": attendance_date(ts, emp["shift_start"], emp["shift_end"]),
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, emp["shift_start"], emp["shift_end"]),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        db.attendance_logs.insert_one(doc)  # unique index decides the race
    except DuplicateKeyError:
        raise HTTPException(409, "already punched in for this date")
    return attendance_out(doc)
 
 
@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if date_from:
        parse_date_or_422(date_from, "date_from")
    if date_to:
        parse_date_or_422(date_to, "date_to")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must not be after date_to")
    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status
    total = db.attendance_logs.count_documents(q)
    cursor = (
        db.attendance_logs.find(q)
        .sort([("date", -1), ("emp_code", 1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    return {"items": [attendance_out(d) for d in cursor], "total": total, "page": page, "page_size": page_size}
 
 
# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #