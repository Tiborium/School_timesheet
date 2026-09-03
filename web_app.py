"""
Веб-приложение для управления школьным расписанием
Запуск: uvicorn web_app:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime
import json

from database import Database
from solver import ScheduleSolver, SolverConfig
from models import ScheduleValidator, DayOfWeek

app = FastAPI(title="School Schedule Manager", version="1.0.0")

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files и templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Инициализация БД
db = Database()

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def get_day_name(day_num: int) -> str:
    """Получить название дня недели."""
    days = {1: "Понедельник", 2: "Вторник", 3: "Среда", 4: "Четверг", 5: "Пятница"}
    return days.get(day_num, "")

# ===== СТРАНИЦЫ =====

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница."""
    teachers = db.get_all_teachers()
    subjects = db.get_all_subjects()
    classes = db.get_all_classes()
    rooms = db.get_all_rooms()
    
    # Статистика
    total_load = sum(len(db.get_full_load(t['id'])) for t in teachers)
    schedule_count = 0
    for c in classes:
        schedule_count += len(db.get_schedule_for_class(c['id']))
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "teachers_count": len(teachers),
        "subjects_count": len(subjects),
        "classes_count": len(classes),
        "rooms_count": len(rooms),
        "total_load": total_load,
        "schedule_count": schedule_count,
    })

# ===== УЧИТЕЛЯ =====

@app.get("/teachers", response_class=HTMLResponse)
async def teachers_page(request: Request):
    """Страница учителей."""
    teachers = db.get_all_teachers()
    teacher_data = []
    
    for t in teachers:
        load = db.get_teacher_load(t['id'])
        full_load = db.get_full_load(t['id'])
        teacher_data.append({
            **t,
            'current_hours': load.get('total_hours', 0),
            'subjects_count': len(full_load),
            'is_overloaded': load.get('total_hours', 0) > t['warn_hours_week'],
        })
    
    return templates.TemplateResponse("teachers.html", {
        "request": request,
        "teachers": teacher_data,
    })

@app.post("/teachers/add")
async def add_teacher(
    fio: str = Form(...),
    max_hours: int = Form(36),
    warn_hours: int = Form(40),
    no_first: bool = Form(False),
    no_windows: bool = Form(False),
):
    """Добавить учителя."""
    db.add_teacher(
        fio=fio,
        max_hours=max_hours,
        warn_hours=warn_hours,
        no_first=no_first,
        no_windows=no_windows,
    )
    return RedirectResponse(url="/teachers", status_code=303)

@app.post("/teachers/{tid}/delete")
async def delete_teacher(tid: int):
    """Удалить учителя."""
    # TODO: Добавить проверку на использование в расписании
    with db.get_conn() as conn:
        conn.execute("UPDATE teachers SET is_active=0 WHERE id=?", (tid,))
    return RedirectResponse(url="/teachers", status_code=303)

# ===== ПРЕДМЕТЫ =====

@app.get("/subjects", response_class=HTMLResponse)
async def subjects_page(request: Request):
    """Страница предметов."""
    subjects = db.get_all_subjects()
    return templates.TemplateResponse("subjects.html", {
        "request": request,
        "subjects": subjects,
    })

@app.post("/subjects/add")
async def add_subject(
    name: str = Form(...),
    room_types: str = Form("universal"),
    is_group: bool = Form(False),
    is_double: bool = Form(False),
    difficulty: int = Form(2),
):
    """Добавить предмет."""
    room_types_list = [rt.strip() for rt in room_types.split(",")]
    db.add_subject(
        name=name,
        room_types=room_types_list,
        is_group=is_group,
        is_double=is_double,
        difficulty=difficulty,
    )
    return RedirectResponse(url="/subjects", status_code=303)

# ===== КЛАССЫ =====

@app.get("/classes", response_class=HTMLResponse)
async def classes_page(request: Request):
    """Страница классов."""
    classes = db.get_all_classes()
    teachers = db.get_all_teachers()
    
    class_data = []
    for c in classes:
        schedule = db.get_schedule_for_class(c['id'])
        class_data.append({
            **c,
            'lessons_count': len(schedule),
            'teacher_name': next(
                (t['fio'] for t in teachers if t['id'] == c['class_teacher_id']),
                "Не назначен"
            )
        })
    
    return templates.TemplateResponse("classes.html", {
        "request": request,
        "classes": class_data,
        "teachers": teachers,
    })

@app.post("/classes/add")
async def add_class(
    name: str = Form(...),
    op_type: str = Form("general"),
    class_teacher_id: Optional[int] = Form(None),
    shift: int = Form(1),
    max_lessons: int = Form(7),
):
    """Добавить класс."""
    db.add_class(
        name=name,
        op_type=op_type,
        class_teacher_id=class_teacher_id,
        shift=shift,
        max_lessons_day=max_lessons,
    )
    return RedirectResponse(url="/classes", status_code=303)

# ===== КАБИНЕТЫ =====

@app.get("/rooms", response_class=HTMLResponse)
async def rooms_page(request: Request):
    """Страница кабинетов."""
    rooms = db.get_all_rooms()
    return templates.TemplateResponse("rooms.html", {
        "request": request,
        "rooms": rooms,
    })

@app.post("/rooms/add")
async def add_room(
    number: str = Form(...),
    room_type: str = Form("universal"),
    capacity: int = Form(30),
):
    """Добавить кабинет."""
    db.add_room(number=number, room_type=room_type, capacity=capacity)
    return RedirectResponse(url="/rooms", status_code=303)

# ===== НАГРУЗКА =====

@app.get("/load", response_class=HTMLResponse)
async def load_page(request: Request):
    """Страница назначения нагрузки."""
    teachers = db.get_all_teachers()
    subjects = db.get_all_subjects()
    classes = db.get_all_classes()
    
    # Текущая нагрузка
    load_data = []
    for t in teachers:
        full_load = db.get_full_load(t['id'])
        for fl in full_load:
            load_data.append(fl)
    
    return templates.TemplateResponse("load.html", {
        "request": request,
        "teachers": teachers,
        "subjects": subjects,
        "classes": classes,
        "load_data": load_data,
    })

@app.post("/load/assign")
async def assign_load(
    teacher_id: int = Form(...),
    subject_id: int = Form(...),
    class_id: int = Form(...),
    hours: int = Form(...),
):
    """Назначить нагрузку."""
    db.set_teacher_load(teacher_id, subject_id, class_id, hours)
    return RedirectResponse(url="/load", status_code=303)

@app.post("/load/remove/{lid}")
async def remove_load(lid: int):
    """Удалить нагрузку."""
    with db.get_conn() as conn:
        conn.execute("DELETE FROM teacher_load WHERE id=?", (lid,))
    return RedirectResponse(url="/load", status_code=303)

# ===== РАСПИСАНИЕ =====

@app.get("/schedule", response_class=HTMLResponse)
async def schedule_page(request: Request):
    """Страница просмотра расписания."""
    classes = db.get_all_classes()
    teachers = db.get_all_teachers()
    rooms = db.get_all_rooms()
    
    # Получить расписание для всех классов
    all_schedules = {}
    for c in classes:
        schedule = db.get_schedule_for_class(c['id'])
        # Группировка по дням и урокам
        by_day_lesson = {}
        for s in schedule:
            day = s['day_of_week']
            lesson = s['lesson_number']
            if day not in by_day_lesson:
                by_day_lesson[day] = {}
            by_day_lesson[day][lesson] = s
        all_schedules[c['id']] = {
            'class': c,
            'schedule': by_day_lesson,
        }
    
    bells = db.get_bell_schedule(shift=1)
    
    return templates.TemplateResponse("schedule.html", {
        "request": request,
        "classes": classes,
        "all_schedules": all_schedules,
        "bells": bells,
        "days": [1, 2, 3, 4, 5],
        "day_names": {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт"},
    })

@app.get("/schedule/teacher/{tid}", response_class=HTMLResponse)
async def teacher_schedule(request: Request, tid: int):
    """Расписание конкретного учителя."""
    teacher = None
    for t in db.get_all_teachers():
        if t['id'] == tid:
            teacher = t
            break
    
    if not teacher:
        raise HTTPException(status_code=404, detail="Учитель не найден")
    
    schedule = db.get_schedule_for_teacher(tid)
    
    # Группировка
    by_day_lesson = {}
    for s in schedule:
        day = s['day_of_week']
        lesson = s['lesson_number']
        if day not in by_day_lesson:
            by_day_lesson[day] = {}
        by_day_lesson[day][lesson] = s
    
    bells = db.get_bell_schedule(shift=1)
    
    return templates.TemplateResponse("teacher_schedule.html", {
        "request": request,
        "teacher": teacher,
        "schedule": by_day_lesson,
        "bells": bells,
        "days": [1, 2, 3, 4, 5],
        "day_names": {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт"},
    })

@app.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request):
    """Страница генерации расписания."""
    return templates.TemplateResponse("generate.html", {"request": request})

@app.post("/generate/run")
async def generate_schedule(
    max_time: int = Form(300),
    request: Request = None,
):
    """Запустить генерацию расписания."""
    config = SolverConfig(max_time_seconds=max_time)
    solver = ScheduleSolver(db, config)
    
    result = solver.solve()
    
    if result['status'] in ('optimal', 'feasible'):
        db.save_schedule(result['lessons'])
        
        return templates.TemplateResponse("generate_result.html", {
            "request": request,
            "success": True,
            "status": result['status'],
            "stats": result['stats'],
            "lessons_count": len(result['lessons']),
        })
    else:
        return templates.TemplateResponse("generate_result.html", {
            "request": request,
            "success": False,
            "message": result.get('message', 'Не удалось сгенерировать расписание'),
        })

@app.get("/validate", response_class=HTMLResponse)
async def validate_page(request: Request):
    """Проверка расписания."""
    validator = ScheduleValidator(db)
    errors = validator.validate_full_schedule()
    
    return templates.TemplateResponse("validate.html", {
        "request": request,
        "errors": errors,
    })

# ===== ЗАМЕНЫ И СОБЫТИЯ =====

@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    """Страница событий (замены, болезни)."""
    events = db.get_active_events()
    teachers = db.get_all_teachers()
    classes = db.get_all_classes()
    
    return templates.TemplateResponse("events.html", {
        "request": request,
        "events": events,
        "teachers": teachers,
        "classes": classes,
    })

@app.post("/events/add")
async def add_event(
    event_type: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    description: str = Form(""),
    affected_teachers: str = Form(""),
    affected_classes: str = Form(""),
    replacement_teacher_id: Optional[int] = Form(None),
):
    """Добавить событие."""
    teachers_list = [int(x) for x in affected_teachers.split(",") if x.strip()]
    classes_list = [int(x) for x in affected_classes.split(",") if x.strip()]
    
    db.add_event(
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        description=description,
        affected_teachers=teachers_list,
        affected_classes=classes_list,
        replacement_teacher_id=replacement_teacher_id,
    )
    
    return RedirectResponse(url="/events", status_code=303)

# ===== API ЭНДПОИНТЫ (для AJAX) =====

@app.get("/api/teachers/{tid}/load")
async def api_teacher_load(tid: int):
    """API: Нагрузка учителя."""
    return db.check_teacher_hours(tid)

@app.get("/api/schedule/class/{cid}")
async def api_class_schedule(cid: int, day: Optional[int] = None):
    """API: Расписание класса."""
    return db.get_schedule_for_class(cid, day)

@app.get("/api/schedule/teacher/{tid}")
async def api_teacher_schedule(tid: int, day: Optional[int] = None):
    """API: Расписание учителя."""
    return db.get_schedule_for_teacher(tid, day)

# ===== ИНИЦИАЛИЗАЦИЯ =====

@app.post("/init/demo")
async def init_demo(request: Request):
    """Инициализировать демо-данные."""
    from scheduler_app import SchoolSchedulerApp
    app_instance = SchoolSchedulerApp()
    app_instance.init_demo_data()
    
    return JSONResponse({
        "status": "ok",
        "message": "Демо-данные инициализированы"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
