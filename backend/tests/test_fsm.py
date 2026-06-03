"""Тесты FSM WorkOrderStatus и ActStatus."""
from __future__ import annotations

import pytest

from app.models.act import (
    ACT_TRANSITIONS,
    ActStatus,
    assert_act_transition,
    can_act_transition,
)
from app.models.order import (
    WORK_ORDER_TRANSITIONS,
    WorkOrderStatus,
    assert_transition,
    can_transition,
)


@pytest.mark.parametrize(
    "frm, to, allowed",
    [
        # стандартный happy path
        (WorkOrderStatus.DRAFT, WorkOrderStatus.ASSIGNED, True),
        (WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS, True),
        (WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.SUBMITTED, True),
        (WorkOrderStatus.SUBMITTED, WorkOrderStatus.AUTO_CONFIRMED, True),
        (WorkOrderStatus.SUBMITTED, WorkOrderStatus.DELAYED_VERIFICATION, True),
        (WorkOrderStatus.DELAYED_VERIFICATION, WorkOrderStatus.VERIFIED, True),
        # rework
        (WorkOrderStatus.REJECTED, WorkOrderStatus.DRAFT, True),
        (WorkOrderStatus.ISSUE_FOUND, WorkOrderStatus.ASSIGNED, True),
        # cancel из разных мест
        (WorkOrderStatus.DRAFT, WorkOrderStatus.CANCELLED, True),
        (WorkOrderStatus.ASSIGNED, WorkOrderStatus.CANCELLED, True),
        (WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED, True),
        # no-op
        (WorkOrderStatus.ASSIGNED, WorkOrderStatus.ASSIGNED, True),
        # терминальные
        (WorkOrderStatus.CONFIRMED, WorkOrderStatus.CANCELLED, False),
        (WorkOrderStatus.VERIFIED, WorkOrderStatus.CANCELLED, False),
        (WorkOrderStatus.CANCELLED, WorkOrderStatus.ASSIGNED, False),
        # прыжки
        (WorkOrderStatus.DRAFT, WorkOrderStatus.IN_PROGRESS, False),
        (WorkOrderStatus.DRAFT, WorkOrderStatus.AUTO_CONFIRMED, False),
        (WorkOrderStatus.ASSIGNED, WorkOrderStatus.AUTO_CONFIRMED, False),
        (WorkOrderStatus.SUBMITTED, WorkOrderStatus.VERIFIED, False),
        (WorkOrderStatus.DELAYED_VERIFICATION, WorkOrderStatus.CONFIRMED, False),
    ],
)
def test_can_transition(frm: WorkOrderStatus, to: WorkOrderStatus, allowed: bool) -> None:
    assert can_transition(frm, to) is allowed


def test_assert_transition_raises_on_invalid() -> None:
    with pytest.raises(ValueError, match="Недопустимый переход"):
        assert_transition(WorkOrderStatus.DRAFT, WorkOrderStatus.AUTO_CONFIRMED)


def test_assert_transition_no_op() -> None:
    # no-op не должен бросать
    assert_transition(WorkOrderStatus.ASSIGNED, WorkOrderStatus.ASSIGNED)


def test_all_statuses_have_transition_entry() -> None:
    """Каждый статус должен иметь запись в таблице (даже пустую)."""
    for s in WorkOrderStatus:
        assert s in WORK_ORDER_TRANSITIONS, f"no transitions entry for {s}"


def test_terminal_states_have_no_outgoing() -> None:
    for terminal in (WorkOrderStatus.CONFIRMED, WorkOrderStatus.VERIFIED, WorkOrderStatus.CANCELLED):
        assert WORK_ORDER_TRANSITIONS[terminal] == frozenset()


# ---------- ActStatus ----------


@pytest.mark.parametrize(
    "frm, to, allowed",
    [
        (ActStatus.DRAFT, ActStatus.SUBMITTED, True),
        (ActStatus.DRAFT, ActStatus.REJECTED, True),
        (ActStatus.SUBMITTED, ActStatus.AUTO_CONFIRMED, True),
        (ActStatus.SUBMITTED, ActStatus.DELAYED_VERIFICATION, True),
        (ActStatus.AUTO_CONFIRMED, ActStatus.CONFIRMED, True),
        (ActStatus.AUTO_CONFIRMED, ActStatus.ISSUE_FOUND, True),
        (ActStatus.DELAYED_VERIFICATION, ActStatus.VERIFIED, True),
        (ActStatus.ISSUE_FOUND, ActStatus.DRAFT, True),
        (ActStatus.REJECTED, ActStatus.DRAFT, True),
        # no-op
        (ActStatus.DRAFT, ActStatus.DRAFT, True),
        # терминальные
        (ActStatus.CONFIRMED, ActStatus.DRAFT, False),
        (ActStatus.VERIFIED, ActStatus.DRAFT, False),
        # прыжки
        (ActStatus.DRAFT, ActStatus.AUTO_CONFIRMED, False),
        (ActStatus.DRAFT, ActStatus.CONFIRMED, False),
        (ActStatus.SUBMITTED, ActStatus.VERIFIED, False),
        (ActStatus.SUBMITTED, ActStatus.CONFIRMED, False),
    ],
)
def test_can_act_transition(frm: ActStatus, to: ActStatus, allowed: bool) -> None:
    assert can_act_transition(frm, to) is allowed


def test_assert_act_transition_raises() -> None:
    with pytest.raises(ValueError, match="Недопустимый переход Act"):
        assert_act_transition(ActStatus.DRAFT, ActStatus.AUTO_CONFIRMED)


def test_act_terminal_states() -> None:
    for terminal in (ActStatus.CONFIRMED, ActStatus.VERIFIED):
        assert ACT_TRANSITIONS[terminal] == frozenset()

