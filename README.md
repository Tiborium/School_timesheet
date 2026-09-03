# School_timesheet
 Школьное расписание  в МБОУ СОШ №6 г. Канска

Структура проекта

school_schedule/
── requirements.txt
├── config.py
├── database.py          # Схема БД и подключение
├── models.py            # Бизнес-модели и валидация
├── solver.py            # Генератор расписания (OR-Tools)
├── scheduler_app.py     # Основное приложение (CLI + API)
├── ui.py                # Консольный интерфейс
└── data/
    └── school.db        # SQLite БД
