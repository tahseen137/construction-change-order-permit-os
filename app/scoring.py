from __future__ import annotations

from dataclasses import dataclass

from app.models import ChangeEvent, ChangeOrder, Permit, Project


@dataclass
class PermitHealthScore:
    score: float
    summary: str


@dataclass
class ProjectRiskRollup:
    permit_score: float
    change_score: float
    approval_score: float
    overall_score: float


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def score_permit_health(permit: Permit) -> PermitHealthScore:
    score = 100.0
    drivers: list[str] = []

    if permit.status == "revision_requested":
      score -= 28
      drivers.append("revision requested")
    if permit.current_blocker.strip():
      score -= 22
      drivers.append("active blocker")
    if permit.inspection_status == "failed":
      score -= 24
      drivers.append("failed inspection")
    if permit.revision_count:
      score -= min(permit.revision_count * 5, 15)
      drivers.append(f"{permit.revision_count} revisions")
    if permit.status == "approved":
      score += 6
      drivers.append("approved")

    if not drivers:
      drivers.append("tracking clean")

    return PermitHealthScore(score=round(_clamp(score), 1), summary=", ".join(drivers))


def score_change_event_exposure(change_event: ChangeEvent) -> float:
    score = min(change_event.cost_impact_usd / 5000, 45)
    score += min(change_event.schedule_impact_days * 2.5, 30)
    if change_event.status in {"pricing_requested", "internal_review", "owner_submitted"}:
        score += 15
    if "permit_blocker" in change_event.risk_tags:
        score += 8
    if "unpriced_exposure" in change_event.risk_tags:
        score += 8
    return round(_clamp(score), 1)


def score_change_order_confidence(change_order: ChangeOrder) -> float:
    if not change_order.approvals:
        return 25.0 if change_order.status == "draft" else 40.0

    approved = sum(1 for approval in change_order.approvals if approval.status == "approved")
    confidence = (approved / len(change_order.approvals)) * 100
    if change_order.status == "approved":
        confidence = max(confidence, 95.0)
    if change_order.status == "rejected":
        confidence = min(confidence, 15.0)
    return round(_clamp(confidence), 1)


def score_project_risk(project: Project) -> ProjectRiskRollup:
    permit_scores = [score_permit_health(permit).score for permit in project.permits] or [100.0]
    change_scores = [score_change_event_exposure(event) for event in project.change_events] or [0.0]
    approval_scores = [
        score_change_order_confidence(order)
        for event in project.change_events
        for order in event.change_orders
    ] or [100.0]

    permit_score = round(sum(permit_scores) / len(permit_scores), 1)
    change_score = round(sum(change_scores) / len(change_scores), 1)
    approval_score = round(sum(approval_scores) / len(approval_scores), 1)

    overall = round(_clamp((permit_score * 0.45) + ((100 - change_score) * 0.35) + (approval_score * 0.2)), 1)
    return ProjectRiskRollup(
        permit_score=permit_score,
        change_score=change_score,
        approval_score=approval_score,
        overall_score=overall,
    )
