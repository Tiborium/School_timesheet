"""
Генератор школьного расписания на базе Google OR-Tools (CP-SAT Solver).

Алгоритм:
1. Формируем множество переменных: x[class, subject, teacher, day, lesson] = room
2. Задаём жёсткие ограничения (hard constraints):
   - Один учитель в одно время — один класс
   - Один класс в одно время — один урок
   - Один кабинет в одно время — один урок
   - Предмет только в подходящем кабинете
   - Нагрузка учителя не превышает максимум
   - Часы предмета в классе = учебный план
3. Задаём мягкие ограничения (soft constraints) для оптимизации:
   - Равномерное распределение сложных предметов
   - Минимизация окон у учителей
   - Физкультура не последним уроком
   - Предпочтения учителей по дням
4. Решаем оптимизационную задачу.
"""

from ortools.sat.python import cp_model
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import json


@dataclass
class SolverConfig:
    """Конфигурация солвера."""
    max_time_seconds: int = 300  # Макс. время решения (5 мин)
    num_workers: int = 4         # Параллельные потоки
    optimize_soft: bool = True   # Оптимизировать мягкие ограничения


class ScheduleSolver:
    """CP-SAT солвер для школьного расписания."""

    def __init__(self, db, config: SolverConfig = None):
        self.db = db
        self.config = config or SolverConfig()
        self.model = cp_model.CpModel()
        self.vars = {}
        self.solution = []

    def solve(self) -> Dict:
        """
        Запуск генерации расписания.
        Возвращает: {"status": "optimal"|"feasible"|"infeasible",
                      "lessons": [...], "stats": {...}}
        """
        # Собрать данные
        teachers = self.db.get_all_teachers()
        subjects = self.db.get_all_subjects()
        classes = self.db.get_all_classes()
        rooms = self.db.get_all_rooms()
        bells = {}
        for shift in [1, 2]:
            bells[shift] = self.db.get_bell_schedule(shift)

        if not teachers or not subjects or not classes or not rooms:
            return {"status": "error",
                    "message": "Недостаточно данных. Заполните справочники."}

        # Собрать нагрузку (teacher -> subject -> class -> hours)
        load_map: Dict[int, Dict[int, Dict[int, int]]] = {}
        for t in teachers:
            load_map[t['id']] = {}
            for subj_entry in t['subjects']:
                sid = subj_entry.get('subject_id')
                if sid is None:
                    # Найти по имени
                    for s in subjects:
                        if s['name'] == subj_entry.get('subject', ''):
                            sid = s['id']
                            break
                if sid is None:
                    continue
                # Найти классы для этого предмета у учителя
                # (упрощение: считаем что учитель ведёт предмет во всех классах
                #  пропорционально нагрузке)
                if sid not in load_map[t['id']]:
                    load_map[t['id']][sid] = {}

        # Для простоты прототипа: используем teacher_load таблицу
        load_map = {}
        for t in teachers:
            full_load = self.db.get_full_load(t['id'])
            load_map[t['id']] = {}
            for fl in full_load:
                sid = fl['subject_id']
                cid = fl['class_id']
                hours = fl['hours_per_week']
                if sid not in load_map[t['id']]:
                    load_map[t['id']][sid] = {}
                load_map[t['id']][sid][cid] = hours

        # Построить модель
        self._build_model(teachers, subjects, classes, rooms, load_map)

        # Решить
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.max_time_seconds
        solver.parameters.num_workers = self.config.num_workers
        solver.parameters.log_search_progress = True

        if self.config.optimize_soft:
            solver.parameters.cp_model_presolve = True

        status = solver.Solve(self.model)

        if status == cp_model.OPTIMAL:
            result_status = "optimal"
        elif status == cp_model.FEASIBLE:
            result_status = "feasible"
        else:
            return {
                "status": "infeasible",
                "message": "Не удалось найти решение. "
                           "Проверьте ограничения и данные.",
                "stats": {}
            }

        # Извлечь решение
        lessons = self._extract_solution(solver, teachers, subjects,
                                          classes, rooms)

        stats = {
            "total_lessons": len(lessons),
            "total_teacher_hours": sum(
                t['total_hours'] for t in teachers
            ),
            "objective_value": solver.ObjectiveValue(),
        }

        return {
            "status": result_status,
            "lessons": lessons,
            "stats": stats
        }

    def _build_model(self, teachers, subjects, classes, rooms, load_map):
        """Построение модели ограничений."""

        DAYS = 5   # Пн-Пт
        MAX_LESSONS = 8

        # Индексы
        teacher_ids = [t['id'] for t in teachers]
        subject_ids = [s['id'] for s in subjects]
        class_ids = [c['id'] for c in classes]
        room_ids = [r['id'] for r in rooms]

        teacher_map = {t['id']: t for t in teachers}
        subject_map = {s['id']: s for s in subjects}
        class_map = {c['id']: c for c in classes}
        room_map = {r['id']: r for r in rooms}

        # ===== ПЕРЕМЕННЫЕ =====
        # x[t, c, d, l] = subject_id (или 0 если нет урока)
        # room[t, c, d, l] = room_id
        # Для упрощения: создаём бинарные переменные
        # lesson_exists[t, c, s, d, l] = 1 если учитель t ведёт предмет s
        #                                  в классе c в день d на уроке l

        # Упрощённый подход: для каждого (class, day, lesson) определяем
        # (teacher, subject, room)

        # Переменные: для каждого слота (class, day, lesson)
        # назначаем teacher и subject и room

        # Создаём пул возможных назначений
        # valid_assignments[c, d, l] = список (teacher_id, subject_id, room_id)

        # Для прототипа используем более простой подход:
        # Создаём переменные teacher_var[c, d, l] и subject_var[c, d, l]

        self.vars['teacher'] = {}
        self.vars['subject'] = {}
        self.vars['room'] = {}

        # Допустимые значения
        for c in class_ids:
            cls = class_map[c]
            max_lessons = cls.get('max_lessons_day', 7)
            if cls.get('op_type') == 'primary' or int(cls['name'][0]) <= 4:
                max_lessons = min(max_lessons, 4)

            for d in range(1, DAYS + 1):
                for l in range(1, MAX_LESSONS + 1):
                    key = (c, d, l)

                    # Переменная учителя (0 = нет урока)
                    t_var = self.model.NewIntVar(0, max(teacher_ids),
                                                  f"t_{c}_{d}_{l}")
                    # Переменная предмета (0 = нет урока)
                    s_var = self.model.NewIntVar(0, max(subject_ids),
                                                  f"s_{c}_{d}_{l}")
                    # Переменная кабинета (0 = нет урока)
                    r_var = self.model.NewIntVar(0, max(room_ids),
                                                  f"r_{c}_{d}_{l}")

                    self.vars['teacher'][key] = t_var
                    self.vars['subject'][key] = s_var
                    self.vars['room'][key] = r_var

        # ===== ОГРАНИЧЕНИЯ =====

        # 1. Если нет учителя — нет предмета и кабинета (и наоборот)
        for c in class_ids:
            for d in range(1, DAYS + 1):
                for l in range(1, MAX_LESSONS + 1):
                    key = (c, d, l)
                    t = self.vars['teacher'][key]
                    s = self.vars['subject'][key]
                    r = self.vars['room'][key]

                    # t=0 <=> s=0 <=> r=0
                    # Используем реификацию
                    t_is_zero = self.model.NewBoolVar(f"tz_{c}_{d}_{l}")
                    self.model.Add(t == 0).OnlyEnforceIf(t_is_zero)
                    self.model.Add(t > 0).OnlyEnforceIf(t_is_zero.Not())

                    s_is_zero = self.model.NewBoolVar(f"sz_{c}_{d}_{l}")
                    self.model.Add(s == 0).OnlyEnforceIf(s_is_zero)
                    self.model.Add(s > 0).OnlyEnforceIf(s_is_zero.Not())

                    r_is_zero = self.model.NewBoolVar(f"rz_{c}_{d}_{l}")
                    self.model.Add(r == 0).OnlyEnforceIf(r_is_zero)
                    self.model.Add(r > 0).OnlyEnforceIf(r_is_zero.Not())

                    self.model.Add(t_is_zero == s_is_zero)
                    self.model.Add(t_is_zero == r_is_zero)

        # 2. Один класс — один урок в слот (автоматически, т.к. одна переменная)

        # 3. Один учитель не может быть в двух классах одновременно
        for t_id in teacher_ids:
            for d in range(1, DAYS + 1):
                for l in range(1, MAX_LESSONS + 1):
                    # Сумма индикаторов "учитель t занят в слот (d,l)" <= 1
                    indicators = []
                    for c in class_ids:
                        key = (c, d, l)
                        t_var = self.vars['teacher'][key]
                        is_t = self.model.NewBoolVar(f"ist_{t_id}_{c}_{d}_{l}")
                        self.model.Add(t_var == t_id).OnlyEnforceIf(is_t)
                        self.model.Add(t_var != t_id).OnlyEnforceIf(is_t.Not())
                        indicators.append(is_t)
                    self.model.Add(sum(indicators) <= 1)

        # 4. Один кабинет не может быть занят дважды
        for r_id in room_ids:
            for d in range(1, DAYS + 1):
                for l in range(1, MAX_LESSONS + 1):
                    indicators = []
                    for c in class_ids:
                        key = (c, d, l)
                        r_var = self.vars['room'][key]
                        is_r = self.model.NewBoolVar(f"isr_{r_id}_{c}_{d}_{l}")
                        self.model.Add(r_var == r_id).OnlyEnforceIf(is_r)
                        self.model.Add(r_var != r_id).OnlyEnforceIf(is_r.Not())
                        indicators.append(is_r)
                    self.model.Add(sum(indicators) <= 1)

        # 5. Нагрузка учителя = сумме часов по нагрузке
        for t_id in teacher_ids:
            if t_id not in load_map:
                continue
            for s_id, class_hours in load_map[t_id].items():
                total_hours = sum(class_hours.values())
                # Подсчитать сколько раз учитель t ведёт предмет s во всех классах
                indicators = []
                for c_id in class_ids:
                    if c_id not in class_hours:
                        continue
                    hours_for_class = class_hours[c_id]
                    for d in range(1, DAYS + 1):
                        for l in range(1, MAX_LESSONS + 1):
                            key = (c_id, d, l)
                            t_var = self.vars['teacher'][key]
                            s_var = self.vars['subject'][key]
                            is_ts = self.model.NewBoolVar(
                                f"ists_{t_id}_{s_id}_{c_id}_{d}_{l}"
                            )
                            self.model.Add(t_var == t_id).OnlyEnforceIf(is_ts)
                            self.model.Add(t_var != t_id).OnlyEnforceIf(
                                is_ts.Not()
                            )
                            # Также предмет должен совпадать
                            is_s = self.model.NewBoolVar(
                                f"iss_{t_id}_{s_id}_{c_id}_{d}_{l}"
                            )
                            self.model.Add(s_var == s_id).OnlyEnforceIf(is_s)
                            self.model.Add(s_var != s_id).OnlyEnforceIf(
                                is_s.Not()
                            )
                            is_both = self.model.NewBoolVar(
                                f"isb_{t_id}_{s_id}_{c_id}_{d}_{l}"
                            )
                            self.model.AddBoolAnd([is_ts, is_s]).OnlyEnforceIf(
                                is_both
                            )
                            self.model.AddBoolOr([is_ts.Not(), is_s.Not()
                                                  ]).OnlyEnforceIf(
                                is_both.Not()
                            )
                            indicators.append(is_both)
                self.model.Add(sum(indicators) == total_hours)

        # 6. Предмет только в подходящем кабинете
        for s_id in subject_ids:
            subj = subject_map[s_id]
            allowed_types = json.loads(subj.get('room_types', '["universal"]'))
            allowed_rooms = [
                r['id'] for r in rooms
                if r['room_type'] in allowed_types or 'universal' in allowed_types
            ]
            if not allowed_rooms:
                allowed_rooms = room_ids  # fallback

            for c in class_ids:
                for d in range(1, DAYS + 1):
                    for l in range(1, MAX_LESSONS + 1):
                        key = (c, d, l)
                        s_var = self.vars['subject'][key]
                        r_var = self.vars['room'][key]

                        is_s = self.model.NewBoolVar(
                            f"chk_s_{s_id}_{c}_{d}_{l}"
                        )
                        self.model.Add(s_var == s_id).OnlyEnforceIf(is_s)
                        self.model.Add(s_var != s_id).OnlyEnforceIf(is_s.Not())

                        # Если предмет s_id, то кабинет должен быть из allowed
                        for r_id in room_ids:
                            if r_id not in allowed_rooms:
                                is_r = self.model.NewBoolVar(
                                    f"chk_r_{r_id}_{c}_{d}_{l}"
                                )
                                self.model.Add(r_var == r_id).OnlyEnforceIf(
                                    is_r
                                )
                                self.model.Add(r_var != r_id).OnlyEnforceIf(
                                    is_r.Not()
                                )
                                # is_s и is_r не могут быть оба 1
                                self.model.AddBoolOr([is_s.Not(), is_r.Not()])

        # 7. Ограничения учителей (no_first_lesson)
        for t in teachers:
            if t.get('no_first_lesson'):
                t_id = t['id']
                for c in class_ids:
                    for d in range(1, DAYS + 1):
                        key = (c, d, 1)
                        t_var = self.vars['teacher'][key]
                        is_t = self.model.NewBoolVar(
                            f"nf_{t_id}_{c}_{d}"
                        )
                        self.model.Add(t_var == t_id).OnlyEnforceIf(is_t)
                        self.model.Add(t_var != t_id).OnlyEnforceIf(is_t.Not())
                        self.model.Add(is_t == 0)

        # 8. Макс. уроков в день для класса
        for c in class_ids:
            cls = class_map[c]
            max_per_day = cls.get('max_lessons_day', 7)
            if int(cls['name'][0]) <= 4:
                max_per_day = min(max_per_day, 4)

            for d in range(1, DAYS + 1):
                indicators = []
                for l in range(1, MAX_LESSONS + 1):
                    key = (c, d, l)
                    t_var = self.vars['teacher'][key]
                    is_lesson = self.model.NewBoolVar(
                        f"il_{c}_{d}_{l}"
                    )
                    self.model.Add(t_var > 0).OnlyEnforceIf(is_lesson)
                    self.model.Add(t_var == 0).OnlyEnforceIf(is_lesson.Not())
                    indicators.append(is_lesson)
                self.model.Add(sum(indicators) <= max_per_day)

        # ===== МЯГКИЕ ОГРАНИЧЕНИЯ (оптимизация) =====
        if self.config.optimize_soft:
            # Минимизировать окна у учителей
            # (упрощённо: штраф за разрыв между первым и последним уроком)

            # Равномерное распределение: не более 2 сложных предметов подряд
            # (это сложное ограничение, для прототипа опустим)

            pass

        # Сохранить маппинги для извлечения решения
        self._meta = {
            'teachers': teacher_map,
            'subjects': subject_map,
            'classes': class_map,
            'rooms': room_map,
            'teacher_ids': teacher_ids,
            'subject_ids': subject_ids,
            'class_ids': class_ids,
            'room_ids': room_ids,
            'days': DAYS,
            'max_lessons': MAX_LESSONS,
        }

    def _extract_solution(self, solver, teachers, subjects, classes,
                           rooms) -> List[Dict]:
        """Извлечение решения из солвера."""
        lessons = []
        meta = self._meta
        class_map = meta['classes']
        subject_map = meta['subjects']
        teacher_map = meta['teachers']
        room_map = meta['rooms']

        for c in meta['class_ids']:
            cls = class_map[c]
            max_lessons = cls.get('max_lessons_day', 7)
            if int(cls['name'][0]) <= 4:
                max_lessons = min(max_lessons, 4)

            for d in range(1, meta['days'] + 1):
                for l in range(1, meta['max_lessons'] + 1):
                    key = (c, d, l)
                    t_val = solver.Value(self.vars['teacher'][key])
                    s_val = solver.Value(self.vars['subject'][key])
                    r_val = solver.Value(self.vars['room'][key])

                    if t_val > 0 and s_val > 0 and r_val > 0:
                        lessons.append({
                            'class_id': c,
                            'class_name': cls['name'],
                            'subject_id': s_val,
                            'subject_name': subject_map[s_val]['name'],
                            'teacher_id': t_val,
                            'teacher_name': teacher_map[t_val]['fio'],
                            'room_id': r_val,
                            'room_number': room_map[r_val]['number'],
                            'day': d,
                            'lesson': l,
                            'is_group': 0,
                            'group_label': '',
                            'week_type': 0,
                            'is_temporary': 0,
                            'original_teacher_id': 0,
                        })

        return lessons
