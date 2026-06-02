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
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.contractor import Contractor
from app.models.equipment import Equipment, EquipmentType
from app.models.object import Object, ObjectKind
from app.models.user import User, UserRole
from app.models.work import (
    ChecklistStep,
    ChecklistTemplate,
    StepDataType,
    WorkCategory,
    WorkType,
)

log = get_logger(__name__)


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
WORK_TYPES = [
    {
        "code": "TR-1",
        "name": "Текущий ремонт скважины (ТР-1)",
        "category": WorkCategory.WORKOVER,
        "duration": Decimal("72.0"),
        "equipment": None,  # для всех
        "steps": [
            ("Подготовительные работы", "Допуск, осмотр, ограждение", StepDataType.BOOLEAN, None, None, True),
            ("Проверка давления в затрубе", "Давление по манометру", StepDataType.NUMERIC,
             {"nominal": 5.0, "tolerance": 1.0, "unit": "атм"}, "P_buf", True),
            ("Спуск инструмента", "Глубина спуска", StepDataType.NUMERIC,
             {"nominal": 1500.0, "tolerance": 50.0, "unit": "м"}, None, True),
            ("Фото оборудования до работ", None, StepDataType.PHOTO, None, None, True),
            ("Промывка скважины", "Объём закачки", StepDataType.NUMERIC,
             {"nominal": 20.0, "tolerance": 5.0, "unit": "м³"}, None, True),
            ("Подъём инструмента", None, StepDataType.BOOLEAN, None, None, True),
            ("Фото оборудования после работ", None, StepDataType.PHOTO, None, None, True),
            ("Замер параметров после ТР", "Дебит жидкости", StepDataType.NUMERIC,
             {"nominal": 80.0, "tolerance": 15.0, "unit": "м³/сут"}, "Q_liq", True),
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
            ("Замер нагрузки на полированный шток", "По динамографу", StepDataType.NUMERIC,
             {"nominal": 50.0, "tolerance": 10.0, "unit": "кН"}, None, True),
            ("Проверка противовыбросового оборудования", None, StepDataType.BOOLEAN, None, None, True),
            ("Фото до ТО", None, StepDataType.PHOTO, None, None, True),
            ("Фото после ТО", None, StepDataType.PHOTO, None, None, True),
            ("Дебит жидкости после ТО", None, StepDataType.NUMERIC,
             {"nominal": 30.0, "tolerance": 8.0, "unit": "м³/сут"}, "Q_liq", True),
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
            ("Проверка тока после запуска", None, StepDataType.NUMERIC,
             {"nominal": 60.0, "tolerance": 8.0, "unit": "А"}, "I", True),
            ("Проверка частоты", None, StepDataType.NUMERIC,
             {"nominal": 50.0, "tolerance": 2.0, "unit": "Гц"}, "V_freq", True),
            ("Фото нового УЭЦН", None, StepDataType.PHOTO, None, None, True),
            ("Дебит после запуска", None, StepDataType.NUMERIC,
             {"nominal": 120.0, "tolerance": 25.0, "unit": "м³/сут"}, "Q_liq", True),
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
            ("Проверка давления на буфере", None, StepDataType.NUMERIC,
             {"nominal": 6.0, "tolerance": 1.5, "unit": "атм"}, "P_buf", True),
            ("Проверка манометров", None, StepDataType.BOOLEAN, None, None, True),
            ("Фото до ТО", None, StepDataType.PHOTO, None, None, True),
            ("Фото после ТО", None, StepDataType.PHOTO, None, None, True),
        ],
    },
]


async def seed_work_types(session: AsyncSession) -> list[WorkType]:
    """Создаёт типовые виды работ и шаблоны чек-листов."""
    out: list[WorkType] = []
    for wt_data in WORK_TYPES:
        existing = await session.scalar(
            select(WorkType).where(WorkType.code == wt_data["code"])
        )
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

        for idx, (title, desc, dtype, norm, tparam, required) in enumerate(wt_data["steps"], start=1):
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

        existing = await session.scalar(
            select(Object).where(Object.code == cluster_code)
        )
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
        existing = await session.scalar(
            select(Contractor).where(Contractor.inn == inn)
        )
        if existing:
            out.append(existing)
            continue
        c = Contractor(
            name=name, inn=inn, kpp=str(random.randint(1000000, 9999999)),
            contact_email=f"office@{name.split('«')[1].split('»')[0].lower().replace(' ', '')}.ru",
            contact_phone=f"+7{random.randint(9000000000, 9999999999)}",
            address=f"г. {random.choice(['Альметьевск', 'Бугульма', 'Лениногорск'])}, ул. Промышленная, {random.randint(1, 50)}",
            specializations="TR-1,TO-USHGN,REPLACE-UECN,TO-WELLHEAD",
            is_active=True,
        )
        session.add(c)
        out.append(c)
    await session.commit()
    log.info("seeded_contractors", count=len(out))
    return out


async def seed_users(
    session: AsyncSession, contractors: list[Contractor]
) -> list[User]:
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
            email=email, full_name=full_name, role=role,
            contractor_id=contractor_id, hashed_password=hash_password("password"),
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
    return {
        "contractors": len(contractors),
        "users": len(users),
        "work_types": len(WORK_TYPES),
    }
