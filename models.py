 """Бизнес-модели и валидация данных."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
import json


class DayOfWeek(Enum):
    MON = 1
    TUE = 2
    WED = 3
    THU = 4
    FRI = 5

    @property
    def name_ru(self):
        names = {1: "Понедельник", 2: "Вторник", 3: "Среда",
                 4: "Четверг", 5: "Пятница"}
        return names[self.value]


@dataclass
class TeacherModel:
    id: int
    fio: str
    max_hours_week: int = 36
    warn_hours_week: int = 40
    no_first_lesson: bool = False
    no_windows: bool = False
    subjects: List[Dict] = field(default_factory=list)
    # subjects = [{"subject_id": 1, "subject_name": "Математика", "hours": 18}, ...]

    @property
    def total_hours(self) -> int:
        return sum(s.get('hours', 0) for s in self.subjects)

    @property
    def is_overloaded(self) -> bool:
        return self.total_hours > self.warn_hours_week

    @property
    def is_warning(self) -> bool:
        return self.total_hours > self.max_hours_week

    def validate(self) -> List[str]:
        errors = []
        if self.total_hours > self.warn_hours_week:
            errors.append(
                f" Критическое превышение: {self.total_hours}ч > "
                f"{self.warn_hours_week}ч (превышение на "
                f"{self.total_hours - self.warn_hours_week}ч)"
            )
        elif self.total_hours > self.max_hours_week:
            errors.append(
                f"⚠️ Превышение нормы: {self.total_hours}ч > "
                f"{self.max_hours_week}ч"
            )
        if not self.subjects:
            errors.append("️ У учителя не назначены предметы")
        return errors


@dataclass
class SubjectModel:
    id: int
    name: str
    room_types: List[str] = field(default_factory=lambda: ["universal"])
    is_group_split: bool = False
    is_double_lesson: bool = False
    difficulty: int = 2

    def validate(self) -> List[str]:
        errors = []
        if self.difficulty < 1 or self.difficulty > 3:
            errors.append("Сложность должна быть 1-3")
        return errors


@dataclass
class ClassModel:
    id: int
    name: str
    op_type: str = "general"  # general, adapted_7_8, adapted_7_9, inclusive
    class_teacher_id: Optional[int] = None
    shift: int = 1
    max_lessons_day: int = 7

    @property
    def is_primary(self) -> bool:
        """Начальная школа (1-4 классы)."""
        try:
            grade = int(self.name[0])
            return grade <= 4
        except (ValueError, IndexError):
            return False

    def validate(self) -> List[str]:
        errors = []
        if self.shift not in (1, 2):
            errors.append("Смена должна быть 1 или 2")
        if self.is_primary and self.max_lessons_day > 4:
            errors.append(
                f"⚠️ Начальный класс {self.name}: макс. 4 урока, "
                f"установлено {self.max_lessons_day}"
            )
        return errors


@dataclass
class RoomModel:
    id: int
    number: str
    room_type: str = "universal"
    capacity: int = 30

    def validate(self) -> List[str]:
        errors = []
        if self.capacity < 1:
            errors.append("Вместимость должна быть > 0")
        return errors


@dataclass
class LessonSlot:
    """Один урок в расписании."""
    class_id: int
    class_name: str
    subject_id: int
    subject_name: str
    teacher_id: int
    teacher_name: str
    room_id: int
    room_number: str
    day: int
    lesson: int
    is_group: bool = False
    group_label: str = ""
    week_type: int = 0  # 0=все, 1=числитель, 2=знаменатель


@dataclass
class ScheduleValidationError:
    """Ошибка валидации расписания."""
    severity: str  # "error", "warning", "info"
    message: str
    entity_type: str  # teacher, class, room, subject
    entity_id: int
    day: Optional[int] = None
    lesson: Optional[int] = None


class ScheduleValidator:
    """Валидатор расписания по всем правилам."""

    def __init__(self, db):
        self.db = db

    def validate_full_schedule(self) -> List[ScheduleValidationError]:
        """Полная проверка расписания."""
        errors = []

        # 1. Проверка нагрузки учителей
        teachers = self.db.get_all_teachers()
        for t in teachers:
            model = TeacherModel(
                id=t['id'], fio=t['fio'],
                max_hours_week=t['max_hours_week'],
                warn_hours_week=t['warn_hours_week'],
                subjects=t['subjects']
            )
            for err in model.validate():
                errors.append(ScheduleValidationError(
                    severity="error" if "Критическое" in err else "warning",
                    message=err,
                    entity_type="teacher",
                    entity_id=t['id']
                ))

        # 2. Проверка конфликтов (задвоений)
        classes = self.db.get_all_classes()
        rooms = self.db.get_all_rooms()

        for day in range(1, 6):
            for lesson in range(1, 9):
                # Конфликты классов
                for cls in classes:
                    conflict = self.db.check_class_conflict(
                        cls['id'], day, lesson
                    )
                    # check_class_conflict возвращает один урок,
                    # но нам нужно проверить задвоение
                    rows = self.db.get_schedule_for_class(cls['id'], day)
                    lessons_at_slot = [
                        r for r in rows if r['lesson_number'] == lesson
                        and not r['is_temporary']
                    ]
                    if len(lessons_at_slot) > 1:
                        errors.append(ScheduleValidationError(
                            severity="error",
                            message=f"Класс {cls['name']} имеет "
                                    f"{len(lessons_at_slot)} уроков "
                                    f"в {DayOfWeek(day).name_ru} {lesson}-й урок",
                            entity_type="class",
                            entity_id=cls['id'],
                            day=day, lesson=lesson
                        ))

                # Конфликты учителей
                for t in teachers:
                    rows = self.db.get_schedule_for_teacher(t['id'], day)
                    lessons_at_slot = [
                        r for r in rows if r['lesson_number'] == lesson
                        and not r['is_temporary']
                    ]
                    if len(lessons_at_slot) > 1:
                        names = ", ".join(
                            f"{r['class_name']}({r['subject_name']})"
                            for r in lessons_at_slot
                        )
                        errors.append(ScheduleValidationError(
                            severity="error",
                            message=f"Учитель {t['fio']} задвоен: {names}",
                            entity_type="teacher",
                            entity_id=t['id'],
                            day=day, lesson=lesson
                        ))

                # Конфликты кабинетов
                for room in rooms:
                    rows = self.db.get_schedule_for_room(room['id'], day)
                    lessons_at_slot = [
                        r for r in rows if r['lesson_number'] == lesson
                        and not r['is_temporary']
                    ]
                    if len(lessons_at_slot) > 1:
                        names = ", ".join(
                            f"{r['class_name']}({r['subject_name']})"
                            for r in lessons_at_slot
                        )
                        errors.append(ScheduleValidationError(
                            severity="error",
                            message=f"Кабинет {room['number']} задвоен: {names}",
                            entity_type="room",
                            entity_id=room['id'],
                            day=day, lesson=lesson
                        ))

        return errors

    def check_room_specialization(self, subject_id: int,
                                   room_id: int) -> bool:
        """Проверка соответствия кабинета предмету."""
        # Получить допустимые типы для предмета
        subjects = self.db.get_all_subjects()
        subject = next((s for s in subjects if s['id'] == subject_id), None)
        if not subject:
            return True

        rooms = self.db.get_all_rooms()
        room = next((r for r in rooms if r['id'] == room_id), None)
        if not room:
            return True

        allowed = subject.get('room_types', ['universal'])
        if 'universal' in allowed:
            return True
        return room['room_type'] in allowed
