"""
Минимальный REST API для веб-интерфейса.
Запуск: uvicorn ui:app --reload
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from database import Database
from solver import ScheduleSolver, SolverConfig
from models import ScheduleValidator

app = FastAPI(title="School Schedule API")
db = Database()


# ===== MODELS =====

class TeacherCreate(BaseModel):
    fio: str
    max_hours_week: int = 36
    warn_hours_week: int = 40
    no_first_lesson: bool = False
    no_windows: bool = False
    subjects: List[dict] = []


class SubjectCreate(BaseModel):
    name: str
    room_types: List[str] = ["universal"]
    is_group_split: bool = False
    is_double_lesson: bool = False
    difficulty: int = 2


class ClassCreate(BaseModel):
    name: str
    op_type: str = "general"
    class_teacher_id: Optional[int] = None
    shift: int = 1
    max_lessons_day: int = 7


class RoomCreate(BaseModel):
    number: str
    room_type: str = "universal"
    capacity: int = 30


class LoadAssign(BaseModel):
    teacher_id: int
    subject_id: int
    class_id: int
    hours_per_week: int


class GenerateRequest(BaseModel):
    max_time_seconds: int = 300


class EventCreate(BaseModel):
    event_type: str
    start_date: str
    end_date: str
    description: str = ""
    affected_teachers: List[int] = []
    affected_classes: List[int] = []
    replacement_teacher_id: Optional[int] = None


# ===== ENDPOINTS =====

@app.get("/")
def root():
    return {"message": "School Schedule API", "status": "running"}


# Teachers
@app.get("/teachers")
def get_teachers():
    return db.get_all_teachers()


@app.post("/teachers")
def create_teacher(t: TeacherCreate):
    tid = db.add_teacher(
        t.fio, t.max_hours_week, t.warn_hours_week,
        t.subjects, t.no_first_lesson, t.no_windows
    )
    return {"id": tid, "fio": t.fio}


@app.get("/teachers/{tid}/load")
def get_teacher_load(tid: int):
    return db.check_teacher_hours(tid)


@app.get("/teachers/{tid}/schedule")
def get_teacher_schedule(tid: int, day: Optional[int] = None):
    return db.get_schedule_for_teacher(tid, day)


# Subjects
@app.get("/subjects")
def get_subjects():
    return db.get_all_subjects()


@app.post("/subjects")
def create_subject(s: SubjectCreate):
    sid = db.add_subject(
        s.name, s.room_types, s.is_group_split,
        s.is_double_lesson, s.difficulty
    )
    return {"id": sid, "name": s.name}


# Classes
@app.get("/classes")
def get_classes():
    return db.get_all_classes()


@app.post("/classes")
def create_class(c: ClassCreate):
    cid = db.add_class(
        c.name, c.op_type, c.class_teacher_id, c.shift
    )
    return {"id": cid, "name": c.name}


@app.get("/classes/{cid}/schedule")
def get_class_schedule(cid: int, day: Optional[int] = None):
    return db.get_schedule_for_class(cid, day)


# Rooms
@app.get("/rooms")
def get_rooms():
    return db.get_all_rooms()


@app.post("/rooms")
def create_room(r: RoomCreate):
    rid = db.add_room(r.number, r.room_type, r.capacity)
    return {"id": rid, "number": r.number}


# Load
@app.post("/load")
def assign_load(l: LoadAssign):
    db.set_teacher_load(
        l.teacher_id, l.subject_id, l.class_id, l.hours_per_week
    )
    return {"status": "ok"}


# Bell schedule
@app.get("/bells/{shift}")
def get_bells(shift: int):
    return db.get_bell_schedule(shift)


# Generate
@app.post("/generate")
def generate_schedule(req: GenerateRequest):
    config = SolverConfig(max_time_seconds=req.max_time_seconds)
    solver = ScheduleSolver(db, config)
    result = solver.solve()

    if result['status'] in ('optimal', 'feasible'):
        db.save_schedule(result['lessons'])

    return result


# Validate
@app.get("/validate")
def validate_schedule():
    validator = ScheduleValidator(db)
    errors = validator.validate_full_schedule()
    return [
        {
            "severity": e.severity,
            "message": e.message,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
        }
        for e in errors
    ]


# Events
@app.post("/events")
def create_event(e: EventCreate):
    eid = db.add_event(
        e.event_type, e.start_date, e.end_date,
        e.description, e.affected_teachers,
        e.affected_classes, e.replacement_teacher_id
    )
    return {"id": eid}


@app.get("/events")
def get_events(on_date: Optional[str] = None):
    return db.get_active_events(on_date)
