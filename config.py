"""Конфигурация приложения. Все нормативы и ограничения."""

from dataclasses import dataclass, field
from typing import Dict, List
from enum import Enum


class Shift(Enum):
    FIRST = 1   # 1 смена
    SECOND = 2  # 2 смена


class RoomType(Enum):
    """Типы кабинетов по СанПиН и предметной специализации."""
    UNIVERSAL = "universal"           # Любой предмет
    MATH = "math"                     # Математика
    PHYSICS = "physics"               # Физика (лабораторное оборудование)
    CHEMISTRY = "chemistry"           # Химия (вытяжка, реактивы)
    BIOLOGY = "biology"               # Биология (микролаборатория)
    COMPUTER = "computer"             # Информатика (компьютеры)
    LANGUAGE = "language"             # Иностранные языки (лингвалаб)
    SPORT = "sport"                   # Спортзал
    LABOR = "labor"                   # Трудовая мастерская (мальч./девч.)
    ART = "art"                       # ИЗО/Музыка
    HISTORY = "history"               # История/Обществознание
    PRIMARY = "primary"               # Начальная школа


class LessonType(Enum):
    """Типы уроков."""
    REGULAR = "regular"
    DOUBLE = "double"       # Сдвоенный урок (химия, физика лаб.)
    GROUP = "group"         # Деление класса на группы (ин.яз, труд, информатика)
    ELECTIVE = "elective"   # Факультатив/электив


class ConstraintType(Enum):
    """Типы ограничений."""
    TEACHER_MAX_HOURS = "teacher_max_hours"
    TEACHER_NO_WINDOWS = "teacher_no_windows"
    TEACHER_FIXED_DAYS = "teacher_fixed_days"
    CLASS_MAX_LESSONS_PER_DAY = "class_max_per_day"
    SUBJECT_DIFFICULTY_SPREAD = "subject_spread"  # Сложные предметы не подряд
    ROOM_SPECIALIZATION = "room_specialization"
    NO_LAST_LESSON_SPORT = "no_last_sport"
    TEACHER_NO_FIRST_LESSON = "teacher_no_first"


# Нормативы по СанПиН и Трудовому кодексу РФ
@dataclass
class Normatives:
    MAX_TEACHER_HOURS_WEEK: int = 36        # Макс. нагрузка учителя (ставки)
    MAX_TEACHER_HOURS_WARN: int = 40        # Порог предупреждения
    MAX_LESSONS_PER_DAY_CLASS: int = 7      # Макс. уроков в день для класса
    MAX_LESSONS_PER_DAY_PRIMARY: int = 4    # Начальная школа
    MIN_BREAK_MINUTES: int = 10             # Мин. перемена
    MAX_BREAK_MINUTES: int = 30             # Макс. перемена (без обеда)
    LUNCH_BREAK_MIN: int = 30               # Обеденная перемена
    MAX_CONSECUTIVE_DIFFICULT: int = 2      # Макс. сложных предметов подряд


# Сложность предметов (для равномерного распределения)
SUBJECT_DIFFICULTY: Dict[str, int] = {
    "Математика": 3, "Алгебра": 3, "Геометрия": 3,
    "Физика": 3, "Химия": 3,
    "Русский язык": 2, "Литература": 2,
    "История": 2, "Обществознание": 2,
    "Биология": 2, "География": 2,
    "Информатика": 2,
    "Английский язык": 2, "Немецкий язык": 2,
    "Физическая культура": 1, "ОБЗР": 1,
    "Труд": 1, "ИЗО": 1, "Музыка": 1,
    "Технология": 1,
}

# Сопоставление предметов и типов кабинетов
SUBJECT_ROOM_MAP: Dict[str, List[RoomType]] = {
    "Математика": [RoomType.UNIVERSAL, RoomType.MATH],
    "Алгебра": [RoomType.UNIVERSAL, RoomType.MATH],
    "Геометрия": [RoomType.UNIVERSAL, RoomType.MATH],
    "Физика": [RoomType.UNIVERSAL, RoomType.PHYSICS],
    "Химия": [RoomType.UNIVERSAL, RoomType.CHEMISTRY],
    "Биология": [RoomType.UNIVERSAL, RoomType.BIOLOGY],
    "Информатика": [RoomType.UNIVERSAL, RoomType.COMPUTER],
    "Английский язык": [RoomType.UNIVERSAL, RoomType.LANGUAGE],
    "Немецкий язык": [RoomType.UNIVERSAL, RoomType.LANGUAGE],
    "Физическая культура": [RoomType.UNIVERSAL, RoomType.SPORT],
    "ОБЗР": [RoomType.UNIVERSAL, RoomType.SPORT],
    "Труд": [RoomType.UNIVERSAL, RoomType.LABOR],
    "Технология": [RoomType.UNIVERSAL, RoomType.LABOR],
    "ИЗО": [RoomType.UNIVERSAL, RoomType.ART],
    "Музыка": [RoomType.UNIVERSAL, RoomType.ART],
    "История": [RoomType.UNIVERSAL, RoomType.HISTORY],
    "Обществознание": [RoomType.UNIVERSAL, RoomType.HISTORY],
}

# Часы по учебному плану (пример для ФГОС, настраивается)
# Формат: {предмет: {класс: часов_в_неделю}}
CURRICULUM_HOURS: Dict[str, Dict[str, int]] = {
    "Русский язык": {"5": 5, "6": 5, "7": 4, "8": 4, "9": 3, "10": 3, "11": 3},
    "Литература": {"5": 3, "6": 3, "7": 3, "8": 3, "9": 3, "10": 3, "11": 3},
    "Математика": {"5": 5, "6": 5},
    "Алгебра": {"7": 4, "8": 4, "9": 4, "10": 5, "11": 5},
    "Геометрия": {"7": 2, "8": 2, "9": 2, "10": 3, "11": 3},
    "Физика": {"7": 2, "8": 2, "9": 3, "10": 3, "11": 3},
    "Химия": {"8": 2, "9": 2, "10": 3, "11": 3},
    "Биология": {"5": 2, "6": 2, "7": 2, "8": 2, "9": 2, "10": 2, "11": 2},
    "География": {"5": 2, "6": 2, "7": 2, "8": 2, "9": 2, "10": 2, "11": 2},
    "История": {"5": 2, "6": 2, "7": 2, "8": 2, "9": 3, "10": 3, "11": 3},
    "Обществознание": {"6": 1, "7": 1, "8": 1, "9": 2, "10": 2, "11": 2},
    "Информатика": {"7": 1, "8": 1, "9": 2, "10": 2, "11": 2},
    "Английский язык": {"5": 3, "6": 3, "7": 3, "8": 3, "9": 3, "10": 3, "11": 3},
    "Физическая культура": {"5": 3, "6": 3, "7": 3, "8": 3, "9": 3, "10": 3, "11": 3},
    "ОБЗР": {"10": 1, "11": 1},
    "Труд": {"5": 2, "6": 2, "7": 2, "8": 2, "9": 2},
    "ИЗО": {"5": 1, "6": 1, "7": 1},
    "Музыка": {"5": 1, "6": 1, "7": 1},
}

