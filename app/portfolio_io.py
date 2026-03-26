from __future__ import annotations

import csv
from io import StringIO

from app.models import Project


def permit_register_csv(project: Project) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "permit_name",
            "jurisdiction",
            "status",
            "inspection_status",
            "submission_due_date",
            "inspection_due_date",
            "current_blocker",
            "linked_change_event_id",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for permit in project.permits:
        writer.writerow(
            {
                "permit_name": permit.name,
                "jurisdiction": permit.jurisdiction,
                "status": permit.status,
                "inspection_status": permit.inspection_status,
                "submission_due_date": permit.submission_due_date.isoformat() if permit.submission_due_date else "",
                "inspection_due_date": permit.inspection_due_date.isoformat() if permit.inspection_due_date else "",
                "current_blocker": permit.current_blocker,
                "linked_change_event_id": permit.linked_change_event.id if permit.linked_change_event else "",
            }
        )
    return buffer.getvalue()


def change_order_register_csv(project: Project) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "change_event_title",
            "change_order_number",
            "kind",
            "status",
            "amount_usd",
            "schedule_impact_days",
            "submitted_at",
            "approved_at",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for change_event in project.change_events:
        for change_order in change_event.change_orders:
            writer.writerow(
                {
                    "change_event_title": change_event.title,
                    "change_order_number": change_order.number,
                    "kind": change_order.kind,
                    "status": change_order.status,
                    "amount_usd": f"{change_order.amount_usd:.2f}",
                    "schedule_impact_days": change_order.schedule_impact_days,
                    "submitted_at": change_order.submitted_at.isoformat() if change_order.submitted_at else "",
                    "approved_at": change_order.approved_at.isoformat() if change_order.approved_at else "",
                }
            )
    return buffer.getvalue()
