"""
Главное приложение: CLI + FastAPI сервер.
"""

import sys
import json
from pathlib import Path
from datetime import date, datetime
from typing import Optional, List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from database import Database
from models import (
    TeacherModel, SubjectModel, ClassModel, RoomModel,
    ScheduleValidator, DayOfWeek
)
from solver import ScheduleSolver, SolverConfig
from config import Normatives, SUBJECT_DIFFICULTY, SUBJECT_ROOM_MAP, RoomType


console = Console()


class SchoolSchedulerApp:
    """Основное приложение для управления расписанием."""

    def __init__(self):
        self.db = Database()
        self.validator = ScheduleValidator(self.db)

    # ===== ИНИЦИАЛИЗАЦИЯ ДАННЫХ =====

    def init_demo_data(self):
        """Заполнить БД демонстрационными данными."""
        console.print(Panel(" Инициализация демонстрационных данных",
                            style="bold blue"))

        # Кабинеты
        rooms_data = [
            ("1.1", "universal", 30), ("1.2", "universal", 30),
            ("1.3", "universal", 30), ("2.1", "universal", 30),
            ("2.2", "universal", 30), ("2.3", "universal", 30),
            ("3.0", "math", 30), ("3.1", "math", 30),
            ("3.2", "universal", 30), ("3.3", "universal", 30),
            ("3.4", "computer", 15), ("3.5", "physics", 25),
            ("3.8", "universal", 30), ("3.10", "biology", 25),
            ("3.12", "language", 20), ("3.15", "labor", 20),
            ("1.1/3.15", "labor", 20),
            ("2.8", "universal", 30), ("2.11", "history", 30),
            ("сп.зал", "sport", 40),
        ]
        room_ids = {}
        for num, rtype, cap in rooms_data:
            rid = self.db.add_room(num, rtype, cap)
            room_ids[num] = rid
            console.print(f"   Кабинет {num} ({rtype})")

        # Предметы
        subjects_data = [
            ("Русский язык", ["universal"], False, False, 2),
            ("Литература", ["universal"], False, False, 2),
            ("Математика", ["universal", "math"], False, False, 3),
            ("Алгебра", ["universal", "math"], False, False, 3),
            ("Геометрия", ["universal", "math"], False, False, 3),
            ("Физика", ["universal", "physics"], False, True, 3),
            ("Химия", ["universal", "chemistry"], False, True, 3),
            ("Биология", ["universal", "biology"], False, False, 2),
            ("География", ["universal"], False, False, 2),
            ("История", ["universal", "history"], False, False, 2),
            ("Обществознание", ["universal", "history"], False, False, 2),
            ("Информатика", ["universal", "computer"], False, False, 2),
            ("Английский язык", ["universal", "language"], True, False, 2),
            ("Физическая культура", ["universal", "sport"], False, False, 1),
            ("ОБЗР", ["universal", "sport"], False, False, 1),
            ("Труд", ["universal", "labor"], True, False, 1),
            ("Технология", ["universal", "labor"], True, False, 1),
            ("ИЗО", ["universal", "art"], False, False, 1),
            ("Музыка", ["universal", "art"], False, False, 1),
        ]
        subject_ids = {}
        for name, rtypes, is_group, is_double, diff in subjects_data:
            sid = self.db.add_subject(name, rtypes, is_group, is_double, diff)
            subject_ids[name] = sid
            console.print(f"  📚 Предмет: {name}")

        # Учителя
        teachers_data = [
            ("Иванова А.С.", 36, 40, False, False,
             [{"subject": "Русский язык", "hours": 18},
              {"subject": "Литература", "hours": 10}]),
            ("Петрова М.И.", 36, 40, False, False,
             [{"subject": "Математика", "hours": 20},
              {"subject": "Алгебра", "hours": 12}]),
            ("Сидорова Е.В.", 36, 40, True, False,  # no_first_lesson
             [{"subject": "Физика", "hours": 16}]),
            ("Козлова Н.П.", 36, 40, False, False,
             [{"subject": "Химия", "hours": 14},
              {"subject": "Биология", "hours": 8}]),
            ("Михайлова А.В.", 36, 40, False, False,
             [{"subject": "История", "hours": 18},
              {"subject": "Обществознание", "hours": 6}]),
            ("Волкова Д.А.", 36, 40, False, False,
             [{"subject": "Английский язык", "hours": 22}]),
            ("Новикова О.Р.", 36, 40, False, False,
             [{"subject": "Физическая культура", "hours": 20},
              {"subject": "ОБЗР", "hours": 4}]),
            ("Морозова Т.К.", 36, 40, False, False,
             [{"subject": "Информатика", "hours": 14}]),
            ("Лебедева С.Н.", 36, 40, False, False,
             [{"subject": "География", "hours": 12}]),
            ("Соколова И.М.", 30, 36, False, False,
             [{"subject": "ИЗО", "hours": 6},
              {"subject": "Музыка", "hours": 6}]),
            ("Попова А.Г.", 36, 40, False, False,
             [{"subject": "Труд", "hours": 16},
              {"subject": "Технология", "hours": 8}]),
        ]
        teacher_ids = {}
        for fio, max_h, warn_h, no_first, no_win, subjects in teachers_data:
            # Преобразовать имена предметов в id
            subj_entries = []
            for s in subjects:
                sid = subject_ids.get(s['subject'])
                if sid:
                    subj_entries.append({
                        "subject_id": sid,
                        "subject": s['subject'],
                        "hours": s['hours']
                    })
            tid = self.db.add_teacher(
                fio, max_h, warn_h, subj_entries, no_first, no_win
            )
            teacher_ids[fio] = tid
            console.print(f"  👨‍🏫 Учитель: {fio} ({sum(s['hours'] for s in subjects)}ч)")

        # Классы
        classes_data = [
            ("5А", "general", None, 1, 7),
            ("5Б", "general", None, 1, 7),
            ("5В", "general", None, 1, 7),
            ("6А", "general", None, 2, 7),
            ("6Б", "general", None, 2, 7),
            ("7А", "general", None, 1, 7),
            ("7Б", "general", None, 1, 7),
            ("8А", "general", None, 1, 7),
            ("9А", "general", None, 1, 7),
            ("10А", "general", None, 1, 7),
            ("11А", "general", None, 1, 7),
        ]
        class_ids = {}
        for name, op, ct, shift, max_l in classes_data:
            ct_id = teacher_ids.get(ct) if ct else None
            cid = self.db.add_class(name, op, ct_id, shift)
            class_ids[name] = cid
            console.print(f"   Класс: {name} ({op}, {shift} смена)")

        # Расписание звонков — 1 смена
        bells_1 = [
            (1, 1, "08:00", "08:45", 10),
            (1, 2, "08:55", "09:40", 10),
            (1, 3, "09:50", "10:35", 15),
            (1, 4, "10:50", "11:35", 10),
            (1, 5, "11:45", "12:30", 10),
            (1, 6, "12:40", "13:25", 20),  # обед
            (1, 7, "13:45", "14:30", 10),
            (1, 8, "14:40", "15:25", 0),
        ]
        for shift, num, start, end, brk in bells_1:
            self.db.add_bell(shift, num, start, end, brk)

        # 2 смена
        bells_2 = [
            (2, 1, "14:00", "14:45", 10),
            (2, 2, "14:55", "15:40", 10),
            (2, 3, "15:50", "16:35", 15),
            (2, 4, "16:50", "17:35", 10),
            (2, 5, "17:45", "18:30", 10),
            (2, 6, "18:40", "19:25", 0),
        ]
        for shift, num, start, end, brk in bells_2:
            self.db.add_bell(shift, num, start, end, brk)

        # Назначить нагрузку учителям по классам
        # (упрощённо: распределяем часы учителей по классам)
        self._assign_load(teacher_ids, subject_ids, class_ids)

        console.print(Panel("✅ Данные инициализированы!", style="bold green"))

    def _assign_load(self, teacher_ids, subject_ids, class_ids):
        """Распределить нагрузку учителей по классам."""
        # Упрощённое распределение для демо
        assignments = [
            # (teacher, subject, class, hours)
            ("Иванова А.С.", "Русский язык", "5А", 5),
            ("Иванова А.С.", "Русский язык", "5Б", 5),
            ("Иванова А.С.", "Литература", "5А", 3),
            ("Иванова А.С.", "Литература", "5Б", 3),
            ("Петрова М.И.", "Математика", "5А", 5),
            ("Петрова М.И.", "Математика", "5Б", 5),
            ("Сидорова Е.В.", "Физика", "7А", 2),
            ("Сидорова Е.В.", "Физика", "7Б", 2),
            ("Козлова Н.П.", "Химия", "8А", 2),
            ("Козлова Н.П.", "Биология", "5А", 2),
            ("Михайлова А.В.", "История", "5А", 2),
            ("Михайлова А.В.", "История", "5Б", 2),
            ("Волкова Д.А.", "Английский язык", "5А", 3),
            ("Волкова Д.А.", "Английский язык", "5Б", 3),
            ("Новикова О.Р.", "Физическая культура", "5А", 3),
            ("Новикова О.Р.", "Физическая культура", "5Б", 3),
            ("Морозова Т.К.", "Информатика", "7А", 1),
            ("Лебедева С.Н.", "География", "5А", 2),
            ("Соколова И.М.", "ИЗО", "5А", 1),
            ("Попова А.Г.", "Труд", "5А", 2),
        ]
        for t_name, s_name, c_name, hours in assignments:
            tid = teacher_ids.get(t_name)
            sid = subject_ids.get(s_name)
            cid = class_ids.get(c_name)
            if tid and sid and cid:
                self.db.set_teacher_load(tid, sid, cid, hours)

    # ===== МЕНЮ =====

    def run_cli(self):
        """Запуск консольного интерфейса."""
        console.print(Panel(
            "[bold blue]🏫 ШКОЛЬНОЕ РАСПИСАНИЕ[/bold blue]\n"
            "Система составления и ведения расписания",
            box=box.DOUBLE
        ))

        while True:
            console.print("\n[bold]Главное меню:[/bold]")
            console.print("  1. 📋 Справочники (учителя, предметы, классы, кабинеты)")
            console.print("  2. ⚙️  Настройка нагрузки учителей")
            console.print("  3. 🔔 Расписание звонков")
            console.print("  4. 🧮 Сгенерировать расписание")
            console.print("  5. 📊 Просмотр расписания")
            console.print("  6. ✅ Проверка расписания")
            console.print("  7. 🔄 Внесение изменений (замены, болезни)")
            console.print("  8. 📥 Импорт/Экспорт данных")
            console.print("  0. 🚪 Выход")

            choice = console.input("\n[bold]Выбор:[/bold] ").strip()

            if choice == "1":
                self._menu_references()
            elif choice == "2":
                self._menu_load()
            elif choice == "3":
                self._menu_bells()
            elif choice == "4":
                self._menu_generate()
            elif choice == "5":
                self._menu_view()
            elif choice == "6":
                self._menu_validate()
            elif choice == "7":
                self._menu_changes()
            elif choice == "8":
                self._menu_import_export()
            elif choice == "0":
                console.print("[green]До свидания![/green]")
                break
            else:
                console.print("[red]Неверный выбор[/red]")

    def _menu_references(self):
        """Меню справочников."""
        while True:
            console.print("\n[bold]📋 Справочники:[/bold]")
            console.print("  1. 👨‍🏫 Учителя")
            console.print("  2. 📚 Предметы")
            console.print("  3. 🎓 Классы")
            console.print("  4. 📍 Кабинеты")
            console.print("  5. 🏫 Инициализировать демо-данные")
            console.print("  0. ← Назад")

            choice = console.input("\n[bold]Выбор:[/bold] ").strip()

            if choice == "1":
                self._show_teachers()
            elif choice == "2":
                self._show_subjects()
            elif choice == "3":
                self._show_classes()
            elif choice == "4":
                self._show_rooms()
            elif choice == "5":
                self.init_demo_data()
            elif choice == "0":
                break

    def _show_teachers(self):
        """Показать список учителей с нагрузкой."""
        teachers = self.db.get_all_teachers()
        if not teachers:
            console.print("[yellow]Список учителей пуст[/yellow]")
            return

        table = Table(title="👨‍🏫 Преподаватели", box=box.ROUNDED)
        table.add_column("ID", style="dim")
        table.add_column("ФИО")
        table.add_column("Предметы", max_width=30)
        table.add_column("Часы", justify="right")
        table.add_column("Норма", justify="right")
        table.add_column("Статус")

        for t in teachers:
            model = TeacherModel(
                id=t['id'], fio=t['fio'],
                max_hours_week=t['max_hours_week'],
                warn_hours_week=t['warn_hours_week'],
                subjects=t['subjects']
            )
            subjects_str = ", ".join(
                f"{s.get('subject', '?')}({s.get('hours', 0)}ч)"
                for s in t['subjects']
            )

            if model.is_overloaded:
                status = "[red]⛔ ПЕРЕБОР[/red]"
            elif model.is_warning:
                status = "[yellow]️ Превышение[/yellow]"
            else:
                status = "[green]✅ Норма[/green]"

            table.add_row(
                str(t['id']), t['fio'], subjects_str,
                str(model.total_hours), str(t['max_hours_week']), status
            )

        console.print(table)

        # Детали по учителю
        tid = console.input("\nID учителя для деталей (Enter — назад): ").strip()
        if tid:
            self._show_teacher_detail(int(tid))

    def _show_teacher_detail(self, teacher_id: int):
        """Детальная информация об учителе."""
        teachers = self.db.get_all_teachers()
        teacher = next((t for t in teachers if t['id'] == teacher_id), None)
        if not teacher:
            console.print("[red]Учитель не найден[/red]")
            return

        model = TeacherModel(
            id=teacher['id'], fio=teacher['fio'],
            max_hours_week=teacher['max_hours_week'],
            warn_hours_week=teacher['warn_hours_week'],
            subjects=teacher['subjects']
        )

        console.print(Panel(
            f"[bold]{teacher['fio']}[/bold]\n"
            f"Норма: {teacher['max_hours_week']}ч | "
            f"Порог предупреждения: {teacher['warn_hours_week']}ч\n"
            f"Текущая нагрузка: {model.total_hours}ч\n"
            f"1-й урок: {'❌ запрещён' if teacher['no_first_lesson'] else '✅ разрешён'}\n"
            f"Без окон: {'✅ да' if teacher['no_windows'] else ' нет'}",
            title="Карточка учителя"
        ))

        # Нагрузка по классам
        load = self.db.get_full_load(teacher_id)
        if load:
            table = Table(title="Нагрузка по классам")
            table.add_column("Предмет")
            table.add_column("Класс")
            table.add_column("Часов/нед", justify="right")
            for l in load:
                table.add_row(l['subject_name'], l['class_name'],
                              str(l['hours_per_week']))
            console.print(table)

        # Проверка
        check = self.db.check_teacher_hours(teacher_id)
        for w in check.get('warnings', []):
            console.print(f"  {w}")

    def _show_subjects(self):
        """Показать предметы."""
        subjects = self.db.get_all_subjects()
        if not subjects:
            console.print("[yellow]Список предметов пуст[/yellow]")
            return

        table = Table(title="📚 Предметы", box=box.ROUNDED)
        table.add_column("ID")
        table.add_column("Название")
        table.add_column("Типы кабинетов")
        table.add_column("Группы")
        table.add_column("Сдвоен.")
        table.add_column("Сложность")

        for s in subjects:
            table.add_row(
                str(s['id']), s['name'],
                ", ".join(s['room_types']),
                "✅" if s['is_group_split'] else "—",
                "✅" if s['is_double_lesson'] else "—",
                str(s['difficulty']),
            )
        console.print(table)

    def _show_classes(self):
        """Показать классы."""
        classes = self.db.get_all_classes()
        if not classes:
            console.print("[yellow]Список классов пуст[/yellow]")
            return

        table = Table(title=" Классы", box=box.ROUNDED)
        table.add_column("ID")
        table.add_column("Название")
        table.add_column("ОП")
        table.add_column("Смена")
        table.add_column("Макс. уроков/день")

        for c in classes:
            table.add_row(
                str(c['id']), c['name'], c['op_type'],
                str(c['shift']), str(c['max_lessons_day'])
            )
        console.print(table)

    def _show_rooms(self):
        """Показать кабинеты."""
        rooms = self.db.get_all_rooms()
        if not rooms:
            console.print("[yellow]Список кабинетов пуст[/yellow]")
            return

        table = Table(title="📍 Кабинеты", box=box.ROUNDED)
        table.add_column("ID")
        table.add_column("Номер")
        table.add_column("Тип")
        table.add_column("Вместимость")

        for r in rooms:
            table.add_row(str(r['id']), r['number'], r['room_type'],
                          str(r['capacity']))
        console.print(table)

    def _menu_load(self):
        """Меню настройки нагрузки."""
        console.print("\n[bold]⚙️  Настройка нагрузки учителей[/bold]")
        console.print("Нагрузка назначается: Учитель → Предмет → Класс → Часы/неделю")

        teachers = self.db.get_all_teachers()
        subjects = self.db.get_all_subjects()
        classes = self.db.get_all_classes()

        if not (teachers and subjects and classes):
            console.print("[red]Недостаточно данных. Сначала заполните справочники.[/red]")
            return

        tid = int(console.input("ID учителя: "))
        sid = int(console.input("ID предмета: "))
        cid = int(console.input("ID класса: "))
        hours = int(console.input("Часов в неделю: "))

        self.db.set_teacher_load(tid, sid, cid, hours)
        console.print("[green]✅ Нагрузка назначена[/green]")

        # Проверка
        check = self.db.check_teacher_hours(tid)
        for w in check.get('warnings', []):
            console.print(f"  {w}")

    def _menu_bells(self):
        """Меню расписания звонков."""
        console.print("\n[bold]🔔 Расписание звонков[/bold]")

        for shift in [1, 2]:
            bells = self.db.get_bell_schedule(shift)
            if bells:
                table = Table(title=f"{shift} смена")
                table.add_column("№")
                table.add_column("Начало")
                table.add_column("Конец")
                table.add_column("Перемена")
                for b in bells:
                    table.add_row(
                        str(b['lesson_number']),
                        b['start_time'], b['end_time'],
                        f"{b['break_minutes']} мин"
                    )
                console.print(table)

    def _menu_generate(self):
        """Генерация расписания."""
        console.print(Panel(
            "[bold]🧮 Генерация расписания[/bold]\n"
            "Используется CP-SAT Solver (Google OR-Tools)\n"
            "Время решения: до 5 минут",
            style="yellow"
        ))

        max_time = int(console.input(
            "Макс. время решения в секундах [300]: "
        ) or 300)

        config = SolverConfig(max_time_seconds=max_time)
        solver = ScheduleSolver(self.db, config)

        console.print("\n[bold]⏳ Решение задачи...[/bold]")
        result = solver.solve()

        if result['status'] in ('optimal', 'feasible'):
            console.print(
                f"\n[green]✅ Решение найдено! "
                f"Статус: {result['status']}[/green]"
            )
            console.print(
                f"Всего уроков: {result['stats']['total_lessons']}"
            )

            # Сохранить
            save = console.input("\nСохранить расписание? (y/n): ").strip()
            if save.lower() == 'y':
                self.db.save_schedule(result['lessons'])
                console.print("[green]✅ Расписание сохранено![/green]")

                # Показать превью
                self._show_schedule_preview(result['lessons'])
            else:
                console.print("[yellow]Расписание не сохранено[/yellow]")
        else:
            console.print(f"\n[red]❌ {result['message']}[/red]")
            console.print(
                "[yellow]Попробуйте ослабить ограничения или "
                "увеличить время решения[/yellow]"
            )

    def _show_schedule_preview(self, lessons: List[Dict]):
        """Показать превью расписания."""
        # Группировка по классам
        by_class = {}
        for l in lessons:
            cname = l['class_name']
            if cname not in by_class:
                by_class[cname] = {}
            day = l['day']
            if day not in by_class[cname]:
                by_class[cname][day] = {}
            by_class[cname][day][l['lesson']] = l

        # Показать первые 3 класса
        for cname in list(by_class.keys())[:3]:
            table = Table(title=f"📅 {cname}", box=box.SIMPLE)
            table.add_column("Урок")
            for d in range(1, 6):
                table.add_column(DayOfWeek(d).name_ru[:3])

            for lesson in range(1, 9):
                row = [str(lesson)]
                for d in range(1, 6):
                    l = by_class[cname].get(d, {}).get(lesson)
                    if l:
                        row.append(
                            f"{l['subject_name'][:10]}\n"
                            f"{l['room_number']}"
                        )
                    else:
                        row.append("—")
                table.add_row(*row)

            console.print(table)
            console.print()

    def _menu_view(self):
        """Просмотр расписания."""
        console.print("\n[bold]📊 Просмотр расписания[/bold]")
        console.print("  1. По классу")
        console.print("  2. По учителю")
        console.print("  3. По кабинету")

        choice = console.input("Выбор: ").strip()

        if choice == "1":
            classes = self.db.get_all_classes()
            for c in classes:
                console.print(f"  {c['id']}. {c['name']}")
            cid = int(console.input("ID класса: "))

            table = Table(title=f"📅 Расписание класса", box=box.ROUNDED)
            table.add_column("Урок")
            for d in range(1, 6):
                table.add_column(DayOfWeek(d).name_ru[:3])

            schedule = self.db.get_schedule_for_class(cid)
            by_day_lesson = {}
            for s in schedule:
                key = (s['day_of_week'], s['lesson_number'])
                by_day_lesson[key] = s

            for lesson in range(1, 9):
                row = [str(lesson)]
                for d in range(1, 6):
                    s = by_day_lesson.get((d, lesson))
                    if s:
                        row.append(
                            f"{s['subject_name'][:12]}\n"
                            f"{s['teacher_name'][:12]}\n"
                            f"каб.{s['room_number']}"
                        )
                    else:
                        row.append("—")
                table.add_row(*row)

            console.print(table)

        elif choice == "2":
            teachers = self.db.get_all_teachers()
            for t in teachers:
                console.print(f"  {t['id']}. {t['fio']}")
            tid = int(console.input("ID учителя: "))

            table = Table(title=f" Расписание учителя", box=box.ROUNDED)
            table.add_column("Урок")
            for d in range(1, 6):
                table.add_column(DayOfWeek(d).name_ru[:3])

            schedule = self.db.get_schedule_for_teacher(tid)
            by_day_lesson = {}
            for s in schedule:
                key = (s['day_of_week'], s['lesson_number'])
                by_day_lesson[key] = s

            for lesson in range(1, 9):
                row = [str(lesson)]
                for d in range(1, 6):
                    s = by_day_lesson.get((d, lesson))
                    if s:
                        row.append(
                            f"{s['class_name']} {s['subject_name'][:10]}\n"
                            f"каб.{s['room_number']}"
                        )
                    else:
                        row.append("—")
                table.add_row(*row)

            console.print(table)

    def _menu_validate(self):
        """Проверка расписания."""
        console.print("\n[bold]✅ Проверка расписания[/bold]")
        errors = self.validator.validate_full_schedule()

        if not errors:
            console.print("[green]✅ Ошибок не найдено! "
                          "Расписание корректно.[/green]")
        else:
            table = Table(title="Результаты проверки", box=box.ROUNDED)
            table.add_column("Тип")
            table.add_column("Сообщение")
            table.add_column("Сущность")

            for e in errors:
                severity = {
                    "error": "[red] ОШИБКА[/red]",
                    "warning": "[yellow]⚠️ Внимание[/yellow]",
                    "info": "[blue]️ Инфо[/blue]",
                }.get(e.severity, e.severity)

                table.add_row(severity, e.message,
                              f"{e.entity_type}#{e.entity_id}")

            console.print(table)

    def _menu_changes(self):
        """Внесение изменений (замены, болезни)."""
        console.print("\n[bold]🔄 Внесение изменений[/bold]")
        console.print("  1. Замена учителя (болезнь)")
        console.print("  2. Карантин класса")
        console.print("  3. Внештатное мероприятие")
        console.print("  4. Активный день (отмена уроков)")

        choice = console.input("Выбор: ").strip()

        if choice == "1":
            self._replace_teacher()
        elif choice == "2":
            self._quarantine_class()
        elif choice == "3":
            self._add_event()

    def _replace_teacher(self):
        """Замена учителя."""
        teachers = self.db.get_all_teachers()
        console.print("\nУчителя:")
        for t in teachers:
            console.print(f"  {t['id']}. {t['fio']}")

        tid = int(console.input("ID заболевшего учителя: "))
        rid = int(console.input("ID заменяющего учителя: "))

        start = console.input("Дата начала (ГГГГ-ММ-ДД): ")
        end = console.input("Дата окончания (ГГГГ-ММ-ДД): ")

        eid = self.db.add_event(
            "illness", start, end,
            f"Замена: {teachers[tid-1]['fio']} → "
            f"{teachers[rid-1]['fio']}",
            affected_teachers=[tid],
            replacement_teacher_id=rid
        )
        console.print(f"[green]✅ Замена оформлена (событие #{eid})[/green]")
        console.print("[yellow]️ Необходимо пересгенерировать расписание "
                      "на указанный период[/yellow]")

    def _quarantine_class(self):
        """Карантин класса."""
        classes = self.db.get_all_classes()
        console.print("\nКлассы:")
        for c in classes:
            console.print(f"  {c['id']}. {c['name']}")

        cid = int(console.input("ID класса на карантин: "))
        start = console.input("Дата начала: ")
        end = console.input("Дата окончания: ")

        self.db.add_event(
            "quarantine", start, end,
            f"Карантин класса {classes[cid-1]['name']}",
            affected_classes=[cid]
        )
        console.print("[green]✅ Карантин оформлен[/green]")

    def _add_event(self):
        """Добавить внештатное событие."""
        event_type = console.input(
            "Тип (holiday/event/sanitary_day): "
        )
        start = console.input("Дата начала: ")
        end = console.input("Дата окончания: ")
        desc = console.input("Описание: ")

        self.db.add_event(event_type, start, end, desc)
        console.print("[green]✅ Событие добавлено[/green]")

    def _menu_import_export(self):
        """Импорт/Экспорт."""
        console.print("\n[bold]📥 Импорт/Экспорт[/bold]")
        console.print("  1. Экспорт расписания в JSON")
        console.print("  2. Импорт нагрузки из JSON")

        choice = console.input("Выбор: ").strip()

        if choice == "1":
            classes = self.db.get_all_classes()
            data = {}
            for c in classes:
                schedule = self.db.get_schedule_for_class(c['id'])
                data[c['name']] = schedule

            with open("schedule_export.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            console.print("[green]✅ Экспортировано в schedule_export.json[/green]")


def main():
    app = SchoolSchedulerApp()
    app.run_cli()


if __name__ == "__main__":
    main()
