# АСКК «Татнефть-Добыча» — прототип

Автоматизированная система контроля качества работ подрядчиков.
Переход от визуального/бумажного контроля к цифровой модели с объективным
подтверждением (геолокация, фото, чек-листы, данные АСУ ТП).

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
│   │   ├── db/          # Base, session, types (JSONBCompat)
│   │   ├── models/      # SQLAlchemy ORM
│   │   ├── schemas/     # Pydantic
│   │   ├── api/v1/      # FastAPI роутеры
│   │   ├── services/    # бизнес-логика (auth, rules, geo, rating, audit, cv_client)
│   │   ├── integrations/asutp/  # мок + стаб OPC-UA
│   │   ├── mocks/       # генераторы синтетики
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── cv-service/          # CV-микросервис (YOLOv8) — MVP/спайк
│   ├── app/
│   │   ├── config.py
│   │   ├── factory.py
│   │   ├── main.py
│   │   └── detectors/
│   │       ├── base.py        # BaseDetector, Detection
│   │       ├── coco.py        # YOLOv8n pretrained (placeholder)
│   │       ├── defect.py      # заглушка под обученную модель
│   │       └── mock.py        # для тестов (без torch)
│   ├── tests/                 # 11 тестов на MockDetector
│   ├── pyproject.toml
│   ├── Dockerfile             # multi-stage, CPU-only torch
│   └── .env.example
├── docs/
│   ├── analogs.md       # отраслевые аналоги
│   └── data-model.md    # ER-диаграмма
├── docker-compose.yml   # + сервис `cv`
├── Makefile             # + цели cv-dev / cv-test / cv-lint
├── make.ps1
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
| `make cv-dev` | CV-сервис локально (uvicorn, без docker) |
| `make cv-test` | Тесты CV-сервиса на MockDetector (без torch) |
| `make cv-lint` | ruff + mypy для CV-сервиса |
| `make cv-install` | Создать `cv-service/.venv` + поставить deps (без torch) |
| `make cv-install-full` | + ultralytics + torch CPU |
| `make cv-synth-data` | Сгенерить синтетический датасет (400 train + 100 val) |
| `make cv-train` | Дообучить YOLOv8n на синтетике (~50 мин/30 эпох на CPU) |
| `make cv-train-quick` | 5 эпох для smoke-проверки (~8 мин) |
| `make cv-eval` | Валидация обученной модели (mAP50/95) |
| `make cv-defect-smoke` | Smoke-тесты DefectDetector на val-выборке |
| `make synth-demo` | Демо: синтетика → YOLOv8 (in-process) |
| `make clean` | Удалить `__pycache__`, `build`, `dist`, `.egg-info` |

Windows без GNU make:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1 test
powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1 ci
```

## CV-сервис (YOLOv8, MVP/спайк)

Отдельный FastAPI-микросервис для детекции объектов и (в перспективе) дефектов
оборудования. Запускается как сервис `cv` в `docker-compose` (CPU-only torch).

### Контракт

| Метод | URL | Назначение |
|-------|-----|------------|
| `GET`  | `/health`   | Liveness (всегда 200, если процесс жив) |
| `GET`  | `/readyz`   | Readiness (200 только после `warmup`) |
| `GET`  | `/detectors` | Имя активного детектора и список поддерживаемых |
| `POST` | `/infer`    | `multipart file=...` → `{detector, count, latency_ms, image_size, detections[]}` |

`Detection`:
```json
{
  "label": "person",
  "confidence": 0.91,
  "bbox": {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100},
  "detector": "yolov8-coco",
  "meta": {"coco_class_id": 0}
}
```

### Детекторы

| `DETECTOR=` | Что делает | Когда использовать |
|-------------|-----------|-------------------|
| `coco` (default) | YOLOv8n pretrained на COCO (80 классов: person, car, fire_hydrant…) | MVP / placeholder. Умеет находить людей, технику общего вида. |
| `defect` | Заглушка: возвращает `[]` + лог «model not trained» | Пока нет обученной модели дефектов (коррозия, утечки). |
| `mock` | Фиксированные боксы, **без torch** | Только локальные тесты. |

### Запуск

```bash
# 1) Поднять весь стек
make docker-up

# 2) Логи CV-сервиса (первый старт: скачивание yolov8n.pt + warmup)
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
make cv-install         # ~30с: venv + deps БЕЗ torch
make cv-install-full    # + ultralytics + torch CPU (~250 MB, ~2-3 мин)
make cv-dev             # uvicorn --reload на порту 8000
make cv-test            # 11 тестов на MockDetector (0.2с, без torch)
make cv-smoke           # 3 smoke-теста с реальным YOLO (нужен cv-install-full)
make cv-lint            # ruff + mypy
```

### Демо на синтетике (что уже работает сейчас)

`make synth-demo` (после `cv-install-full`) генерирует 6 сцен и прогоняет
через YOLOv8:

| Сцена | Что на ней | YOLOv8 (COCO) находит |
|-------|-----------|----------------------|
| `person` | Стик-человечек на градиенте неба | `[]` — слишком стилизованно |
| `car` | Красный прямоугольник + колёса | `[]` — не похоже на фото |
| `fire_hydrant` | Красный цилиндр + шапка | `[]` — YOLO не учил «гидранты из геометрии» |
| `multi` | 2 человечка + машина | `[]` |
| `noise` | RGB-шум | `[]` (и не должен) |
| `real_photo` | **Реальное фото с Pexels (CC0)** | **`[person]`** с conf ~0.7-0.9, latency ~70мс ✓ |

YOLOv8 обучен на фото из COCO, поэтому стилизованные рисунки не
детектируются — это ожидаемо. **`real_photo` подтверждает, что pipeline
end-to-end работает**: веса скачиваются, warmup, инференс, формат
ответа, latency — всё ок.

Чтобы получить **детекцию дефектов оборудования**, нужна обученная
модель на реальных данных (см. ниже).

### Загрузка реального фото для smoke-теста

```bash
cd cv-service
python scripts/fetch_sample_image.py   # один раз: ~40KB Pexels JPEG
```

### Backend-интеграция

`backend/app/services/cv_client.py` — httpx-клиент. Вызывается из
`auto_check_act` (см. `app/services/rules.py:_run_cv_check`):
- Если `CV_ENABLED=true` и у акта есть фото — каждое прогоняется через `/infer`.
- Результаты (счётчик детекций, лейблы) попадают в `auto_check_details["cv"]`.
- Если CV-сервис недоступен (`CVUnavailableError`) — автопроверка
  продолжается без CV-шага (graceful degradation, не валит акт).
- Конкретные правила («нет дефектов на after-фото», «обнаружена каска»)
  добавим, когда появится обученная модель.

Переменные backend:
- `CV_SERVICE_URL` (default `http://cv:8000`)
- `CV_TIMEOUT_S` (default `30.0`)
- `CV_ENABLED` (default `true`)

### Обучение на синтетике (текущий MVP)

Синтетика — это стартовая точка: показываем, что пайплайн «генерация
датасета → обучение → инференс через HTTP» работает end-to-end, без
необходимости собирать и размечать реальные фото.

```bash
# 1) Сгенерить датасет (numpy-генератор, ~15 сек на 500 картинок)
make cv-synth-data

# 2) Обучить YOLOv8n (CPU, 30 эпох ≈ 50 мин; 5 эпох ≈ 8 мин для smoke)
make cv-train-quick           # 5 эпох
make cv-train                 # 30 эпох (дефолт)

# 3) Оценить на val (mAP50/mAP50-95 по классам)
make cv-eval

# 4) Запустить CV-сервис с обученной моделью
DETECTOR=defect make cv-dev
curl -sS -X POST -F "file=@cv-service/dataset/images/val/val_0000.jpg" \
    http://127.0.0.1:8000/infer | jq .

# 5) Smoke-тесты
make cv-defect-smoke
```

Классы (см. `cv-service/scripts/synth_train_data.py`):

| ID | Имя | Severity | Описание |
|----|-----|----------|----------|
| 0 | corrosion | 1 | Рыжие пятна окисления (неровные ellipse с шумом) |
| 1 | leak      | 2 | Капли/потёки (округлые пятна с градиентом) |
| 2 | damage    | 3 | Механические повреждения (с-curve / сетка трещин) |

`severity` прокидывается в `Detection.meta.severity` и пригодится для
приоритизации ремонта в бекенде (`_run_cv_check` / auto_check).

**Метрики** (5 эпох, CPU, yolov8n):

| Class    | Images | Instances | P     | R     | mAP50 | mAP50-95 |
|----------|--------|-----------|-------|-------|-------|----------|
| all      | 100    | 252       | 0.816 | 0.943 | 0.909 | 0.778    |
| corrosion | 56    | 81        | 0.955 | 0.988 | 0.985 | 0.910    |
| leak     | 63     | 89        | 0.581 | 0.955 | 0.800 | 0.684    |
| damage   | 62     | 82        | 0.912 | 0.887 | 0.944 | 0.742    |

Что в гите: `scripts/`, `app/detectors/yolo.py`, `app/detectors/defect.py`,
`tests/test_defect_smoke.py`. Что в `.gitignore`: `cv-service/dataset/`
и `cv-service/models/` (регенерируются / тренируются локально).

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
| `GET`  | `:8001/health` | Liveness CV-сервиса (YOLOv8) |
| `GET`  | `:8001/readyz` | Readiness CV-сервиса |
| `POST` | `:8001/infer` | Детекция объектов на фото |

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

## Следующие шаги

1. [ ] Перевести frontend на отдельный сервис (Next.js / Vite+React)
2. [ ] Мобильное PWA-приложение подрядчика (offline + камера + гео)
3. [ ] ML-модель отложенной верификации (аномалии в динамике)
4. [ ] Формула рейтинга с калибровкой весов
