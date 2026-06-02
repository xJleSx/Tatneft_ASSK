# CHANGELOG

Все изменения, **не запушенные** в remote — смотри `git log main..HEAD` после `git push`.

## Незапушенные улучшения (MVP: аномалии + двухфазные наряды)

| # | Тип | Файл | Что сделано |
|---|---|---|---|
| 1 | **feat(backend)** | `backend/app/services/anomaly_detector.py` | Детектор аномалий телеметрии (compute-on-the-fly, без новой таблицы). Сравнивает последние 6ч с baseline 24ч назад. Правила: падение дебита (<80% / <60%), перегруз по току, перегрев, превышение давления, data-gap. |
| 2 | **feat(backend)** | `backend/app/api/v1/anomalies.py` | `GET /anomalies/` с фильтрами `object_id` и `min_severity`. Возвращает `{items, total, critical, warning}`. Поле `suggested_work_type_code` для one-click создания наряда. |
| 3 | **feat(backend)** | `backend/app/models/order.py` | `WorkOrderPriority` enum (low/normal/high/critical), `work_type_id` стал nullable, новые поля: `priority`, `defect_ref`, `is_diagnostic`. |
| 4 | **feat(backend)** | `backend/alembic/versions/c4d2e1f8b901_work_order_priority_and_diagnostic.py` | Миграция: enum `work_order_priority` + 3 новых колонки + relax NOT NULL на `work_type_id`. |
| 5 | **feat(backend)** | `backend/app/schemas/order.py` | `WorkOrderBase/Create/Update/Out` обновлены: новые поля. `WorkOrderCreate.work_type_id` опционально. |
| 6 | **feat(backend)** | `backend/app/api/v1/orders.py` | `POST /orders/` принимает `priority`, `defect_ref`, `is_diagnostic`, nullable `work_type_id`. |
| 7 | **feat(backend)** | `backend/app/mocks/generators/seed.py` | Новый вид работ `DIAGNOSTIC` (4 шага: осмотр/замер/фото/заключение). В `seed_telemetry_history` инжектируются 4 аномалии (1 critical debit, 1 warning debit, 1 warning USHGN debit, 1 warning motor overload) на последние 24ч. Все подрядчики получают спец. `DIAGNOSTIC`. |
| 8 | **feat(backend)** | `backend/app/main.py` | Роутер `/anomalies/` зарегистрирован. |
| 9 | **feat(frontend)** | `frontend/index.html` | Карточка «Аномалии АСУ ТП» в дашборде (critical/warning, left-strip, кнопка «Создать наряд» пре-заполняет модал: object, suggested_wt, priority, defect_ref). |
| 10 | **feat(frontend)** | `frontend/index.html` | Модал создания наряда переделан в 3-step wizard: (1) объект + авто-подсказка аномалии с кнопкой «Создать диагностику», (2) тип работ + чекбокс «только диагностика» + подрядчик (фильтр по спец-ям), (3) сроки/стоимость/описание. Stepper сверху. Новые поля: `priority`, `defect_ref`. |
| 11 | **test** | `scripts/test_anomaly_flow.py` | E2E: детектор аномалий → создание наряда на диагностику (priority=critical, is_diagnostic=True, defect_ref сгенерён) → подрядчик берёт в работу → заполняет 4-step чек-лист → подаёт акт → auto-check score. |

## Ранее запушенное

| Коммит | Что |
|---|---|
| `5265e5c` | feat(frontend+backend): contractor mobile UI + photo upload with EXIF + start endpoint |
| `63a3a1a` | feat(frontend): industrial control panel redesign (manager dashboard) |
| `f551f36` | test: web form POST flow simulation |
| `a16788f` | feat(frontend): modal for creating work order |
| `e03450d` | fix: unique WO numbers + work_order eager-load in rule engine |
| `0bde7ae` | demo script, frontend dashboard, fix template endpoint, contractor rating |
| `bdc2e4b` | docs: backend README with setup instructions |
| `2caae93` | test+docs: geo unit tests + analogs documentation |
| `ee0d86a` | feat: SQLAlchemy models |
| `ff3d582` | feat(db): alembic setup with initial schema migration |
| `1d73aec` | chore: project scaffold |

## Что появится в UI после открытия http://127.0.0.1:5500/

- Новая карточка **«Аномалии АСУ ТП»** с цветной left-stripe (red=critical, amber=warning), кодом аномалии, серийным номером оборудования, описанием, рекомендуемым типом работ
- Кнопка **«Создать наряд»** на карточке аномалии открывает wizard с предзаполненными полями (объект, приоритет, тип работ, defect_ref `DF-ANOM-...`)
- В модале создания наряда:
  - **Шаг 1**: выбор объекта → если по нему есть аномалия, появляется плашка «Зафиксирована аномалия» с кнопками «Создать диагностику» / «Игнорировать»
  - **Шаг 2**: тип работ (можно оставить пустым) + чекбокс «Только диагностика» + подрядчик (фильтруется по специализации)
  - **Шаг 3**: сроки, стоимость, описание
- Везде в формах: **приоритет** (low/normal/high/critical) и **№ дефекта** (1С/SAP)

## E2E проверка

```bash
$env:PYTHONIOENCODING="utf-8"
python scripts/test_anomaly_flow.py
```

Ожидаемый итог:
- total=3, critical=1, warning=2
- создан наряд `WO-YYYYMMDD-XXXXXX`, status=assigned, priority=critical, is_diagnostic=True, defect_ref=`DF-ANOM-...`
- подрядчик берёт в работу → status=in_progress
- акт создан и подан, auto_check_score вычислен

## ⚠️ Напоминание про безопасность

**6+ GitHub PAT всё ещё лежат в чате.** Отзови на https://github.com/settings/tokens — это **твои токены**, и я не могу их отозвать за тебя.
