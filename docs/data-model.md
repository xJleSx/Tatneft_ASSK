# Data Model (ER)

> Диаграмма сущностей прототипа. Полное описание полей — в docstring
> каждой модели в `backend/app/models/`.

```
                  ┌─────────────┐
                  │   User      │── role: admin/manager/technologist/master/contractor
                  └──────┬──────┘
                         │ N
                         │
                  ┌──────┴──────┐
                  │ Contractor  │── rating_score (денорм.)
                  └──────┬──────┘
                         │ 1
                         │
                  ┌──────┴──────┐         ┌──────────────┐
                  │ WorkOrder   │────────▶│   Object     │── kind: cluster/well/facility
                  │  status     │         │  (lat/lon)   │── parent_id (иерархия)
                  └──────┬──────┘         └──────┬───────┘
                         │ 1                    │ 1
                         │                      │
                         │ N              ┌─────┴──────┐
                  ┌──────┴──────┐         │ Equipment  │── type: UECN/USHGN/WH/...
                  │    Act      │         └─────┬──────┘
                  │   status    │               │ 1
                  └─┬───────┬───┘               │
                    │ N     │ N                 │ N
            ┌───────┘       └───────┐     ┌─────┴──────────┐
            ▼                       ▼     ▼                ▼
   ┌─────────────────┐     ┌──────────────┐      ┌─────────────────────┐
   │ ChecklistResp   │     │   Photo      │      │  TelemetryReading   │
   │ value (bool/num/│     │ kind:before/ │      │  params (JSONB)     │
   │ text/json)      │     │  after/issue │      │  source:mock/...    │
   └────────┬────────┘     └──────────────┘      └─────────────────────┘
            │ N
            │
            │ 1
   ┌────────┴────────┐         ┌──────────────────┐
   │ ChecklistStep   │────────▶│ ChecklistTpl     │── 1:1 WorkType
   │ norm_json       │         │ version, active  │
   │ telemetry_param │         └──────────────────┘
   └─────────────────┘

   ┌──────────────────┐
   │ ContractorRating │── 1:1 Contractor, period: month/quarter/year
   └──────────────────┘

   ┌──────────┐
   │ AuditLog │── user_id (nullable), action, entity_type, entity_id, details
   └──────────┘
```

## Ключевые решения

1. **Иерархия Object** (cluster/well/facility) — `parent_id` self-FK, чтобы можно
   было подниматься от скважины к кусту (для отчётов по месторождению).
2. **UUID как PK** — безопасно для распределённой генерации, удобно для API.
3. **Photo в MinIO/S3** — в БД только ключ + метаданные (гео, EXIF, hash).
4. **Telemetry** — JSONB + индекс `(equipment_id, observed_at)`. В проде —
   TimescaleDB hypertable (см. миграцию для ручного вызова `create_hypertable`).
5. **ChecklistResponse** — универсальный контейнер значения (bool/num/text/json)
   чтобы не плодить таблицы под типы.
6. **Act/WorkOrder статусы** — конечный автомат, переходы контролируются
   в `api/v1/acts.py` и `orders.py`.
7. **AuditLog** — JSONB details, ip, user_agent. Пишется через middleware
   (TODO) или явно в сервисах.
8. **ContractorRating** — отдельная таблица, чтобы не терять историю
   при пересчёте. В `Contractor.rating_score` — денорм. текущий.
