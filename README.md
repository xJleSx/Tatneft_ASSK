# АСКК «Татнефть-Добыча» — прототип

Автоматизированная система контроля качества работ подрядчиков.
Переход от визуального/бумажного контроля к цифровой модели с объективным
подтверждением (геолокация, фото, чек-листы, данные АСУ ТП).

> ⚠️ **Доступа к реальным актам и АСУ ТП пока нет** — прототип построен на
> синтетических данных на основе отраслевых аналогов (РД 153-112-017/02-97,
> 1С:ТОИР, SAP PM, IFS). См. [docs/analogs.md](docs/analogs.md) — откуда
> взяты предположения и что нужно уточнить у заказчика.

## Стек

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic
- **БД**: PostgreSQL + TimescaleDB (для телеметрии)
- **Хранилище фото**: MinIO (S3-совместимое)
- **Кэш/очереди**: Redis
- **Тесты**: pytest, pytest-asyncio
- **Деплой**: Docker, docker-compose

## Структура

```
askk-prototype/
├── backend/
│   ├── app/
│   │   ├── core/        # config, security, logging
│   │   ├── db/          # Base, session
│   │   ├── models/      # SQLAlchemy ORM
│   │   ├── schemas/     # Pydantic
│   │   ├── api/v1/      # FastAPI роутеры
│   │   ├── services/    # бизнес-логика (auth, rules, geo, rating)
│   │   ├── integrations/asutp/  # мок + стаб OPC-UA
│   │   ├── mocks/       # генераторы синтетики
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── docs/
│   ├── analogs.md       # откуда взяты предположения
│   └── data-model.md    # ER-диаграмма
├── docker-compose.yml
└── README.md
```

## Быстрый старт

### 1) Поднять инфру
```bash
docker-compose up -d
```
Поднимутся: postgres+timescale, minio, minio-bucket-init, redis.

### 2) Установить зависимости и мигрировать БД
```bash
cd backend
cp .env.example .env
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate
pip install -e ".[dev]"

# Сгенерировать первую миграцию (autogenerate подхватит все модели):
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

### 3) Засеять синтетикой
```bash
curl -X POST http://localhost:8000/api/v1/auth/seed
```
Создаст: 6 подрядчиков, 4 типовых вида работ с чек-листами, 5 кустов с 15-25
скважинами, 4 пользователя (admin/manager/tech/master) + 6 учёток подрядчиков.

### 4) Запустить API
```bash
uvicorn app.main:app --reload
```
OpenAPI: http://localhost:8000/docs

### 5) Войти
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@tatneft.local", "password": "password"}'
```

Тестовые учётки (пароль у всех `password`):

| Роль | Email |
|------|-------|
| admin | admin@tatneft.ru |
| manager | manager@tatneft.ru |
| technologist | tech@tatneft.ru |
| master | master@tatneft.ru |
| contractor | contractor_{inn}@example.ru |

### 6) Демо-скрипт (E2E)

Симулирует полный цикл: создание наряда → заполнение чек-листа подрядчиком →
submit → авто-проверка (Rule Engine) → ручная верификация мастером.

```bash
python scripts/demo.py
```

Скрипт печатает статусы наряда/акта на каждом шаге, в т.ч. итоговый `auto_check_score`
и финальный статус.

### 7) Дашборд

Read-only UI на vanilla JS. После того, как API поднят и засеян:

```bash
python -m http.server 5500 --bind 127.0.0.1 --directory frontend
```

Открыть в браузере: http://127.0.0.1:5500/

Логин: `admin@tatneft.ru` / `password` (или `manager`, `tech`, `master`, `contractor_*`).

Дашборд показывает: KPI сводку, последние наряды, рейтинг подрядчиков,
распределение актов по статусам.

## Команды разработки (Makefile)

Все рутинные команды собраны в `Makefile` (GNU make) и продублированы в
`make.ps1` для Windows PowerShell (если GNU make не установлен —
делает прямые вызовы `pytest` / `ruff` / `mypy` / `alembic`).

| Команда | Что делает |
|---------|-----------|
| `make help` | Список всех целей с описанием |
| `make install` | Создать venv, поставить `.[dev]` |
| `make dev` | Запустить API (`uvicorn --reload`) |
| `make test` | Полный прогон тестов (`pytest -v`) |
| `make test-fast` | Быстрый прогон (`pytest -q`) |
| `make test-cov` | Тесты + coverage |
| `make lint` | `ruff check` (только safe) |
| `make lint-fix` | `ruff check --fix` |
| `make fmt` | `black` + `ruff --fix` |
| `make typecheck` | `mypy app` |
| `make ci` | `lint` + `typecheck` + `test-fast` (как в GitHub Actions) |
| `make migrate` | `alembic upgrade head` |
| `make revision msg="..."` | Сгенерировать новую миграцию |
| `make seed` | Заполнить БД демо-данными (через API `/auth/seed`) |
| `make docker-up` | `docker compose up -d` |
| `make docker-logs` | Логи API |
| `make clean` | Удалить `__pycache__`, `build`, `dist`, `.egg-info` |

Windows без GNU make:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1 test
powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1 ci
```

## Ключевые эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| `POST` | `/api/v1/auth/login` | Логин |
| `GET`  | `/api/v1/auth/me` | Текущий пользователь |
| `POST` | `/api/v1/auth/seed` | Заполнить БД синтетикой (dev) |
| `GET`  | `/api/v1/contractors/` | Список подрядчиков |
| `GET`  | `/api/v1/objects/?kind=well` | Скважины |
| `GET`  | `/api/v1/objects/{id}/equipment` | Оборудование объекта |
| `GET`  | `/api/v1/works/types` | Типы работ |
| `GET`  | `/api/v1/works/types/{id}/template` | Чек-лист типа работ |
| `GET/POST/PATCH` | `/api/v1/orders/` | Наряды-заказы |
| `GET/POST` | `/api/v1/acts/` | Акты |
| `POST` | `/api/v1/acts/{id}/submit` | Подписать акт (запустит auto-check) |
| `POST` | `/api/v1/acts/{id}/review` | Ручное подтверждение/отклонение |
| `GET`  | `/api/v1/telemetry/equipment/{id}/snapshot` | Снимок АСУ ТП (мок) |
| `GET`  | `/api/v1/telemetry/equipment/{id}/history?hours=24` | История |
| `GET`  | `/api/v1/dashboard/summary` | Сводка для главной |
| `GET`  | `/api/v1/dashboard/contractors/ranking` | Рейтинг подрядчиков |

## Поток данных (end-to-end сценарий)

```
1. Менеджер создаёт WorkOrder (наряд-заказ) и назначает подрядчика
   POST /api/v1/orders/

2. Подрядчик видит наряд в мобильном/PWA-приложении, выезжает на объект
   GET /api/v1/orders/?contractor_id=...

3. На объекте подрядчик:
   - открывает чек-лист для типа работ
   - фотографирует «до» (гео+EXIF пишутся автоматически)
   - выполняет операции, заполняет пункты
   - фотографирует «после»
   - подписывает акт → submit

4. Backend при submit:
   - сохраняет ответы чек-листа
   - запрашивает снимки телеметрии equipment у АСУ ТП (мок)
   - запускает Rule Engine: чек-лист + гео + фото + телеметрия
   - если score >= 0.8 → AUTO_CONFIRMED
   - иначе → DELAYED_VERIFICATION (ручная проверка через 30 дней)

5. Мастер/технолог видит результат в дашборде
   - авто-подтверждённые — закрыты
   - спорные — отправлены на ручной review
   POST /api/v1/acts/{id}/review
```

## Что нужно уточнить у заказчика

См. [docs/analogs.md](docs/analogs.md#5-что-нужно-уточнить-у-заказчика):

- Каталог работ и нормативы
- Протокол АСУ ТП (OPC-UA / REST / Modbus), песочница
- Юридическая значимость цифрового акта (КЭП?)
- Радиус гео-проверки (75 м по умолчанию)
- Формула рейтинга (W_STEP, W_GEO, W_PHOTO, W_TELEMETRY)
- Срок отложенной верификации (30 дней)
- Регламенты ИБ

## Следующие шаги

1. [ ] Перевести frontend на отдельный сервис (Next.js / Vite+React)
2. [ ] Мобильное PWA-приложение подрядчика (offline + камера + гео)
3. [ ] Реализовать OPC-UA адаптер после получения доступа
4. [ ] Импорт реальных актов (когда откроют доступ)
5. [ ] ML-модель отложенной верификации (аномалии в динамике)
6. [ ] Формула рейтинга с калибровкой весов
