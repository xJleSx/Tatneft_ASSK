"""Синтетические данные на основе отраслевых аналогов.

Источники аналогов:
- РД 153-112-017 (регламент по текущему ремонту скважин)
- ТР ТЭО 001-2006 (тех. регламент по эксплуатации УЭЦН)
- Типовые чек-листы оператора УШГН
- Аналоги: АРМ оператора ЦДНГ, 1С:ТОИР, SAP PM, IFS

Сгенерированные данные реалистичны, но синтетичны:
- Реальные ИНН/КПП валидируются по формату, но не существуют
- Геолокации — около реальных месторождений Татарстана
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.act import Act, ActStatus, ChecklistResponse
from app.models.contractor import Contractor
from app.models.equipment import Equipment, EquipmentType
from app.models.object import Object, ObjectKind
from app.models.order import WorkOrder, WorkOrderStatus
from app.models.photo import Photo, PhotoKind
from app.models.telemetry import TelemetryKind, TelemetryReading
from app.models.user import User, UserRole
from app.models.work import (
    ChecklistStep,
    ChecklistTemplate,
    StepDataType,
    WorkCategory,
    WorkType,
)

log = get_logger(__name__)


# Шаг чек-листа: (title, description, data_type, norm, telemetry_param, required)
StepT = tuple[str, str | None, StepDataType, dict[str, Any] | None, str | None, bool]


class WorkTypeDataT(TypedDict):
    code: str
    name: str
    category: WorkCategory
    duration: Decimal
    equipment: EquipmentType | None
    steps: list[StepT]


# Привязка к месторождениям Татарстана (примерные координаты кустов)
WELL_CLUSTERS = [
    ("Ромашкинское", Decimal("54.5833"), Decimal("51.7833")),
    ("Ново-Елховское", Decimal("54.9500"), Decimal("51.1000")),
    ("Бавлинское", Decimal("54.4000"), Decimal("53.2500")),
    ("Бондюжское", Decimal("55.9167"), Decimal("51.9167")),
    ("Первомайское", Decimal("54.8500"), Decimal("52.4000")),
]

CONTRACTOR_NAMES = [
    ("ООО «Уралнефтесервис»", "0278901234"),
    ("АО «Татнефть-РемСервис»", "1644012345"),
    ("ООО «Нефтегаз-Инжиниринг»", "0268012345"),
    ("ООО «Сервис-Центр»", "1655123456"),
    ("ООО «ТНГ-Групп»", "1645012345"),
    ("ООО «Промтехсервис»", "0277012345"),
]

# Типовые виды работ (на основе ТР-РД 153-112-017 и аналогов)
WORK_TYPES: list[WorkTypeDataT] = [
    {
        "code": "TR-1",
        "name": "Текущий ремонт скважины (ТР-1)",
        "category": WorkCategory.WORKOVER,
        "duration": Decimal("72.0"),
        "equipment": None,  # для всех
        "steps": [
            (
                "Подготовительные работы",
                "Допуск, осмотр, ограждение",
                StepDataType.BOOLEAN,
                None,
                None,
                True,
            ),
            (
                "Проверка давления в затрубе",
                "Давление по манометру",
                StepDataType.NUMERIC,
                {"nominal": 5.0, "tolerance": 1.0, "unit": "атм"},
                "P_buf",
                True,
            ),
            (
                "Спуск инструмента",
                "Глубина спуска",
                StepDataType.NUMERIC,
                {"nominal": 1500.0, "tolerance": 50.0, "unit": "м"},
                None,
                True,
            ),
            ("Фото оборудования до работ", None, StepDataType.PHOTO, None, None, True),
            (
                "Промывка скважины",
                "Объём закачки",
                StepDataType.NUMERIC,
                {"nominal": 20.0, "tolerance": 5.0, "unit": "м³"},
                None,
                True,
            ),
            ("Подъём инструмента", None, StepDataType.BOOLEAN, None, None, True),
            ("Фото оборудования после работ", None, StepDataType.PHOTO, None, None, True),
            (
                "Замер параметров после ТР",
                "Дебит жидкости",
                StepDataType.NUMERIC,
                {"nominal": 80.0, "tolerance": 15.0, "unit": "м³/сут"},
                "Q_liq",
                True,
            ),
            ("Заключение мастера", "Замечания", StepDataType.TEXT, None, None, False),
        ],
    },
    {
        "code": "TO-USHGN",
        "name": "ТО штангового насоса (УШГН)",
        "category": WorkCategory.ROUTINE,
        "duration": Decimal("8.0"),
        "equipment": EquipmentType.USHGN,
        "steps": [
            ("Внешний осмотр станка-качалки", None, StepDataType.BOOLEAN, None, None, True),
            ("Проверка уровня масла в редукторе", None, StepDataType.BOOLEAN, None, None, True),
            (
                "Замер нагрузки на полированный шток",
                "По динамографу",
                StepDataType.NUMERIC,
                {"nominal": 50.0, "tolerance": 10.0, "unit": "кН"},
                None,
                True,
            ),
            (
                "Проверка противовыбросового оборудования",
                None,
                StepDataType.BOOLEAN,
                None,
                None,
                True,
            ),
            ("Фото до ТО", None, StepDataType.PHOTO, None, None, True),
            ("Фото после ТО", None, StepDataType.PHOTO, None, None, True),
            (
                "Дебит жидкости после ТО",
                None,
                StepDataType.NUMERIC,
                {"nominal": 30.0, "tolerance": 8.0, "unit": "м³/сут"},
                "Q_liq",
                True,
            ),
        ],
    },
    {
        "code": "REPLACE-UECN",
        "name": "Замена УЭЦН",
        "category": WorkCategory.INSTALLATION,
        "duration": Decimal("48.0"),
        "equipment": EquipmentType.UECN,
        "steps": [
            ("Подъём старого УЭЦН", None, StepDataType.BOOLEAN, None, None, True),
            ("Дефектовка старого оборудования", "Заключение", StepDataType.TEXT, None, None, True),
            ("Монтаж нового УЭЦН", None, StepDataType.BOOLEAN, None, None, True),
            (
                "Проверка тока после запуска",
                None,
                StepDataType.NUMERIC,
                {"nominal": 60.0, "tolerance": 8.0, "unit": "А"},
                "I",
                True,
            ),
            (
                "Проверка частоты",
                None,
                StepDataType.NUMERIC,
                {"nominal": 50.0, "tolerance": 2.0, "unit": "Гц"},
                "V_freq",
                True,
            ),
            ("Фото нового УЭЦН", None, StepDataType.PHOTO, None, None, True),
            (
                "Дебит после запуска",
                None,
                StepDataType.NUMERIC,
                {"nominal": 120.0, "tolerance": 25.0, "unit": "м³/сут"},
                "Q_liq",
                True,
            ),
        ],
    },
    {
        "code": "TO-WELLHEAD",
        "name": "ТО устьевой арматуры",
        "category": WorkCategory.ROUTINE,
        "duration": Decimal("4.0"),
        "equipment": EquipmentType.WELLHEAD,
        "steps": [
            ("Осмотр фланцевых соединений", None, StepDataType.BOOLEAN, None, None, True),
            (
                "Проверка давления на буфере",
                None,
                StepDataType.NUMERIC,
                {"nominal": 6.0, "tolerance": 1.5, "unit": "атм"},
                "P_buf",
                True,
            ),
            ("Проверка манометров", None, StepDataType.BOOLEAN, None, None, True),
            ("Фото до ТО", None, StepDataType.PHOTO, None, None, True),
            ("Фото после ТО", None, StepDataType.PHOTO, None, None, True),
        ],
    },
    {
        # Двухфазный сценарий: сначала диагностика, тип работ уточняется
        # по результатам акта и выставляется отдельным нарядом.
        "code": "DIAGNOSTIC",
        "name": "Диагностика оборудования",
        "category": WorkCategory.ROUTINE,
        "duration": Decimal("2.0"),
        "equipment": None,  # применимо ко всему
        "steps": [
            ("Внешний осмотр", None, StepDataType.BOOLEAN, None, None, True),
            (
                "Замер ключевых параметров",
                None,
                StepDataType.NUMERIC,
                {"nominal": 0.0, "tolerance": 0.0, "unit": "ед"},
                None,
                True,
            ),
            ("Фото общего вида", None, StepDataType.PHOTO, None, None, True),
            (
                "Заключение о состоянии",
                "Описание дефектов и рекомендация",
                StepDataType.TEXT,
                None,
                None,
                True,
            ),
        ],
    },
]


async def seed_work_types(session: AsyncSession) -> list[WorkType]:
    """Создаёт типовые виды работ и шаблоны чек-листов."""
    out: list[WorkType] = []
    for wt_data in WORK_TYPES:
        existing = await session.scalar(select(WorkType).where(WorkType.code == wt_data["code"]))
        if existing:
            out.append(existing)
            continue

        wt = WorkType(
            code=wt_data["code"],
            name=wt_data["name"],
            category=wt_data["category"],
            planned_duration_hours=wt_data["duration"],
            applies_to_equipment_type=(
                wt_data["equipment"].value if wt_data["equipment"] else None
            ),
            description=f"Типовой регламент: {wt_data['name']}",
        )
        session.add(wt)
        await session.flush()

        template = ChecklistTemplate(work_type_id=wt.id, version=1, is_active=True)
        session.add(template)
        await session.flush()

        for idx, (title, desc, dtype, norm, tparam, required) in enumerate(
            wt_data["steps"], start=1
        ):
            step = ChecklistStep(
                template_id=template.id,
                order_index=idx,
                title=title,
                description=desc,
                data_type=dtype,
                is_required=required,
                norm_json=norm,
                telemetry_param=tparam,
            )
            session.add(step)
        out.append(wt)
    await session.commit()
    log.info("seeded_work_types", count=len(out))
    return out


async def seed_objects(session: AsyncSession, count: int = 5) -> list[Object]:
    """Создаёт кусты + скважины + оборудование."""
    out: list[Object] = []
    for i in range(count):
        cluster_name, lat, lon = WELL_CLUSTERS[i % len(WELL_CLUSTERS)]
        cluster_code = f"KUST-{i+1:03d}"

        existing = await session.scalar(select(Object).where(Object.code == cluster_code))
        if existing:
            out.append(existing)
            continue

        cluster = Object(
            name=f"Куст {cluster_name} №{i+1}",
            code=cluster_code,
            kind=ObjectKind.CLUSTER,
            latitude=lat,
            longitude=lon,
        )
        session.add(cluster)
        await session.flush()
        out.append(cluster)

        # 3-5 скважин на куст
        for w in range(random.randint(3, 5)):
            well_code = f"{cluster_code}-W{w+1:02d}"
            well = Object(
                name=f"Скважина {w+1} куста {cluster_name}",
                code=well_code,
                kind=ObjectKind.WELL,
                parent_id=cluster.id,
                # Координаты скважин слегка смещены от куста
                latitude=lat + Decimal(str(random.uniform(-0.005, 0.005))),
                longitude=lon + Decimal(str(random.uniform(-0.005, 0.005))),
            )
            session.add(well)
            await session.flush()
            out.append(well)

            # 1-2 единицы оборудования на скважину
            for e in range(random.randint(1, 2)):
                eq_type = random.choice([EquipmentType.UECN, EquipmentType.USHGN])
                eq = Equipment(
                    object_id=well.id,
                    type=eq_type,
                    serial_number=f"{eq_type.value.upper()}-{well_code}-{e+1:02d}",
                    manufacturer=random.choice(["Борец", "Элкам", "Новомет", "Schlumberger"]),
                    model=random.choice(["ЭЦН5А-250", "ЭЦН5-80", "ШНН-50-2000"]),
                    commissioned_at=date.today() - timedelta(days=random.randint(100, 1500)),
                    nominal_params_json='{"P_nom":50,"Q_nom":80}',
                )
                session.add(eq)
                await session.flush()
            # Wellhead — одна штука на скважину
            wh = Equipment(
                object_id=well.id,
                type=EquipmentType.WELLHEAD,
                serial_number=f"WH-{well_code}-01",
                manufacturer="АРМЗ",
                model="АУ-700",
                commissioned_at=date.today() - timedelta(days=random.randint(100, 1500)),
            )
            session.add(wh)
    await session.commit()
    log.info("seeded_objects", count=len(out))
    return out


async def seed_contractors(session: AsyncSession) -> list[Contractor]:
    out: list[Contractor] = []
    for name, inn in CONTRACTOR_NAMES:
        existing = await session.scalar(select(Contractor).where(Contractor.inn == inn))
        if existing:
            out.append(existing)
            continue
        c = Contractor(
            name=name,
            inn=inn,
            kpp=str(random.randint(1000000, 9999999)),
            contact_email=f"office@{name.split('«')[1].split('»')[0].lower().replace(' ', '')}.ru",
            contact_phone=f"+7{random.randint(9000000000, 9999999999)}",
            address=f"г. {random.choice(['Альметьевск', 'Бугульма', 'Лениногорск'])}, ул. Промышленная, {random.randint(1, 50)}",
            specializations="TR-1,TO-USHGN,REPLACE-UECN,TO-WELLHEAD,DIAGNOSTIC",
            is_active=True,
        )
        session.add(c)
        out.append(c)
    await session.commit()
    log.info("seeded_contractors", count=len(out))
    return out


async def seed_users(session: AsyncSession, contractors: list[Contractor]) -> list[User]:
    out: list[User] = []
    base_users = [
        ("admin@tatneft.ru", "Admin Admin", UserRole.ADMIN, None),
        ("manager@tatneft.ru", "Менеджер Качества", UserRole.MANAGER, None),
        ("tech@tatneft.ru", "Технолог ЦДНГ", UserRole.TECHNOLOGIST, None),
        ("master@tatneft.ru", "Мастер Участка", UserRole.MASTER, None),
    ]
    for email, full_name, role, contractor_id in base_users:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            out.append(existing)
            continue
        u = User(
            email=email,
            full_name=full_name,
            role=role,
            contractor_id=contractor_id,
            hashed_password=hash_password("password"),
            is_active=True,
        )
        session.add(u)
        out.append(u)

    for c in contractors:
        email = f"contractor_{c.inn}@example.ru"
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            continue
        u = User(
            email=email,
            full_name=f"Бригадир {c.name}",
            role=UserRole.CONTRACTOR,
            contractor_id=c.id,
            hashed_password=hash_password("password"),
            is_active=True,
        )
        session.add(u)
        out.append(u)
    await session.commit()
    log.info("seeded_users", count=len(out))
    return out


async def run_all_seeds(session: AsyncSession) -> dict[str, Any]:
    contractors = await seed_contractors(session)
    await seed_work_types(session)
    await seed_objects(session)
    users = await seed_users(session, contractors)
    telemetry = await seed_telemetry_history(session, days=3)
    orders, acts = await seed_work_orders_and_acts(session, contractors, users)
    rated = await recalc_contractor_ratings(session)
    return {
        "contractors": len(contractors),
        "users": len(users),
        "work_types": len(WORK_TYPES),
        "telemetry_points": telemetry,
        "work_orders": orders,
        "acts": acts,
        "ratings_recalculated": rated,
    }


async def recalc_contractor_ratings(session: AsyncSession) -> int:
    """Пересчитывает рейтинг каждого подрядчика по его нарядам/актам.

    Формула (упрощённая, для демо):
      completeness = completed / total
      timeliness   = 1.0 если нет просрочек (упрощённо: planned vs actual end)
      quality      = средний auto_check_score среди актов
      total        = средневзвешенное (0.4, 0.3, 0.3) в шкале 0..100
    """
    from app.models.act import Act, ActStatus
    from app.models.rating import ContractorRating, RatingPeriod

    today = date.today()
    period_start = today.replace(day=1)
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1) - timedelta(days=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1) - timedelta(days=1)

    contractors = (await session.scalars(select(Contractor))).all()
    updated = 0
    for c in contractors:
        orders = (
            await session.scalars(select(WorkOrder).where(WorkOrder.contractor_id == c.id))
        ).all()
        total = len(orders)
        if total == 0:
            c.rating_score = Decimal("0.00")
            updated += 1
            continue

        completed_acts = (
            await session.scalars(
                select(Act)
                .join(WorkOrder, Act.work_order_id == WorkOrder.id)
                .where(
                    WorkOrder.contractor_id == c.id,
                    Act.status.in_(
                        [
                            ActStatus.AUTO_CONFIRMED,
                            ActStatus.CONFIRMED,
                            ActStatus.VERIFIED,
                        ]
                    ),
                )
            )
        ).all()
        rejected_acts = (
            await session.scalars(
                select(Act)
                .join(WorkOrder, Act.work_order_id == WorkOrder.id)
                .where(
                    WorkOrder.contractor_id == c.id,
                    Act.status == ActStatus.REJECTED,
                )
            )
        ).all()

        completeness = len(completed_acts) / total if total else 0.0
        rejection_rate = len(rejected_acts) / total if total else 0.0
        timeliness = 1.0 - rejection_rate

        scores = [a.auto_check_score for a in completed_acts if a.auto_check_score is not None]
        quality = (sum(scores) / len(scores)) if scores else 0.5

        total_score = round(
            Decimal(str(0.4 * completeness + 0.3 * timeliness + 0.3 * quality)) * 100,
            2,
        )
        c.rating_score = total_score

        # Запишем и в историю рейтинга
        rating = ContractorRating(
            contractor_id=c.id,
            period=RatingPeriod.MONTHLY,
            period_start=period_start,
            period_end=period_end,
            orders_total=total,
            orders_completed=len(completed_acts),
            orders_auto_confirmed=sum(
                1 for a in completed_acts if a.status == ActStatus.AUTO_CONFIRMED
            ),
            orders_rejected=len(rejected_acts),
            completeness_score=Decimal(str(round(completeness * 100, 2))),
            timeliness_score=Decimal(str(round(timeliness * 100, 2))),
            quality_score=Decimal(str(round(quality * 100, 2))),
            total_score=total_score,
            weights_json='{"completeness":0.4,"timeliness":0.3,"quality":0.3}',
        )
        session.add(rating)
        updated += 1

    await session.commit()
    log.info("ratings_recalculated", count=updated)
    return updated


async def seed_telemetry_history(session: AsyncSession, days: int = 3) -> int:
    """Заполняет таблицу telemetry_readings за последние N дней (шаг 15 мин).

    Использует ту же детерминированную функцию, что и MockAsutpAdapter —
    чтобы графики в дашборде выглядели «реалистично».

    Дополнительно инжектирует 1-2 аномалии в последние 24ч на конкретных
    установках, чтобы детектор нашёл их при первом запуске.
    """
    from app.integrations.asutp.mock import _generate_params

    equipment_list = (await session.scalars(select(Equipment))).all()
    if not equipment_list:
        return 0

    existing = await session.scalar(select(func.count(TelemetryReading.id)))
    if existing and existing > 0:
        log.info("telemetry_history_already_seeded", count=existing)
        return 0

    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    step = timedelta(minutes=15)
    inserted = 0

    BATCH = 500
    batch: list[TelemetryReading] = []

    eq_types = {e.id: e.type for e in equipment_list}

    # === ИНЪЕКЦИЯ АНОМАЛИЙ (для демо детектора) ===
    # Берём первые установки подходящего типа и «ломаем» их в последние сутки.
    # Множители подобраны так, чтобы пороги детектора (0.80/0.55) сработали
    # надёжно поверх ±2% шума.
    anomaly_targets: dict[UUID, dict[str, float]] = {}
    # 1) UECN: -50% дебит (warning), 2) UECN: -70% дебит (critical),
    # 3) USHGN: -50% дебит, 4) UECN: +50% ток
    targets_needed = [
        ("uecn", "Q_liq", 0.50),
        ("uecn", "Q_liq", 0.30),  # critical
        ("ushgn", "Q_liq", 0.50),
        ("uecn", "I", 1.50),
    ]
    for want_type, param, mult in targets_needed:
        for eq in equipment_list:
            if eq.id in anomaly_targets:
                continue
            t = eq.type.value if eq.type else ""
            if t == want_type:
                anomaly_targets[eq.id] = {param: mult}
                break

    anomaly_from = now - timedelta(hours=24)

    cur = start
    while cur <= now:
        in_anom_window = cur >= anomaly_from
        for eq_id, eq_type in eq_types.items():
            # стабильный seed: equipment_id + minute bucket
            import hashlib

            bucket = int(cur.timestamp()) // 60
            seed = int(hashlib.sha256(f"{eq_id}:{bucket}".encode()).hexdigest(), 16) % (2**32)
            params = _generate_params(eq_type, seed)
            # Применяем аномалию
            if in_anom_window and eq_id in anomaly_targets:
                for p, mult in anomaly_targets[eq_id].items():
                    if p in params:
                        params[p] = round(params[p] * mult, 3)
            batch.append(
                TelemetryReading(
                    equipment_id=eq_id,
                    observed_at=cur,
                    kind=TelemetryKind.SCRAPE,
                    params=params,
                    source="seed-mock",
                )
            )
            inserted += 1
            if len(batch) >= BATCH:
                session.add_all(batch)
                await session.flush()
                batch.clear()
        cur += step

    if batch:
        session.add_all(batch)
        await session.flush()
    await session.commit()
    if anomaly_targets:
        log.info("seeded_telemetry_anomalies", equipment=len(anomaly_targets))
    log.info("seeded_telemetry", points=inserted, days=days, equipment=len(equipment_list))
    return inserted


async def seed_work_orders_and_acts(
    session: AsyncSession, contractors: list[Contractor], users: list[User]
) -> tuple[int, int]:
    """Создаёт наряды-заказы и акты в разных статусах для наглядного демо.

    Распределение:
    - 5 нарядов в ASSIGNED (ожидают выезда)
    - 3 наряда в IN_PROGRESS
    - 8 актов AUTO_CONFIRMED (хорошие работы)
    - 3 акта CONFIRMED (вручную подтверждены)
    - 2 акта REJECTED (с замечаниями)
    - 2 акта DELAYED_VERIFICATION (на отложенной проверке)
    """
    from app.integrations.asutp.mock import _generate_params

    wells = (await session.scalars(select(Object).where(Object.kind == ObjectKind.WELL))).all()
    work_types = (await session.scalars(select(WorkType))).all()
    if not wells or not work_types or not contractors:
        return 0, 0

    existing = await session.scalar(select(func.count(WorkOrder.id)))
    if existing and existing > 0:
        log.info("orders_acts_already_seeded", count=existing)
        return 0, 0

    contractor_users: dict[UUID, User] = {
        u.contractor_id: u for u in users if u.role == UserRole.CONTRACTOR and u.contractor_id
    }
    managers = [u for u in users if u.role == UserRole.MANAGER]
    masters = [u for u in users if u.role == UserRole.MASTER]

    def gen_number(i: int) -> str:
        return f"WO-{datetime.now(UTC).strftime('%Y%m%d')}-{i:04d}"

    orders: list[WorkOrder] = []
    acts: list[Act] = []

    # 1) Назначенные, ожидают выезда (5 шт) — без актов
    for i in range(5):
        wo = WorkOrder(
            number=gen_number(len(orders) + 1),
            object_id=wells[i % len(wells)].id,
            work_type_id=work_types[i % len(work_types)].id,
            contractor_id=contractors[i % len(contractors)].id,
            assigned_by_user_id=managers[0].id if managers else None,
            status=WorkOrderStatus.ASSIGNED,
            planned_start_at=datetime.now(UTC) + timedelta(days=i + 1),
            planned_end_at=datetime.now(UTC) + timedelta(days=i + 1, hours=8),
            planned_cost=Decimal(str(50000 + i * 7500)),
            description=f"Плановые работы по графику {i + 1}",
        )
        session.add(wo)
        orders.append(wo)

    # 2) В работе у подрядчика (3 шт) — без актов
    for i in range(3):
        wo = WorkOrder(
            number=gen_number(len(orders) + 1),
            object_id=wells[(i + 5) % len(wells)].id,
            work_type_id=work_types[(i + 1) % len(work_types)].id,
            contractor_id=contractors[(i + 1) % len(contractors)].id,
            assigned_by_user_id=managers[0].id if managers else None,
            status=WorkOrderStatus.IN_PROGRESS,
            planned_start_at=datetime.now(UTC) - timedelta(days=1),
            planned_end_at=datetime.now(UTC) + timedelta(hours=4),
            actual_start_at=datetime.now(UTC) - timedelta(hours=20),
            planned_cost=Decimal(str(70000 + i * 10000)),
            description="В работе у подрядчика",
        )
        session.add(wo)
        orders.append(wo)

    # 3) «Исторические» наряды — отдельные, чтобы делать по ним акты в разных статусах
    # 8 AUTO_CONFIRMED + 2 CONFIRMED + 2 DELAYED_VERIFICATION + 2 REJECTED = 14
    HISTORICAL_COUNT = 14
    for i in range(HISTORICAL_COUNT):
        wo = WorkOrder(
            number=gen_number(len(orders) + 1),
            object_id=wells[(i + 8) % len(wells)].id,
            work_type_id=work_types[i % len(work_types)].id,
            contractor_id=contractors[i % len(contractors)].id,
            assigned_by_user_id=managers[0].id if managers else None,
            status=WorkOrderStatus.IN_PROGRESS,  # временно, потом переопределим
            planned_start_at=datetime.now(UTC) - timedelta(days=3),
            planned_end_at=datetime.now(UTC) - timedelta(days=2),
            actual_start_at=datetime.now(UTC) - timedelta(days=2, hours=20),
            actual_end_at=datetime.now(UTC) - timedelta(days=2, hours=10),
            planned_cost=Decimal(str(60000 + i * 5000)),
            actual_cost=Decimal(str(58000 + i * 4800)),
            description="Архивная заявка для демонстрации",
        )
        session.add(wo)
        orders.append(wo)

    await session.flush()
    log.info("seeded_work_orders", count=len(orders))

    # 3) Создаём акты с разными исходами
    async def make_act(
        wo: WorkOrder,
        status: ActStatus,
        wo_status: WorkOrderStatus,
        completed_hours_ago: int,
        *,
        with_photos: bool = True,
        rejection_comment: str | None = None,
        reviewer_comment: str | None = None,
    ) -> Act | None:
        cu = contractor_users.get(wo.contractor_id) if wo.contractor_id else None
        if not cu:
            return None

        tpl = await session.scalar(
            select(ChecklistTemplate).where(ChecklistTemplate.work_type_id == wo.work_type_id)
        )
        if not tpl:
            return None
        steps = list(
            await session.scalars(select(ChecklistStep).where(ChecklistStep.template_id == tpl.id))
        )
        if not steps:
            return None

        completed_at = datetime.now(UTC) - timedelta(hours=completed_hours_ago)
        well = await session.get(Object, wo.object_id)

        # Снимки телеметрии до/после (синтетика, но стабильная)
        equipment_for_well = (
            await session.scalars(select(Equipment).where(Equipment.object_id == wo.object_id))
        ).all()
        before: dict[str, dict] = {}
        after: dict[str, dict] = {}
        import hashlib

        for eq in equipment_for_well:
            bseed = int(
                hashlib.sha256(
                    f"{eq.id}:{int((completed_at - timedelta(hours=2)).timestamp()) // 60}".encode()
                ).hexdigest(),
                16,
            ) % (2**32)
            aseed = int(
                hashlib.sha256(
                    f"{eq.id}:{int(completed_at.timestamp()) // 60}".encode()
                ).hexdigest(),
                16,
            ) % (2**32)
            before[eq.serial_number] = _generate_params(eq.type, bseed)
            after[eq.serial_number] = _generate_params(eq.type, aseed)

        act = Act(
            work_order_id=wo.id,
            contractor_user_id=cu.id,
            status=status,
            actual_latitude=well.latitude if well and well.latitude else None,
            actual_longitude=well.longitude if well and well.longitude else None,
            actual_at=completed_at,
            telemetry_before_json=before,
            telemetry_after_json=after,
            reviewer_comment=reviewer_comment,
        )
        if status in (ActStatus.AUTO_CONFIRMED, ActStatus.CONFIRMED, ActStatus.VERIFIED):
            act.auto_check_passed = True
            act.auto_check_score = round(random.uniform(0.85, 0.99), 4)
        elif status == ActStatus.DELAYED_VERIFICATION:
            act.auto_check_passed = False
            act.auto_check_score = round(random.uniform(0.5, 0.7), 4)
        elif status == ActStatus.REJECTED:
            act.auto_check_passed = False
            act.auto_check_score = round(random.uniform(0.3, 0.6), 4)
            act.auto_check_details = {
                "failed_rules": ["step_missing", "geo_out_of_radius"],
                "checklist": {"total": len(steps), "passed": max(1, len(steps) - 2)},
            }

        if status in (ActStatus.CONFIRMED, ActStatus.VERIFIED, ActStatus.REJECTED):
            act.confirmed_by_user_id = masters[0].id if masters else None
            act.confirmed_at = completed_at + timedelta(hours=2)

        session.add(act)
        await session.flush()

        # Ответы чек-листа
        for step in steps:
            if step.data_type == StepDataType.NUMERIC and step.norm_json:
                nominal = float(step.norm_json.get("nominal", 0))
                tol = float(step.norm_json.get("tolerance", 1))
                # в хороших актах — в допуске, в плохих — с отклонением
                if status in (ActStatus.AUTO_CONFIRMED, ActStatus.CONFIRMED, ActStatus.VERIFIED):
                    value = nominal + random.uniform(-tol * 0.5, tol * 0.5)
                elif status == ActStatus.DELAYED_VERIFICATION:
                    value = nominal + random.choice([-1, 1]) * tol * 0.6
                else:
                    value = nominal + random.choice([-1, 1]) * tol * 1.8
                passed = abs(value - nominal) <= tol
                session.add(
                    ChecklistResponse(
                        act_id=act.id,
                        step_id=step.id,
                        value_numeric=Decimal(str(round(value, 3))),
                        passed=passed,
                    )
                )
            elif step.data_type == StepDataType.BOOLEAN:
                passed = (
                    status in (ActStatus.AUTO_CONFIRMED, ActStatus.CONFIRMED, ActStatus.VERIFIED)
                    or random.random() > 0.2
                )
                session.add(
                    ChecklistResponse(
                        act_id=act.id, step_id=step.id, value_bool=passed, passed=passed
                    )
                )
            elif step.data_type == StepDataType.PHOTO:
                # Фото ниже — запишем Photo-записи
                pass
            else:
                session.add(
                    ChecklistResponse(
                        act_id=act.id,
                        step_id=step.id,
                        value_text=(
                            "Замечаний нет"
                            if status
                            in (ActStatus.AUTO_CONFIRMED, ActStatus.CONFIRMED, ActStatus.VERIFIED)
                            else "Обнаружены следы износа, требуется повторный осмотр"
                        ),
                        passed=(status not in (ActStatus.REJECTED,)),
                    )
                )

        if with_photos:
            # До и после
            for kind in (PhotoKind.BEFORE, PhotoKind.AFTER):
                session.add(
                    Photo(
                        act_id=act.id,
                        kind=kind,
                        object_key=f"synthetic/acts/{act.id}/{kind.value}.jpg",
                        content_type="image/jpeg",
                        size_bytes=random.randint(150_000, 800_000),
                        taken_at=completed_at,
                        latitude=act.actual_latitude,
                        longitude=act.actual_longitude,
                        sha256=hashlib.sha256(f"{act.id}-{kind.value}".encode()).hexdigest(),
                        created_at=completed_at,
                    )
                )

        wo.status = wo_status
        if status == ActStatus.REJECTED:
            wo.rejection_reason = rejection_comment or "Не соответствует регламенту"

        return act

    # Берём исторические наряды (последние 14)
    historical = orders[-HISTORICAL_COUNT:] if len(orders) >= HISTORICAL_COUNT else orders
    if len(historical) >= 8:
        for i, wo in enumerate(historical[:8]):
            await make_act(
                wo,
                ActStatus.AUTO_CONFIRMED,
                WorkOrderStatus.AUTO_CONFIRMED,
                completed_hours_ago=24 + i * 6,
            )
            acts.append(wo)  # type: ignore[arg-type]
    if len(historical) >= 10:
        for i, wo in enumerate(historical[8:10]):
            await make_act(
                wo, ActStatus.CONFIRMED, WorkOrderStatus.CONFIRMED, completed_hours_ago=48 + i * 12
            )
            acts.append(wo)  # type: ignore[arg-type]
    if len(historical) >= 12:
        for i, wo in enumerate(historical[10:12]):
            await make_act(
                wo,
                ActStatus.DELAYED_VERIFICATION,
                WorkOrderStatus.DELAYED_VERIFICATION,
                completed_hours_ago=72,
                with_photos=(i % 2 == 0),
            )
            acts.append(wo)  # type: ignore[arg-type]
    if len(historical) >= 14:
        for i, wo in enumerate(historical[12:14]):
            await make_act(
                wo,
                ActStatus.REJECTED,
                WorkOrderStatus.REJECTED,
                completed_hours_ago=96,
                rejection_comment="Не приложены фото «до», не заполнены обязательные пункты",
                with_photos=False,
            )
            acts.append(wo)  # type: ignore[arg-type]

    await session.commit()
    log.info("seeded_acts", count=len(acts), work_orders=len(orders))
    return len(orders), len(acts)
