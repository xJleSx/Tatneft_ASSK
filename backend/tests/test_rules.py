"""Тесты app/services/rules.py (auto_check_act)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.rules import auto_check_act


def make_act(
    act_id=None,
    actual_latitude=None,
    actual_longitude=None,
    telemetry_before=None,
    telemetry_after=None,
    work_order_obj=None,
):
    return SimpleNamespace(
        id=act_id or uuid4(),
        work_order_id=uuid4(),
        actual_latitude=actual_latitude,
        actual_longitude=actual_longitude,
        telemetry_before_json=telemetry_before,
        telemetry_after_json=telemetry_after,
        work_order=work_order_obj,
    )


def make_step(step_id, is_required=True, data_type=None, norm_json=None, title="Step"):
    return SimpleNamespace(
        id=step_id,
        is_required=is_required,
        data_type=data_type,
        norm_json=norm_json,
        title=title,
    )


def make_response(step_id, passed=True, value_numeric=None):
    return SimpleNamespace(
        step_id=step_id,
        passed=passed,
        value_numeric=value_numeric,
    )


def make_session_for_steps(steps, responses, object_row=None, wo_row=None, photos=None):
    """Создать AsyncMock session для auto_check_act."""
    session = AsyncMock()
    call_n = {"n": 0}

    async def scalars_side_effect(*args, **kwargs):
        m = MagicMock()
        if call_n["n"] == 0:
            m.all.return_value = steps
        elif call_n["n"] == 1:
            m.all.return_value = responses
        elif call_n["n"] == 2:
            m.all.return_value = photos or []
        else:
            m.all.return_value = []
        call_n["n"] += 1
        return m

    session.scalars = AsyncMock(side_effect=scalars_side_effect)
    session.scalar = AsyncMock(return_value=object_row)
    default_wo = SimpleNamespace(object_id=uuid4())
    session.get = AsyncMock(return_value=wo_row or default_wo)
    return session


@pytest.mark.asyncio
async def test_auto_check_checklist_empty():
    act = make_act()
    session = make_session_for_steps(steps=[], responses=[])
    result = await auto_check_act(session, act)
    assert result.passed is False
    assert result.score == 0.0
    assert "checklist_empty" in result.failed_rules


@pytest.mark.asyncio
async def test_auto_check_all_passed_no_geo_no_photos():
    step1 = make_step(uuid4(), is_required=True, data_type=None, title="S1")
    step2 = make_step(uuid4(), is_required=True, data_type=None, title="S2")
    responses = [
        make_response(step1.id, passed=True),
        make_response(step2.id, passed=True),
    ]
    act = make_act(actual_latitude=None, actual_longitude=None)
    session = make_session_for_steps([step1, step2], responses, photos=[])
    result = await auto_check_act(session, act)
    # Без фото скор ниже 1.0
    assert result.score < 1.0
    assert result.passed is False  # photo rules тянут вниз


@pytest.mark.asyncio
async def test_auto_check_required_step_missing_response():
    step1 = make_step(uuid4(), is_required=True, title="Required")
    responses = []  # no response for required step
    act = make_act()
    session = make_session_for_steps([step1], responses)
    result = await auto_check_act(session, act)
    assert "step_missing:Required" in result.failed_rules
    assert result.passed is False


@pytest.mark.asyncio
async def test_auto_check_numeric_within_norm():
    from app.models.work import StepDataType

    step = make_step(
        uuid4(),
        is_required=True,
        data_type=StepDataType.NUMERIC,
        norm_json={"nominal": 50, "tolerance": 5},
        title="Pressure",
    )
    response = make_response(step.id, passed=True, value_numeric=52.0)
    act = make_act()
    session = make_session_for_steps([step], [response])
    result = await auto_check_act(session, act)
    assert result.details["checklist"]["numeric_checks"][0]["passed"] is True
    assert result.details["checklist"]["numeric_checks"][0]["value"] == 52.0


@pytest.mark.asyncio
async def test_auto_check_numeric_out_of_norm():
    from app.models.work import StepDataType

    step = make_step(
        uuid4(),
        is_required=True,
        data_type=StepDataType.NUMERIC,
        norm_json={"nominal": 50, "tolerance": 5},
        title="Pressure",
    )
    response = make_response(step.id, passed=True, value_numeric=100.0)  # far off
    act = make_act()
    session = make_session_for_steps([step], [response])
    result = await auto_check_act(session, act)
    assert result.passed is False
    assert result.details["checklist"]["numeric_checks"][0]["passed"] is False


@pytest.mark.asyncio
async def test_auto_check_numeric_norm_missing_nominal():
    from app.models.work import StepDataType

    step = make_step(
        uuid4(),
        is_required=True,
        data_type=StepDataType.NUMERIC,
        norm_json={"tolerance": 5},  # no nominal
        title="X",
    )
    response = make_response(step.id, passed=True, value_numeric=50.0)
    act = make_act()
    session = make_session_for_steps([step], [response])
    result = await auto_check_act(session, act)
    # numeric_checks пуст — проверка не применена
    assert result.details["checklist"]["numeric_checks"] == []


@pytest.mark.asyncio
async def test_auto_check_geo_passed():
    from decimal import Decimal

    from app.models.photo import PhotoKind
    from app.models.work import StepDataType

    step = make_step(uuid4(), is_required=True, data_type=StepDataType.BOOLEAN, title="S")
    responses = [make_response(step.id, passed=True)]
    obj = SimpleNamespace(latitude=Decimal("55.0"), longitude=Decimal("50.0"))
    wo = SimpleNamespace(object_id=uuid4())
    photos = [
        SimpleNamespace(kind=PhotoKind.BEFORE),
        SimpleNamespace(kind=PhotoKind.AFTER),
    ]
    act = make_act(
        actual_latitude=Decimal("55.0"), actual_longitude=Decimal("50.0"), work_order_obj=wo
    )
    session = make_session_for_steps([step], responses, object_row=obj, photos=photos)
    result = await auto_check_act(session, act)
    assert result.details.get("geo", {}).get("in_radius") is True
    assert result.passed is True


@pytest.mark.asyncio
async def test_auto_check_geo_failed():
    from decimal import Decimal

    from app.models.photo import PhotoKind
    from app.models.work import StepDataType

    step = make_step(uuid4(), is_required=True, data_type=StepDataType.BOOLEAN, title="S")
    responses = [make_response(step.id, passed=True)]
    obj = SimpleNamespace(latitude=Decimal("55.0"), longitude=Decimal("50.0"))
    wo = SimpleNamespace(object_id=uuid4())
    photos = [SimpleNamespace(kind=PhotoKind.BEFORE), SimpleNamespace(kind=PhotoKind.AFTER)]
    act = make_act(
        actual_latitude=Decimal("60.0"), actual_longitude=Decimal("50.0"), work_order_obj=wo
    )
    session = make_session_for_steps([step], responses, object_row=obj, photos=photos)
    result = await auto_check_act(session, act)
    assert result.details.get("geo", {}).get("in_radius") is False


@pytest.mark.asyncio
async def test_auto_check_photos_before_and_after():
    from app.models.photo import PhotoKind
    from app.models.work import StepDataType

    step = make_step(uuid4(), is_required=True, data_type=StepDataType.BOOLEAN, title="S")
    responses = [make_response(step.id, passed=True)]
    photos = [
        SimpleNamespace(kind=PhotoKind.BEFORE),
        SimpleNamespace(kind=PhotoKind.AFTER),
    ]
    act = make_act()
    session = make_session_for_steps([step], responses, photos=photos)
    result = await auto_check_act(session, act)
    assert result.details["photos"]["before"] is True
    assert result.details["photos"]["after"] is True


@pytest.mark.asyncio
async def test_auto_check_photos_only_before():
    from app.models.photo import PhotoKind
    from app.models.work import StepDataType

    step = make_step(uuid4(), is_required=True, data_type=StepDataType.BOOLEAN, title="S")
    responses = [make_response(step.id, passed=True)]
    photos = [SimpleNamespace(kind=PhotoKind.BEFORE)]
    act = make_act()
    session = make_session_for_steps([step], responses, photos=photos)
    result = await auto_check_act(session, act)
    assert result.details["photos"]["before"] is True
    assert result.details["photos"]["after"] is False


@pytest.mark.asyncio
async def test_auto_check_telemetry_changed():
    from app.models.work import StepDataType

    step = make_step(uuid4(), is_required=True, data_type=StepDataType.BOOLEAN, title="S")
    responses = [make_response(step.id, passed=True)]
    act = make_act(
        telemetry_before={"Q_liq": 100},
        telemetry_after={"Q_liq": 120},
    )
    session = make_session_for_steps([step], responses, photos=[])
    result = await auto_check_act(session, act)
    assert "Q_liq" in result.details["telemetry"]["params_changed"]


@pytest.mark.asyncio
async def test_auto_check_telemetry_unchanged():
    from app.models.work import StepDataType

    step = make_step(uuid4(), is_required=True, data_type=StepDataType.BOOLEAN, title="S")
    responses = [make_response(step.id, passed=True)]
    act = make_act(
        telemetry_before={"Q_liq": 100},
        telemetry_after={"Q_liq": 100},
    )
    session = make_session_for_steps([step], responses, photos=[])
    result = await auto_check_act(session, act)
    assert result.details["telemetry"]["params_changed"] == []


@pytest.mark.asyncio
async def test_auto_check_no_required_steps():
    step = make_step(uuid4(), is_required=False, title="Optional")
    responses = [make_response(step.id, passed=True)]
    act = make_act()
    session = make_session_for_steps([step], responses)
    result = await auto_check_act(session, act)
    assert "no_required_steps" in result.failed_rules


@pytest.mark.asyncio
async def test_auto_check_uses_passed_work_order_arg():
    """Если передан work_order явно, не идёт в session.get."""
    from decimal import Decimal

    from app.models.photo import PhotoKind
    from app.models.work import StepDataType

    step = make_step(uuid4(), is_required=True, data_type=StepDataType.BOOLEAN, title="S")
    responses = [make_response(step.id, passed=True)]
    wo = SimpleNamespace(object_id=uuid4())
    obj = SimpleNamespace(latitude=Decimal("55.0"), longitude=Decimal("50.0"))
    photos = [SimpleNamespace(kind=PhotoKind.BEFORE), SimpleNamespace(kind=PhotoKind.AFTER)]
    session = make_session_for_steps([step], responses, object_row=obj, photos=photos)
    act = make_act(actual_latitude=Decimal("55.0"), actual_longitude=Decimal("50.0"))

    result = await auto_check_act(session, act, work_order=wo)
    assert result.passed is True
