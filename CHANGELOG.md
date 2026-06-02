# CHANGELOG

Все изменения, **не запушенные** в remote — смотри `git log main..HEAD` после `git push`.

## Незапушенные улучшения (коммит TBD)

| # | Тип | Файл | Что сделано |
|---|---|---|---|
| 1 | **feat(frontend)** | `frontend/index.html` | Панель «Акты на проверке» для master/technologist/manager/admin. Список актов `submitted`/`delayed_verification` с кнопками ✓ Подтвердить / ✗ Отклонить + поле комментария. Видна только ревью-ролям. |
| 2 | **feat(frontend)** | `frontend/index.html` | Модал «Детали наряда» — клик по строке в списке → наряд целиком + связанные акты (таблица). |
| 3 | **feat(frontend)** | `frontend/index.html` | Фильтр по статусам — чипы над списком нарядов: `все / назначен / в работе / на проверке / авто ✓ / подтверждён / отклонён`. Активный чип подсвечен. |
| 4 | **feat(frontend)** | `frontend/index.html` | Авто-рефреш каждые 30 сек (toggle чекбоксом). Не дёргает во время открытых модалок. Лейбл «обновлено N сек назад» обновляется каждые 5 сек, индикатор-пульсар. |
| 5 | **feat(frontend)** | `frontend/index.html` | Параллельная загрузка дашборда (4 endpoint-а в `Promise.all`) — заметно быстрее. |
| 6 | **feat(frontend)** | `frontend/index.html` | Кликабельные строки нарядов (cursor: pointer). |
| 7 | **feat(backend)** | `backend/app/api/v1/orders.py` | Новый endpoint `GET /orders/{order_id}` с проверкой прав (подрядчик видит только свои). Нужен для модала деталей. |
| 8 | **test** | `scripts/test_review_flow.py` | E2E тест: GET /orders/{id}, GET /acts?work_order_id=..., POST /acts/{id}/review, 404 на несуществующий. |
| 9 | **fix(frontend)** | `frontend/index.html` | Закрыт тег `</script>` (был утерян при правке) — без этого страница не исполняла JS. |

## Ранее запушенное

| Коммит | Что |
|---|---|
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

- Сверху над KPI — **пульсирующая зелёная точка** + «обновлено N сек назад» + чекбокс «30с»
- Новая карточка **«Акты на проверке»** (только для master/tech/manager/admin) с inline-кнопками
- В блоке «Наряды-заказы» — **чипы-фильтры** по статусам
- Клик по любой строке наряда — **модал с деталями** (наряд + связанные акты)

## Как закоммитить и запушить одной командой

```bash
cd C:\Users\JleS\OpenCode\projects\askk-prototype
git add -A
git commit -m "feat(frontend): review panel, order detail, status filter, auto-refresh"
# затем git push
```

## ⚠️ Напоминание про безопасность

**6+ GitHub PAT всё ещё лежат в чате.** Отзови на https://github.com/settings/tokens — это **твои токены**, и я не могу их отозвать за тебя.
