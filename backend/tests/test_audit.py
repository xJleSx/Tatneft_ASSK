"""Тесты AuditLog: записи создаются на ключевых действиях."""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.act import Act, ActStatus
from app.models.audit import AuditLog
from app.models.contractor import Contractor
from app.models.equipment import Equipment, EquipmentType
from app.models.object import Object, ObjectKind
from app.models.order import WorkOrder, WorkOrderStatus
from app.models.work import WorkCategory, WorkType
from app.services.audit import audit

# ---------- Unit: helper ----------


@pytest.mark.asyncio
async def test_audit_helper_adds_record(db_session):
    """audit() кладёт запись в session, не делает commit."""
    audit(
        db_session,
        action="test.action",
        entity_type="thing",
        details={"k": "v"},
    )
    await db_session.flush()
    rows = (await db_session.scalars(select(AuditLog))).all()
    assert len(rows) == 1
    assert rows[0].action == "test.action"
    assert rows[0].entity_type == "thing"
    assert rows[0].details == {"k": "v"}


# ---------- Integration: HTTP endpoints ----------


async def _seed_min_world(db_session, manager):
    """Объект + вид работ + подрядчик + оборудование + наряд для тестов."""
    obj = Object(
        id=uuid4(),
        name="Куст 101",
        code="OBJ-101",
        kind=ObjectKind.CLUSTER,
    )
    db_session.add(obj)
    await db_session.flush()

    wt = WorkType(
        id=uuid4(),
        code="REP",
        name="Ремонт",
        category=WorkCategory.ROUTINE,
    )
    db_session.add(wt)
    await db_session.flush()

    con = Contractor(id=uuid4(), name="ООО ТестПодряд", inn="1234567890")
    db_session.add(con)
    await db_session.flush()

    eq = Equipment(
        id=uuid4(),
        object_id=obj.id,
        serial_number="EQ-TEST-1",
        type=EquipmentType.USHGN,
    )
    db_session.add(eq)
    await db_session.flush()

    wo = WorkOrder(
        id=uuid4(),
        number="WO-TEST-001",
        object_id=obj.id,
        work_type_id=wt.id,
        contractor_id=con.id,
        status=WorkOrderStatus.ASSIGNED,
    )
    db_session.add(wo)
    await db_session.flush()
    return obj, wt, con, eq, wo


@pytest.mark.asyncio
async def test_login_success_writes_audit_log(client: AsyncClient, db_session, contractor_user):
    """auth.login запись с user_id, action, ip, user-agent."""
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": contractor_user.email, "password": "password123"},
        headers={"User-Agent": "pytest"},
    )
    assert r.status_code == 200, r.text

    rows = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.login")
    )).all()
    assert len(rows) == 1
    rec = rows[0]
    assert rec.user_id == contractor_user.id
    assert rec.entity_id == contractor_user.id
    assert rec.user_agent == "pytest"
    assert rec.ip_address is not None  # httpx ASGITransport даёт 127.0.0.1


@pytest.mark.asyncio
async def test_login_failure_writes_audit_log(client: AsyncClient, db_session):
    """auth.login_failed запись (без user_id, только email в details)."""
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.ru", "password": "wrong"},
    )
    assert r.status_code == 401

    rows = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.login_failed")
    )).all()
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].details == {"email": "nobody@nowhere.ru"}


@pytest.mark.asyncio
async def test_create_order_writes_audit_log(
    client: AsyncClient, db_session, manager_user, manager_token
):
    obj, wt, con, _eq, _wo = await _seed_min_world(db_session, manager_user)

    r = await client.post(
        "/api/v1/orders/",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={
            "object_id": str(obj.id),
            "work_type_id": str(wt.id),
            "contractor_id": str(con.id),
            "priority": "high",
            "is_diagnostic": False,
        },
    )
    assert r.status_code == 201, r.text

    rows = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "order.create")
    )).all()
    assert len(rows) == 1
    rec = rows[0]
    assert rec.user_id == manager_user.id
    assert rec.entity_type == "work_order"
    assert rec.entity_id is not None
    assert rec.details["priority"] == "high"
    assert rec.details["contractor_id"] == str(con.id)
    assert rec.details["is_diagnostic"] is False


@pytest.mark.asyncio
async def test_update_order_status_writes_audit_log(
    client: AsyncClient, db_session, manager_user, manager_token
):
    """order.update фиксирует status_from/status_to при смене статуса."""
    obj, wt, con, _eq, wo = await _seed_min_world(db_session, manager_user)

    r = await client.patch(
        f"/api/v1/orders/{wo.id}",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"status": "cancelled"},
    )
    assert r.status_code == 200, r.text

    rows = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "order.update")
    )).all()
    assert len(rows) == 1
    assert rows[0].details["status_from"] == "assigned"
    assert rows[0].details["status_to"] == "cancelled"


@pytest.mark.asyncio
async def test_invalid_transition_does_not_write_audit(
    client: AsyncClient, db_session, manager_user, manager_token
):
    """При отказе FSM (запрещённый переход) аудит НЕ пишется — отказ до мутации."""
    obj, wt, con, _eq, wo = await _seed_min_world(db_session, manager_user)

    # assigned -> confirmed — запрещён
    r = await client.patch(
        f"/api/v1/orders/{wo.id}",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"status": "confirmed"},
    )
    assert r.status_code == 400

    rows = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "order.update")
    )).all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_submit_act_writes_two_audit_logs(
    client: AsyncClient, db_session, contractor_user, contractor_token
):
    """submit_act пишет act.submit + act.auto_check (passed/failed)."""
    obj, wt, con, _eq, wo = await _seed_min_world(db_session, contractor_user)

    # Наряд -> in_progress
    wo.status = WorkOrderStatus.IN_PROGRESS
    await db_session.flush()

    # Черновик акта
    act = Act(
        id=uuid4(),
        work_order_id=wo.id,
        contractor_user_id=contractor_user.id,
        status=ActStatus.DRAFT,
        actual_at=wo.planned_start_at or wo.created_at,
    )
    db_session.add(act)
    await db_session.flush()

    r = await client.post(
        f"/api/v1/acts/{act.id}/submit",
        headers={"Authorization": f"Bearer {contractor_token}"},
        json={
            "responses": [],
            "actual_at": act.actual_at.isoformat(),
            "actual_latitude": 55.0,
            "actual_longitude": 50.0,
        },
    )
    assert r.status_code == 200, r.text

    submit_rows = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "act.submit")
    )).all()
    auto_rows = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "act.auto_check")
    )).all()
    assert len(submit_rows) == 1
    assert len(auto_rows) == 1
    assert "passed" in auto_rows[0].details
    assert "score" in auto_rows[0].details
    assert "final_status" in auto_rows[0].details


@pytest.mark.asyncio
async def test_review_act_writes_audit_with_decision(
    client: AsyncClient, db_session, contractor_user, master_user, master_token
):
    """review_act: action = act.review.confirm / act.review.reject."""
    obj, wt, con, _eq, wo = await _seed_min_world(db_session, contractor_user)
    wo.status = WorkOrderStatus.AUTO_CONFIRMED
    act = Act(
        id=uuid4(),
        work_order_id=wo.id,
        contractor_user_id=contractor_user.id,
        status=ActStatus.AUTO_CONFIRMED,
    )
    db_session.add(act)
    await db_session.flush()

    r = await client.post(
        f"/api/v1/acts/{act.id}/review",
        headers={"Authorization": f"Bearer {master_token}"},
        json={"decision": "confirm", "comment": "OK"},
    )
    assert r.status_code == 200, r.text

    rows = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action.like("act.review.%"))
    )).all()
    assert len(rows) == 1
    assert rows[0].action == "act.review.confirm"
    assert rows[0].details["comment"] == "OK"
    assert rows[0].user_id == master_user.id
