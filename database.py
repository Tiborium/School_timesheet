"""Схема базы данных и операции CRUD."""

import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
from datetime import time, date


DB_PATH = Path(__file__).parent / "data" / "school.db"

SCHEMA = """
-- ===== ПРЕПОДАВАТЕЛИ =====
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fio TEXT NOT NULL UNIQUE,
    max_hours_week INTEGER DEFAULT 36,
    warn_hours_week INTEGER DEFAULT 40,
    no_first_lesson INTEGER DEFAULT 0,   -- 1 = не ставить 1-й урок
    no_windows INTEGER DEFAULT 0,         -- 1 = без окон
    fixed_days TEXT DEFAULT '',           -- JSON: ["пн","ср","пт"]
    subjects TEXT DEFAULT '',             -- JSON: [{"subject":"Математика","hours":18}, ...]
    is_active INTEGER DEFAULT 1,
    notes TEXT DEFAULT ''
);

-- ===== ПРЕДМЕТЫ =====
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    room_types TEXT DEFAULT '["universal"]',  -- JSON список допустимых типов
    is_group_split INTEGER DEFAULT 0,         -- Делится на группы (ин.яз, труд)
    group_size INTEGER DEFAULT 0,             -- Размер группы (0 = весь класс)
    is_double_lesson INTEGER DEFAULT 0,       -- Сдвоенный урок
    difficulty INTEGER DEFAULT 2,             -- 1-3 сложность
    notes TEXT DEFAULT ''
);

-- ===== КЛАССЫ =====
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- "5А", "10Б"
    op_type TEXT DEFAULT 'general',     -- general, adapted, inclusive
    class_teacher_id INTEGER REFERENCES teachers(id),
    shift INTEGER DEFAULT 1,            -- 1 или 2 смена
    max_lessons_day INTEGER DEFAULT 7,
    features TEXT DEFAULT '',           -- JSON: особенности
    is_active INTEGER DEFAULT 1
);

-- ===== КАБИНЕТЫ =====
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,        -- "3.5", "сп.зал"
    room_type TEXT DEFAULT 'universal',
    capacity INTEGER DEFAULT 30,
    equipment TEXT DEFAULT '',          -- JSON: оборудование
    is_active INTEGER DEFAULT 1,
    notes TEXT DEFAULT ''
);

-- ===== РАСПИСАНИЕ ЗВОНКОВ =====
CREATE TABLE IF NOT EXISTS bell_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift INTEGER NOT NULL,             -- 1 или 2 смена
    lesson_number INTEGER NOT NULL,     -- Номер урока
    start_time TEXT NOT NULL,           -- "08:00"
    end_time TEXT NOT NULL,             -- "08:45"
    break_minutes INTEGER DEFAULT 10,
    is_lunch INTEGER DEFAULT 0,         -- Обеденная перемена
    is_short INTEGER DEFAULT 0,         -- Сокращённый урок
    UNIQUE(shift, lesson_number)
);

-- ===== РАСПИСАНИЕ УРОКОВ (результат генерации) =====
CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    day_of_week INTEGER NOT NULL,       -- 1=Пн, 2=Вт, ..., 5=Пт
    lesson_number INTEGER NOT NULL,     -- Номер урока
    is_group INTEGER DEFAULT 0,         -- Группа (для делённых классов)
    group_label TEXT DEFAULT '',        -- "1/2", "дев", "мальч"
    week_type INTEGER DEFAULT 0,        -- 0=все недели, 1=числитель, 2=знаменатель
    is_temporary INTEGER DEFAULT 0,     -- Временная замена
    original_teacher_id INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    UNIQUE(class_id, day_of_week, lesson_number, week_type, group_label)
);

-- ===== ОГРАНИЧЕНИЯ (гибкие) =====
CREATE TABLE IF NOT EXISTS constraints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    constraint_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,          -- teacher, class, subject, room
    entity_id INTEGER NOT NULL,
    value TEXT DEFAULT '',
    priority INTEGER DEFAULT 1,         -- 1=жёсткое, 2=мягкое
    is_active INTEGER DEFAULT 1
);

-- ===== ВНЕШТАТНЫЕ СОБЫТИЯ =====
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,           -- illness, holiday, quarantine, event
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    description TEXT DEFAULT '',
    affected_teachers TEXT DEFAULT '',  -- JSON [id, ...]
    affected_classes TEXT DEFAULT '',   -- JSON [id, ...]
    affected_rooms TEXT DEFAULT '',     -- JSON [id, ...]
    replacement_teacher_id INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);

-- ===== НАГРУЗКА ПРЕПОДАВАТЕЛЕЙ (агрегированная) =====
CREATE TABLE IF NOT EXISTS teacher_load (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    class_id INTEGER NOT NULL REFERENCES classes(id),
    hours_per_week INTEGER NOT NULL,
    UNIQUE(teacher_id, subject_id, class_id)
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_schedule_class_day ON schedule(class_id, day_of_week);
CREATE INDEX IF NOT EXISTS idx_schedule_teacher_day ON schedule(teacher_id, day_of_week);
CREATE INDEX IF NOT EXISTS idx_schedule_room_day ON schedule(room_id, day_of_week);
CREATE INDEX IF NOT EXISTS idx_events_dates ON events(start_date, end_date);
"""


class Database:
    """Управление базой данных школы."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self.get_conn() as conn:
            conn.executescript(SCHEMA)

    # ===== TEACHERS =====
    def add_teacher(self, fio: str, max_hours: int = 36,
                    warn_hours: int = 40, subjects: List[Dict] = None,
                    no_first: bool = False, no_windows: bool = False) -> int:
        import json
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO teachers (fio, max_hours_week, warn_hours_week,
                   no_first_lesson, no_windows, subjects)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fio, max_hours, warn_hours, int(no_first), int(no_windows),
                 json.dumps(subjects or []))
            )
            return cur.lastrowid

    def get_all_teachers(self) -> List[Dict]:
        import json
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM teachers WHERE is_active=1").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d['subjects'] = json.loads(d['subjects']) if d['subjects'] else []
                d['fixed_days'] = json.loads(d['fixed_days']) if d['fixed_days'] else []
                result.append(d)
            return result

    def get_teacher_load(self, teacher_id: int) -> Dict[str, Any]:
        """Подсчёт текущей нагрузки учителя."""
        with self.get_conn() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(s.hours_per_week), 0) as total_hours
                   FROM teacher_load s WHERE s.teacher_id = ?""",
                (teacher_id,)
            ).fetchone()
            return dict(row) if row else {"total_hours": 0}

    # ===== SUBJECTS =====
    def add_subject(self, name: str, room_types: List[str] = None,
                    is_group: bool = False, is_double: bool = False,
                    difficulty: int = 2) -> int:
        import json
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO subjects (name, room_types, is_group_split,
                   is_double_lesson, difficulty)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, json.dumps(room_types or ["universal"]),
                 int(is_group), int(is_double), difficulty)
            )
            return cur.lastrowid

    def get_all_subjects(self) -> List[Dict]:
        import json
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM subjects").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d['room_types'] = json.loads(d['room_types'])
                result.append(d)
            return result

    # ===== CLASSES =====
    def add_class(self, name: str, op_type: str = "general",
                  class_teacher_id: int = None, shift: int = 1) -> int:
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO classes (name, op_type, class_teacher_id, shift)
                   VALUES (?, ?, ?, ?)""",
                (name, op_type, class_teacher_id, shift)
            )
            return cur.lastrowid

    def get_all_classes(self) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM classes WHERE is_active=1").fetchall()
            return [dict(r) for r in rows]

    # ===== ROOMS =====
    def add_room(self, number: str, room_type: str = "universal",
                 capacity: int = 30) -> int:
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO rooms (number, room_type, capacity)
                   VALUES (?, ?, ?)""",
                (number, room_type, capacity)
            )
            return cur.lastrowid

    def get_all_rooms(self) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM rooms WHERE is_active=1").fetchall()
            return [dict(r) for r in rows]

    def get_rooms_by_type(self, room_type: str) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM rooms WHERE room_type = ? AND is_active=1",
                (room_type,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ===== BELL SCHEDULE =====
    def add_bell(self, shift: int, lesson_num: int,
                 start: str, end: str, break_min: int = 10) -> int:
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO bell_schedule
                   (shift, lesson_number, start_time, end_time, break_minutes)
                   VALUES (?, ?, ?, ?, ?)""",
                (shift, lesson_num, start, end, break_min)
            )
            return cur.lastrowid

    def get_bell_schedule(self, shift: int = 1) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM bell_schedule WHERE shift=? ORDER BY lesson_number",
                (shift,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ===== TEACHER LOAD =====
    def set_teacher_load(self, teacher_id: int, subject_id: int,
                         class_id: int, hours: int):
        with self.get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO teacher_load
                   (teacher_id, subject_id, class_id, hours_per_week)
                   VALUES (?, ?, ?, ?)""",
                (teacher_id, subject_id, class_id, hours)
            )

    def get_full_load(self, teacher_id: int) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT tl.*, s.name as subject_name, c.name as class_name
                   FROM teacher_load tl
                   JOIN subjects s ON tl.subject_id = s.id
                   JOIN classes c ON tl.class_id = c.id
                   WHERE tl.teacher_id = ?""",
                (teacher_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ===== SCHEDULE =====
    def save_schedule(self, lessons: List[Dict]):
        """Сохранить сгенерированное расписание."""
        with self.get_conn() as conn:
            # Очистить текущее расписание
            conn.execute("DELETE FROM schedule")
            for l in lessons:
                conn.execute(
                    """INSERT INTO schedule
                       (class_id, subject_id, teacher_id, room_id,
                        day_of_week, lesson_number, is_group, group_label,
                        week_type, is_temporary, original_teacher_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (l['class_id'], l['subject_id'], l['teacher_id'],
                     l['room_id'], l['day'], l['lesson'],
                     l.get('is_group', 0), l.get('group_label', ''),
                     l.get('week_type', 0), l.get('is_temporary', 0),
                     l.get('original_teacher_id', 0))
                )

    def get_schedule_for_class(self, class_id: int,
                                day: int = None) -> List[Dict]:
        with self.get_conn() as conn:
            query = """
                SELECT s.*, sub.name as subject_name, t.fio as teacher_name,
                       r.number as room_number
                FROM schedule s
                JOIN subjects sub ON s.subject_id = sub.id
                JOIN teachers t ON s.teacher_id = t.id
                JOIN rooms r ON s.room_id = r.id
                WHERE s.class_id = ? AND s.is_temporary = 0
            """
            params = [class_id]
            if day:
                query += " AND s.day_of_week = ?"
                params.append(day)
            query += " ORDER BY s.day_of_week, s.lesson_number"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_schedule_for_teacher(self, teacher_id: int,
                                  day: int = None) -> List[Dict]:
        with self.get_conn() as conn:
            query = """
                SELECT s.*, sub.name as subject_name, c.name as class_name,
                       r.number as room_number
                FROM schedule s
                JOIN subjects sub ON s.subject_id = sub.id
                JOIN classes c ON s.class_id = c.id
                JOIN rooms r ON s.room_id = r.id
                WHERE s.teacher_id = ? AND s.is_temporary = 0
            """
            params = [teacher_id]
            if day:
                query += " AND s.day_of_week = ?"
                params.append(day)
            query += " ORDER BY s.day_of_week, s.lesson_number"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_schedule_for_room(self, room_id: int,
                               day: int = None) -> List[Dict]:
        with self.get_conn() as conn:
            query = """
                SELECT s.*, sub.name as subject_name, t.fio as teacher_name,
                       c.name as class_name
                FROM schedule s
                JOIN subjects sub ON s.subject_id = sub.id
                JOIN teachers t ON s.teacher_id = t.id
                JOIN classes c ON s.class_id = c.id
                WHERE s.room_id = ? AND s.is_temporary = 0
            """
            params = [room_id]
            if day:
                query += " AND s.day_of_week = ?"
                params.append(day)
            query += " ORDER BY s.day_of_week, s.lesson_number"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ===== EVENTS =====
    def add_event(self, event_type: str, start_date: str, end_date: str,
                  description: str = "", affected_teachers: List[int] = None,
                  affected_classes: List[int] = None,
                  replacement_teacher_id: int = None) -> int:
        import json
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO events
                   (event_type, start_date, end_date, description,
                    affected_teachers, affected_classes, replacement_teacher_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (event_type, start_date, end_date, description,
                 json.dumps(affected_teachers or []),
                 json.dumps(affected_classes or []),
                 replacement_teacher_id)
            )
            return cur.lastrowid

    def get_active_events(self, on_date: str = None) -> List[Dict]:
        import json
        from datetime import date as dt_date
        with self.get_conn() as conn:
            if on_date is None:
                on_date = dt_date.today().isoformat()
            rows = conn.execute(
                """SELECT * FROM events
                   WHERE is_active=1 AND start_date <= ? AND end_date >= ?""",
                (on_date, on_date)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d['affected_teachers'] = json.loads(d['affected_teachers'])
                d['affected_classes'] = json.loads(d['affected_classes'])
                result.append(d)
            return result

    # ===== VALIDATION =====
    def check_teacher_hours(self, teacher_id: int) -> Dict[str, Any]:
        """Проверка нагрузки учителя с предупреждениями."""
        load = self.get_teacher_load(teacher_id)
        teacher = None
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM teachers WHERE id=?", (teacher_id,)
            ).fetchone()
            if row:
                teacher = dict(row)

        if not teacher:
            return {"error": "Teacher not found"}

        total = load['total_hours']
        max_h = teacher['max_hours_week']
        warn_h = teacher['warn_hours_week']

        result = {
            "teacher_id": teacher_id,
            "fio": teacher['fio'],
            "total_hours": total,
            "max_hours": max_h,
            "warn_hours": warn_h,
            "status": "ok",
            "warnings": []
        }

        if total > warn_h:
            result["status"] = "overload"
            result["warnings"].append(
                f"️ ПРЕВЫШЕНИЕ! Нагрузка {total}ч > порог {warn_h}ч "
                f"(превышение на {total - warn_h}ч)"
            )
        elif total > max_h:
            result["status"] = "warning"
            result["warnings"].append(
                f"⚡ Внимание: нагрузка {total}ч > норма {max_h}ч"
            )

        return result

    def check_room_conflict(self, room_id: int, day: int,
                             lesson: int) -> Optional[Dict]:
        """Проверка конфликта кабинета."""
        with self.get_conn() as conn:
            row = conn.execute(
                """SELECT s.*, c.name as class_name, t.fio as teacher_name,
                          sub.name as subject_name
                   FROM schedule s
                   JOIN classes c ON s.class_id = c.id
                   JOIN teachers t ON s.teacher_id = t.id
                   JOIN subjects sub ON s.subject_id = sub.id
                   WHERE s.room_id = ? AND s.day_of_week = ?
                   AND s.lesson_number = ? AND s.is_temporary = 0""",
                (room_id, day, lesson)
            ).fetchone()
            if row:
                return dict(row)
        return None

    def check_teacher_conflict(self, teacher_id: int, day: int,
                                lesson: int) -> Optional[Dict]:
        """Проверка конфликта учителя."""
        with self.get_conn() as conn:
            row = conn.execute(
                """SELECT s.*, c.name as class_name, sub.name as subject_name,
                          r.number as room_number
                   FROM schedule s
                   JOIN classes c ON s.class_id = c.id
                   JOIN subjects sub ON s.subject_id = sub.id
                   JOIN rooms r ON s.room_id = r.id
                   WHERE s.teacher_id = ? AND s.day_of_week = ?
                   AND s.lesson_number = ? AND s.is_temporary = 0""",
                (teacher_id, day, lesson)
            ).fetchone()
            if row:
                return dict(row)
        return None

    def check_class_conflict(self, class_id: int, day: int,
                              lesson: int) -> Optional[Dict]:
        """Проверка конфликта класса."""
        with self.get_conn() as conn:
            row = conn.execute(
                """SELECT s.*, sub.name as subject_name, t.fio as teacher_name,
                          r.number as room_number
                   FROM schedule s
                   JOIN subjects sub ON s.subject_id = sub.id
                   JOIN teachers t ON s.teacher_id = t.id
                   JOIN rooms r ON s.room_id = r.id
                   WHERE s.class_id = ? AND s.day_of_week = ?
                   AND s.lesson_number = ? AND s.is_temporary = 0""",
                (class_id, day, lesson)
            ).fetchone()
            if row:
                return dict(row)
        return None
