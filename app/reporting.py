from __future__ import annotations

from app.models import ChangeEvent, ChangeOrder, Project


def build_owner_change_order_markdown(project: Project, change_event: ChangeEvent, change_order: ChangeOrder) -> str:
    approvals = "\n".join(
        [
            f"- Step {step.step_order}: {step.role_required} -> {step.status}"
            for step in change_order.approvals
        ]
    ) or "- No approvals routed yet"

    risk_tags = ", ".join(change_event.risk_tags) or "none"

    return f"""# Owner Change Order Package

## Project

- Name: {project.name}
- Code: {project.project_code}
- Client: {project.client_name}
- Location: {project.location}

## Change Event

- Title: {change_event.title}
- Source: {change_event.source_type}
- Scope: {change_event.affected_scope or 'Not provided'}
- Subcontractor: {change_event.subcontractor_name or 'Unassigned'}
- Cost impact: ${change_event.cost_impact_usd:,.2f}
- Schedule impact: {change_event.schedule_impact_days} days
- Risk tags: {risk_tags}

## Change Order

- Number: {change_order.number}
- Kind: {change_order.kind}
- Status: {change_order.status}
- Amount: ${change_order.amount_usd:,.2f}
- Schedule impact: {change_order.schedule_impact_days} days

## Description

{change_order.description or change_event.summary or 'No additional description provided.'}

## Required Approvals

{approvals}

## Notes

This package is generated for owner-facing review and internal tracking. Validate final contract language, pricing back-up, and schedule narrative before external submission.
"""
