from __future__ import annotations

import csv
import io
from datetime import date

from app.schemas import PermitCreate


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value.strip())


def permit_template_csv() -> str:
    rows = [
        [
            "name",
            "jurisdiction",
            "package_name",
            "permit_number",
            "responsible_owner",
            "status",
            "submission_due_date",
            "submitted_at",
            "approved_at",
            "revision_requested_at",
            "inspection_due_date",
            "expiration_date",
            "revision_count",
            "inspection_status",
            "current_blocker",
            "notes",
        ],
        [
            "Building Permit",
            "City of Austin",
            "Core and Shell",
            "BP-2026-0142",
            "Project Engineer",
            "submitted",
            "2026-04-15",
            "2026-04-09",
            "",
            "",
            "2026-05-02",
            "2027-04-09",
            "0",
            "scheduled",
            "",
            "Awaiting first inspection.",
        ],
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue()


def change_event_template_csv() -> str:
    rows = [
        [
            "title",
            "source_type",
            "affected_scope",
            "subcontractor_name",
            "owner_reference",
            "cost_impact_usd",
            "schedule_impact_days",
            "required_action_date",
            "summary",
        ],
        [
            "Lobby glazing scope gap",
            "owner_request",
            "Exterior glazing",
            "Skyline Glass",
            "ASI-014",
            "18500",
            "4",
            "2026-04-12",
            "Owner requested upgraded laminated glass package after permit submission.",
        ],
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue()


def parse_permits_csv(csv_content: str) -> tuple[list[PermitCreate], list[str], int]:
    raw_lines = csv_content.splitlines()
    if not raw_lines:
        raise ValueError("CSV file is missing a header row.")

    filtered_lines = [raw_lines[0]]
    skipped_blank_rows = 0
    for line in raw_lines[1:]:
        if line.strip():
            filtered_lines.append(line)
        else:
            skipped_blank_rows += 1

    reader = csv.DictReader(io.StringIO("\n".join(filtered_lines)))
    required = {"name", "jurisdiction"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

    permits: list[PermitCreate] = []
    errors: list[str] = []

    for row_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            skipped_blank_rows += 1
            continue
        try:
            payload = PermitCreate(
                name=(row.get("name") or "").strip(),
                jurisdiction=(row.get("jurisdiction") or "").strip(),
                package_name=(row.get("package_name") or "").strip(),
                permit_number=(row.get("permit_number") or "").strip(),
                responsible_owner=(row.get("responsible_owner") or "").strip(),
                status=((row.get("status") or "draft").strip() or "draft"),
                submission_due_date=_parse_date(row.get("submission_due_date")),
                submitted_at=_parse_date(row.get("submitted_at")),
                approved_at=_parse_date(row.get("approved_at")),
                revision_requested_at=_parse_date(row.get("revision_requested_at")),
                inspection_due_date=_parse_date(row.get("inspection_due_date")),
                expiration_date=_parse_date(row.get("expiration_date")),
                revision_count=int((row.get("revision_count") or "0").strip() or 0),
                inspection_status=((row.get("inspection_status") or "not_scheduled").strip() or "not_scheduled"),
                current_blocker=(row.get("current_blocker") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
            permits.append(payload)
        except Exception as exc:
            errors.append(f"Row {row_number}: {exc}")

    return permits, errors, skipped_blank_rows
