# backend

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL/TimescaleDB + MinIO.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

## Миграции

```bash
# автогенерация (после изменения моделей)
alembic revision --autogenerate -m "..."
# применение
alembic upgrade head
```

При первом запуске добавьте в созданную миграцию вызов TimescaleDB
(вручную или отдельной миграцией):
```sql
SELECT create_hypertable('telemetry_readings', 'observed_at', if_not_exists => TRUE);
```

## Запуск

```bash
uvicorn app.main:app --reload
```

## Тесты

```bash
pytest
```
