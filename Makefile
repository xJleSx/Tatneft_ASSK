# АСКК «Татнефть-Добыча» — entry points
# Use: `make help` (or `pwsh make.ps1 help`) to list targets
#
# Все команды изолированы в `backend/`. Перед первым запуском:
#   1. cp backend/.env.example backend/.env
#   2. docker compose up -d
#   3. make migrate && make seed
#   4. make dev

.PHONY: help install dev test test-fast test-cov lint fmt typecheck ci \
        migrate revision seed seed-clean docker-up docker-down docker-logs \
        db-shell clean clean-pycache clean-build

# ---------- Meta ----------

help:	## Показать список целей
	@$(MAKE) -p 2>/dev/null | awk 'BEGIN {FS = ":.*##"; printf "Цели:\n"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------- Setup ----------

install:	## Установить зависимости в venv
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -e ".[dev]"

# ---------- Run ----------

dev:	## Запустить API локально (uvicorn с reload)
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ---------- Test ----------

test:	## Все тесты (pytest)
	cd backend && pytest tests/ -v

test-fast:	## Быстрый прогон (без verbose, без warnings)
	cd backend && pytest tests/ -q

test-cov:	## Тесты + coverage
	cd backend && pytest tests/ --cov=app --cov-report=term-missing --cov-report=html

# ---------- Lint / Types ----------

lint:	## ruff check (только safe fixes)
	cd backend && ruff check app tests

lint-fix:	## ruff check --fix
	cd backend && ruff check --fix app tests

fmt:	## black + ruff --fix
	cd backend && black app tests
	cd backend && ruff check --fix app tests

typecheck:	## mypy
	cd backend && mypy app

ci: lint typecheck test-fast	## Полный CI-прогон (как в .github/workflows)

# ---------- DB ----------

migrate:	## Применить миграции Alembic
	cd backend && alembic upgrade head

revision:	## Создать новую миграцию (msg=...)
	cd backend && alembic revision --autogenerate -m "$(msg)"

seed:	## Засеять БД демо-данными
	cd backend && python -m app.mocks.generators.seed

seed-clean:	## Очистить и пересоздать демо-данные
	cd backend && python -c "from app.mocks.generators.seed import clean_db; import asyncio; asyncio.run(clean_db())" && $(MAKE) seed

# ---------- Docker ----------

docker-up:	## Поднять postgres+timescale, minio, redis, api
	docker compose up -d

docker-down:	## Остановить и удалить контейнеры (тома сохраняются)
	docker compose down

docker-logs:	## Логи API
	docker compose logs -f api

db-shell:	## Подключиться к Postgres (psql через docker)
	docker compose exec postgres psql -U askk -d askk

# ---------- Cleanup ----------

clean-pycache:	## Удалить __pycache__ / .pyc
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

clean-build:	## Удалить build/ dist/ .egg-info
	rm -rf backend/build backend/dist backend/*.egg-info
	rm -rf backend/src/*.egg-info

clean: clean-pycache clean-build	## Полная очистка артефактов сборки
