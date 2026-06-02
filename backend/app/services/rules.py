"""Rule engine: автоподтверждение акта.

В прототипе — простые правила:
- Все обязательные пункты чек-листа заполнены и passed=True
- Гео-проверка пройдена (если есть координаты объекта)
- Телеметрия equipment после работ в допустимом диапазоне (если есть нормы)
- Фото "до" и "после" приложены

Итог: passed (bool) + score (0..1) + details (dict для UI).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.act import Act, ActStatus, ChecklistResponse
from app.models.photo import Photo, PhotoKind
from app.models.work import ChecklistStep, StepDataType
from app.services.geo import check_geo

log = get_logger(__name__)


@dataclass
class AutoCheckResult:
    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)
    failed_rules: list[str] = field(default_factory=list)


async def auto_check_act(session: AsyncSession, act: Act) -> AutoCheckResult:
    failed: list[str] = []
    details: dict[str, Any] = {}
    weights: list[tuple[float, bool, str]] = []  # (weight, passed, rule_name)

    # 1) Чек-лист: все обязательные ответы passed
    steps = (
        await session.scalars(
            select(ChecklistStep)
            .join(ChecklistResponse, ChecklistResponse.step_id == ChecklistStep.id)
            .where(ChecklistResponse.act_id == act.id)
        )
    ).all()

    if not steps:
        return AutoCheckResult(
            passed=False, score=0.0, failed_rules=["checklist_empty"]
        )

    required_steps = [s for s in steps if s.is_required]
    if not required_steps:
        failed.append("no_required_steps")

    responses_map: dict[UUID, ChecklistResponse] = {
        r.step_id: r
        for r in (
            await session.scalars(
                select(ChecklistResponse).where(ChecklistResponse.act_id == act.id)
            )
        ).all()
    }

    steps_passed = 0
    numeric_checks = []
    for step in steps:
        resp = responses_map.get(step.id)
        if not resp:
            if step.is_required:
                failed.append(f"step_missing:{step.title}")
                weights.append((0.05, False, f"step:{step.title}"))
            continue

        ok = resp.passed
        # Доп. проверка для numeric с нормой
        if step.data_type == StepDataType.NUMERIC and resp.value_numeric is not None and step.norm_json:
            norm = step.norm_json
            nominal = norm.get("nominal")
            tol = norm.get("tolerance")
            if nominal is not None and tol is not None:
                dev = float(resp.value_numeric) - float(nominal)
                in_range = abs(dev) <= float(tol)
                ok = (ok is None or ok) and in_range
                numeric_checks.append(
                    {
                        "step": step.title,
                        "value": float(resp.value_numeric),
                        "nominal": float(nominal),
                        "tolerance": float(tol),
                        "deviation": dev,
                        "passed": in_range,
                    }
                )

        steps_passed += int(bool(ok))
        if step.is_required:
            weights.append((0.10, bool(ok), f"step:{step.title}"))

    details["checklist"] = {
        "total": len(steps),
        "passed": steps_passed,
        "numeric_checks": numeric_checks,
    }

    # 2) Гео-проверка
    from app.models.object import Object  # локальный импорт чтобы избежать цикла
    obj = await session.scalar(select(Object).where(Object.id == act.work_order.object_id))
    if obj and obj.latitude and obj.longitude and act.actual_latitude and act.actual_longitude:
        geo = check_geo(
            float(obj.latitude), float(obj.longitude),
            float(act.actual_latitude), float(act.actual_longitude),
            settings.geo_radius_m,
        )
        if geo is not None:
            details["geo"] = {
                "distance_m": round(geo.distance_m, 1),
                "radius_m": settings.geo_radius_m,
                "in_radius": geo.in_radius,
            }
            weights.append((0.25, geo.in_radius, "geo"))

    # 3) Фото: должны быть до и после
    photos = (
        await session.scalars(select(Photo).where(Photo.act_id == act.id))
    ).all()
    has_before = any(p.kind == PhotoKind.BEFORE for p in photos)
    has_after = any(p.kind == PhotoKind.AFTER for p in photos)
    details["photos"] = {
        "before": has_before, "after": has_after, "total": len(photos),
    }
    weights.append((0.15, has_before, "photo_before"))
    weights.append((0.15, has_after, "photo_after"))

    # 4) Телеметрия: если есть «после» и известны нормативы — проверим
    if act.telemetry_after_json and act.telemetry_before_json:
        # Простая эвристика: ключевые параметры equipment изменились
        # (потом заменим на rule per parameter)
        changed = [
            k for k in act.telemetry_after_json
            if act.telemetry_after_json.get(k) != act.telemetry_before_json.get(k)
        ]
        details["telemetry"] = {
            "params_changed": changed,
            "before": act.telemetry_before_json,
            "after": act.telemetry_after_json,
        }
        weights.append((0.20, bool(changed), "telemetry_changed"))

    # Итоговый score
    total_w = sum(w for w, _, _ in weights) or 1.0
    passed_w = sum(w for w, p, _ in weights if p)
    score = passed_w / total_w
    passed = score >= 0.8 and not failed

    log.info("auto_check", act_id=str(act.id), score=score, passed=passed, failed=failed)

    return AutoCheckResult(
        passed=passed, score=round(score, 4), details=details, failed_rules=failed
    )
