# АСКК «Татнефть-Добыча» — прототип

Автоматизированная система контроля качества работ подрядчиков.
Переход от визуального/бумажного контроля к цифровой модели с объективным
подтверждением (геолокация, фото, чек-листы, данные АСУ ТП).

## Команда

Прототип подготовлен в рамках программы «ЮФУ.Про Исследования» командой из 5 человек:

| Имя | Роль | Зона ответственности |
|-----|------|---------------------|
| **Опик М.Ю.** | Backend · ML | API (FastAPI / PostgreSQL), rule engine, CV-инференс и обучение моделей дефектов |
| **Алейников Н.В.** | Frontend · ML | Дашборд менеджера и мобильное приложение подрядчика, UI для CV-демо |
| **Рязанцев К.А.** | Fullstack | Склейка фронт ↔ бэк, REST-контракты, выкатка, девопс |
| **Соловьев Д.С.** | Аналитика | Бизнес-требования, формализация правил авто-проверки, сценарии E2E |
| **Швецова А.И.** | UX/UI дизайн | Дизайн-система «АСКК», фирменный стиль и состояния интерфейса |

Демо-стенд поднят на оборудовании ЮФУ. Данные синтетические; интеграция
с реальной АСУ ТП не подключена (см. `app/integrations/asutp/base.py`
— задел под OPC-UA / REST).

## Стек

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2
- **БД**: PostgreSQL + TimescaleDB (схема создаётся через `create_all` при старте — без Alembic)
- **Хранилище фото**: MinIO (S3-совместимое)
- **Кэш/очереди**: Redis
- **CV-сервис**: Python 3.11, FastAPI, Ultralytics YOLOv8 (3 класса дефектов)
- **Тесты**: pytest, pytest-asyncio
- **CI**: GitHub Actions (`.github/workflows/backend-ci.yml`)
- **Деплой**: Docker, docker-compose

## Структура

```
askk-prototype/
├── backend/
│   ├── app/
│   │   ├── core/         # config, security, logging
│   │   ├── db/           # Base, session, types (JSONBCompat)
│   │   ├── models/       # SQLAlchemy ORM
│   │   ├── schemas/      # Pydantic
│   │   ├── api/v1/       # FastAPI роутеры
│   │   ├── services/     # auth, rules, geo, rating, audit, cv_client
│   │   ├── integrations/asutp/  # интерфейс АСУ ТП (без реализации)
│   │   ├── mocks/        # seed-данные для демо
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── cv-service/
│   ├── app/
│   │   ├── config.py
│   │   ├── factory.py
│   │   ├── main.py
│   │   └── detectors/
│   │       ├── base.py        # BaseDetector, Detection
│   │       ├── yolo.py        # общий YOLO-инференс
│   │       └── defect.py      # YOLOv8 на 3 классах дефектов
│   ├── weights/
│   │   └── defect.pt          # обученная модель (5.96 MB, едет в образ)
│   ├── tests/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── docs/
│   ├── analogs.md       # отраслевые аналоги
│   └── data-model.md    # ER-диаграмма
├── scripts/             # E2E demo + ручные сценарии
│   ├── demo.py
│   ├── inspect_api.py
│   ├── inspect_api.ps1
│   ├── test_anomaly_flow.py
│   ├── test_contractor_flow.py
│   ├── test_photo_upload.py
│   ├── test_photo_upload_v2.py
│   ├── test_review_flow.py
│   └── test_web_form.py
├── .github/workflows/backend-ci.yml
├── docker-compose.yml   # api, cv, postgres+timescale, minio, redis
├── Makefile             # make help — список целей
├── make.ps1             # Windows shim
└── README.md
```

## Быстрый старт

### 1) Поднять инфру

```bash
docker compose up -d
```

Поднимутся: `postgres+timescale`, `minio`, `minio-bucket-init`, `redis`, `api`, `cv`.

### 2) Установить зависимости и засеять БД

```bash
cd backend
cp .env.example .env
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate
pip install -e ".[dev]"

# Схема создастся автоматически при старте (Base.metadata.create_all в lifespan).
# Остаётся засеять демо-данные:
python -m app.mocks.generators.seed
```

Создаст: 6 подрядчиков, 5 кустов со скважинами, 4 пользователя
(`admin`, `manager`, `tech`, `master`) + 6 учёток подрядчиков,
29 нарядов, 4 акта, телеметрия за 3 дня с инъекцией аномалий
(47 аномалий АСУ ТП для дашборда).

### 3) Запустить API

```bash
uvicorn app.main:app --reload
```

OpenAPI: <http://localhost:8000/docs>

### 4) Войти

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@tatneft.ru", "password": "password"}'
```

Тестовые учётки (пароль у всех `password`):

| Роль | Email |
|------|-------|
| admin | admin@tatneft.ru |
| manager | manager@tatneft.ru |
| technologist | tech@tatneft.ru |
| master | master@tatneft.ru |
| contractor | contractor\_\<inn\>@example.ru |

### 5) Демо-скрипт (E2E)

```bash
python scripts/demo.py
```

Симулирует полный цикл: создание наряда → заполнение чек-листа подрядчиком →
submit → авто-проверка (Rule Engine) → ручная верификация мастером.
Печатает статусы наряда/акта на каждом шаге, в т.ч. итоговый `auto_check_score`
и финальный статус.

### 6) Дашборд

Read-only UI на vanilla JS. После того, как API поднят и засеян:

```bash
python -m http.server 5500 --bind 127.0.0.1 --directory frontend
```

Открыть в браузере: <http://127.0.0.1:5500/>

Логин: `admin@tatneft.ru` / `password` (или `manager`, `tech`, `master`, `contractor_*`).

Дашборд показывает: KPI сводку, последние наряды, рейтинг подрядчиков,
распределение актов по статусам.

## Команды разработки (Makefile)

Все рутинные команды собраны в `Makefile` (GNU make) и продублированы в
`make.ps1` для Windows PowerShell.

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
| `make seed` | Заполнить БД демо-данными (через `python -m app.mocks.generators.seed`) |
| `make seed-clean` | Очистить и пересоздать демо-данные |
| `make docker-up` | `docker compose up -d` |
| `make docker-down` | `docker compose down` |
| `make docker-logs` | Логи API |
| `make docker-logs-cv` | Логи CV-сервиса |
| `make db-shell` | `psql` в контейнере postgres |
| `make cv-dev` | CV-сервис локально (uvicorn, без docker) |
| `make cv-test` | Тесты CV-сервиса (помеченные `@needs_torch`/`@needs_weights` skip-ятся) |
| `make cv-lint` | ruff + mypy для CV-сервиса |
| `make cv-install` | Создать `cv-service/.venv` + поставить deps |
| `make clean` | Удалить `__pycache__`, `build`, `dist`, `.egg-info` |

Windows без GNU make:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1 test
powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1 ci
```

## CV-сервис (YOLOv8, детекция дефектов)

Отдельный FastAPI-микросервис для детекции дефектов оборудования
(YOLOv8, обученная на 3 классах). Запускается как сервис `cv` в
`docker-compose` (CPU-only torch).

### Контракт

| Метод | URL | Назначение |
|-------|-----|------------|
| `GET`  | `/health`   | Liveness (всегда 200, если процесс жив) |
| `GET`  | `/readyz`   | Readiness (200 только после `warmup`) |
| `GET`  | `/detectors` | Имя активного детектора и список поддерживаемых |
| `POST` | `/infer`    | `multipart file=...` → `{detector, count, latency_ms, image_size, detections[]}` |

`Detection` (для дефектов):

```json
{
  "label": "corrosion",
  "confidence": 0.97,
  "bbox": {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100},
  "detector": "defect-yolov8",
  "meta": {"class_id": 0, "expected_label": "corrosion", "severity": 1}
}
```

### Классы дефектов

| ID | Имя | Severity | Описание |
|----|-----|----------|----------|
| 0 | corrosion | 1 | Рыжие пятна окисления |
| 1 | leak      | 2 | Капли / потёки |
| 2 | damage    | 3 | Механические повреждения |

`severity` прокидывается в `Detection.meta.severity` и используется в
backend (`auto_check_act`) для приоритизации ремонта.

### Запуск

```bash
# 1) Поднять весь стек
make docker-up

# 2) Логи CV-сервиса (первый старт: warmup YOLO на weights/defect.pt)
make docker-logs-cv

# 3) Проверка
curl http://localhost:8001/health
curl http://localhost:8001/readyz

# 4) Инференс
curl -X POST http://localhost:8001/infer \
     -F "file=@/path/to/photo.jpg"
```

### Локальная разработка (без docker)

```bash
make cv-install         # ~3 мин: venv + deps (включая torch CPU)
make cv-dev             # uvicorn --reload на порту 8000
make cv-test            # тесты (skip тех, что требуют torch/weights)
make cv-lint            # ruff + mypy
```

### Backend-интеграция

`backend/app/services/cv_client.py` — httpx-клиент. Вызывается из
`auto_check_act` (см. `app/services/rules.py:_run_cv_check`):

- Если `CV_ENABLED=true` и у акта есть фото — каждое прогоняется через `/infer`.
- Результаты (счётчик детекций, лейблы, severity) попадают в
  `auto_check_details["cv"]`.
- Если CV-сервис недоступен (`CVUnavailableError`) — автопроверка
  продолжается без CV-шага (graceful degradation, не валит акт).
- Прокси в backend: `backend/app/api/v1/cv.py` (`/api/v1/cv/infer`,
  `/api/v1/cv/detectors`) — чтобы UI не ходил в CV напрямую.

Переменные backend:

- `CV_SERVICE_URL` (default `http://cv:8000`)
- `CV_TIMEOUT_S` (default `30.0`)
- `CV_ENABLED` (default `true`)

### Веса модели

`cv-service/weights/defect.pt` (5.96 MB) — обученная модель, едет в
Docker-образ (`COPY weights ./weights` в `cv-service/Dockerfile`).
Модель не переобучается в рантайме прототипа — для демо достаточно
зафиксированного качества (mAP50 ≈ 0,91 на синтетике).

## Ключевые эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| `POST` | `/api/v1/auth/login` | Логин |
| `GET`  | `/api/v1/auth/me` | Текущий пользователь |
| `POST` | `/api/v1/auth/seed` | Заполнить БД демо-данными (dev) |
| `GET`  | `/api/v1/contractors/` | Список подрядчиков |
| `GET`  | `/api/v1/objects/?kind=well` | Скважины |
| `GET`  | `/api/v1/objects/{id}/equipment` | Оборудование объекта |
| `GET`  | `/api/v1/works/types` | Типы работ |
| `GET`  | `/api/v1/works/types/{id}/template` | Чек-лист типа работ |
| `GET/POST/PATCH` | `/api/v1/orders/` | Наряды-заказы |
| `GET/POST` | `/api/v1/acts/` | Акты |
| `POST` | `/api/v1/acts/{id}/submit` | Подписать акт (запустит auto-check) |
| `POST` | `/api/v1/acts/{id}/review` | Ручное подтверждение/отклонение |
| `GET`  | `/api/v1/telemetry/equipment/{id}/history` | История телеметрии (из БД) |
| `GET`  | `/api/v1/dashboard/summary` | Сводка для главной |
| `GET`  | `/api/v1/dashboard/contractors/ranking` | Рейтинг подрядчиков |
| `GET`  | `/api/v1/cv/detectors` | Список детекторов CV |
| `POST` | `/api/v1/cv/infer` | Детекция дефектов (прокси к CV-сервису) |
| `GET`  | `:8001/health` | Liveness CV-сервиса (YOLOv8) |
| `GET`  | `:8001/readyz` | Readiness CV-сервиса |
| `POST` | `:8001/infer` | Детекция дефектов (напрямую) |

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
   - запускает Rule Engine: чек-лист + гео + фото (через CV-прокси) + телеметрия
   - если score >= 0.8 → AUTO_CONFIRMED
   - иначе → DELAYED_VERIFICATION (ручная проверка через 30 дней)

5. Мастер/технолог видит результат в дашборде
   - авто-подтверждённые — закрыты
   - спорные — отправлены на ручной review
   POST /api/v1/acts/{id}/review
```

## Структура БД

Схема создаётся при старте backend через `Base.metadata.create_all` —
без Alembic. ER-диаграмма и описание таблиц: `docs/data-model.md`.

Production-миграции потребуют отдельного пайплайна (Alembic / DDL-скрипты
в CI) — для прототипа это избыточно.

## Следующие шаги

1. [ ] Перевести frontend на отдельный сервис (Next.js / Vite+React)
2. [ ] Мобильное PWA-приложение подрядчика (offline + камера + гео)
3. [ ] Подключить реальный CV-детектор (дообучение на реальных фото)
4. [ ] ML-модель отложенной верификации (аномалии в динамике)
5. [ ] Формула рейтинга с калибровкой весов
6. [ ] Подключить реальную АСУ ТП через OPC-UA (см. `app/integrations/asutp/base.py`)
