"""Тесты app/schemas/*."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.act import ActStatus
from app.models.equipment import EquipmentType
from app.models.object import ObjectKind
from app.models.order import WorkOrderPriority, WorkOrderStatus
from app.models.photo import PhotoKind
from app.models.user import UserRole
from app.models.work import StepDataType, WorkCategory
from app.schemas.common import IdName, MessageResponse, PaginatedResponse
from app.schemas.object import (
    EquipmentBase,
    ObjectBase,
    ObjectCreate,
    ObjectUpdate,
)
from app.schemas.order import (
    ActCreate,
    ActOut,
    ActReview,
    ActSubmit,
    ChecklistResponseIn,
    ChecklistResponseOut,
    WorkOrderBase,
    WorkOrderCreate,
    WorkOrderOut,
    WorkOrderUpdate,
)
from app.schemas.photo import PhotoOut, PhotoUploadRequest, TelemetryOut
from app.schemas.user import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserOut,
)
from app.schemas.work import (
    ChecklistStepBase,
    ChecklistStepCreate,
    ChecklistTemplateCreate,
    WorkTypeBase,
)

# ---------- common ----------


def test_id_name():
    obj = IdName(id=uuid4(), name="test")
    assert obj.name == "test"


def test_paginated_response():
    r = PaginatedResponse(items=[1, 2, 3], total=3, page=1, size=10)
    assert r.total == 3


def test_message_response_no_details():
    r = MessageResponse(message="ok")
    assert r.details is None


def test_message_response_with_details():
    r = MessageResponse(message="ok", details={"k": "v"})
    assert r.details == {"k": "v"}


# ---------- user schemas ----------


def test_user_create_short_password_fails():
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.c", full_name="X", role=UserRole.MANAGER, password="short")


def test_user_create_long_password_fails():
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.c", full_name="X", role=UserRole.MANAGER, password="x" * 200)


def test_user_create_min_password_ok():
    u = UserCreate(email="a@b.c", full_name="X", role=UserRole.MANAGER, password="12345678")
    assert u.password == "12345678"


def test_user_create_invalid_email_fails():
    with pytest.raises(ValidationError):
        UserCreate(email="not-an-email", full_name="X", role=UserRole.MANAGER, password="secret123")


def test_user_out_required_fields():
    u = UserOut(
        id=uuid4(),
        email="a@b.c",
        full_name="X",
        role=UserRole.MANAGER,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    assert u.is_active is True
    assert u.last_login_at is None


def test_login_request():
    r = LoginRequest(email="a@b.c", password="secret")
    assert r.password == "secret"


def test_refresh_request():
    r = RefreshRequest(refresh_token="x")
    assert r.refresh_token == "x"


def test_token_response_defaults():
    r = TokenResponse(access_token="a", refresh_token="b", expires_in=60)
    assert r.token_type == "bearer"


# ---------- order schemas ----------


def test_work_order_base_defaults():
    wo = WorkOrderBase(object_id=uuid4())
    assert wo.priority == WorkOrderPriority.NORMAL
    assert wo.is_diagnostic is False
    assert wo.work_type_id is None
    assert wo.contractor_id is None


def test_work_order_create_no_number():
    wo = WorkOrderCreate(object_id=uuid4())
    assert wo.number is None


def test_work_order_update_all_optional():
    wo = WorkOrderUpdate()
    assert wo.contractor_id is None
    assert wo.status is None
    assert wo.priority is None


def test_work_order_out():
    wo = WorkOrderOut(
        id=uuid4(),
        object_id=uuid4(),
        number="WO-1",
        status=WorkOrderStatus.DRAFT,
        priority=WorkOrderPriority.NORMAL,
        is_diagnostic=False,
        created_at=datetime.now(UTC),
    )
    assert wo.number == "WO-1"


def test_act_review_pattern_invalid():
    with pytest.raises(ValidationError):
        ActReview(decision="unknown")


def test_act_review_confirm():
    r = ActReview(decision="confirm", comment="ok")
    assert r.decision == "confirm"


def test_act_review_reject():
    r = ActReview(decision="reject", comment="bad")
    assert r.decision == "reject"


def test_checklist_response_in_minimal():
    r = ChecklistResponseIn(step_id=uuid4())
    assert r.value_bool is None


def test_checklist_response_out_includes_id():
    r = ChecklistResponseOut(id=uuid4(), step_id=uuid4(), passed=True)
    assert r.passed is True


def test_act_create_default_responses():
    r = ActCreate(work_order_id=uuid4())
    assert r.responses == []
    assert r.photo_keys == []


def test_act_submit_requires_actual_coords():
    with pytest.raises(ValidationError):
        ActSubmit(actual_latitude=None, actual_longitude=Decimal("50"), actual_at=datetime.now(UTC))


def test_act_out_full():
    r = ActOut(
        id=uuid4(),
        work_order_id=uuid4(),
        contractor_user_id=uuid4(),
        status=ActStatus.DRAFT,
        auto_check_passed=None,
        auto_check_score=None,
        auto_check_details=None,
        confirmed_by_user_id=None,
        confirmed_at=None,
        reviewer_comment=None,
        created_at=datetime.now(UTC),
    )
    assert r.status == ActStatus.DRAFT


# ---------- object schemas ----------


def test_object_base():
    o = ObjectBase(name="X", code="X-1", kind=ObjectKind.WELL)
    assert o.kind == ObjectKind.WELL
    assert o.latitude is None


def test_object_create():
    ObjectCreate(name="X", code="X-1", kind=ObjectKind.CLUSTER)


def test_object_update_all_optional():
    u = ObjectUpdate()
    assert u.name is None


def test_equipment_base():
    e = EquipmentBase(
        object_id=uuid4(),
        type=EquipmentType.UECN,
        serial_number="EQ-1",
    )
    assert e.manufacturer is None


# ---------- work schemas ----------


def test_work_type_base():
    w = WorkTypeBase(code="TR-1", name="Текущий ремонт", category=WorkCategory.WORKOVER)
    assert w.planned_duration_hours is None


def test_checklist_step_base_defaults():
    s = ChecklistStepBase(order_index=1, title="Шаг 1", data_type=StepDataType.BOOLEAN)
    assert s.is_required is True
    assert s.norm_json is None


def test_checklist_template_create_empty_steps():
    t = ChecklistTemplateCreate(work_type_id=uuid4())
    assert t.steps == []
    assert t.version == 1
    assert t.is_active is True


def test_checklist_template_create_with_steps():
    t = ChecklistTemplateCreate(
        work_type_id=uuid4(),
        steps=[ChecklistStepCreate(order_index=1, title="Шаг 1", data_type=StepDataType.BOOLEAN)],
    )
    assert len(t.steps) == 1


# ---------- photo schemas ----------


def test_photo_upload_request_defaults():
    r = PhotoUploadRequest(kind=PhotoKind.BEFORE)
    assert r.taken_at is None
    assert r.latitude is None


def test_photo_out():
    r = PhotoOut(
        id=uuid4(),
        act_id=uuid4(),
        kind=PhotoKind.BEFORE,
        object_key="photos/x.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        taken_at=None,
        latitude=None,
        longitude=None,
        sha256=None,
        created_at=datetime.now(UTC),
    )
    assert r.size_bytes == 1024


def test_telemetry_out():
    r = TelemetryOut(
        id=uuid4(),
        equipment_id=uuid4(),
        observed_at=datetime.now(UTC),
        params={"P": 10.0},
        source="mock",
    )
    assert r.params["P"] == 10.0
