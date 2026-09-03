# School_timesheet
 Школьное расписание  в МБОУ СОШ №6 г. Канска

Структура проекта

school_schedule/
requirements.txt
config.py            # Константы и настройки
database.py          # Схема базы данных
models.py            # Бизнес-модели и валидация
solver.py            # Генератор расписания (CP-SAT Solver)
scheduler_app.py     # Основное приложение (CLI + API)
ui.py                # Быстрый запуск веб-интерфейса (FastAPI)
data/school.db       # SQLite БД
