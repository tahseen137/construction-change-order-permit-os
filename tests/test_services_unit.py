from __future__ import annotations

from app.permit_io import parse_permits_csv
from app.reporting import build_owner_change_order_markdown
from app.scoring import score_change_order_confidence, score_permit_health, score_project_risk
from app.services import create_change_order, create_permit, create_project, create_quote
from app.schemas import ChangeOrderCreate, PermitCreate, ProjectCreate, QuoteCreate


def test_parse_permits_csv_reports_blank_rows_and_payloads():
    permits, errors, skipped_blank_rows = parse_permits_csv(
        "name,jurisdiction,status,current_blocker\n"
        "Building Permit,City of Austin,submitted,\n"
        "\n"
        "Fire Permit,City of Austin,revision_requested,Need updated fire alarm details\n"
    )

    assert errors == []
    assert skipped_blank_rows == 1
    assert len(permits) == 2
    assert permits[1].status == "revision_requested"


def test_scoring_and_reporting_roll_up(session, workspace):
    project = create_project(
        session,
        workspace,
        ProjectCreate(
            name="South Austin Retail",
            project_code="SAR-2",
            client_name="Retail Ventures",
            location="Austin, TX",
            sector="retail",
            status="active",
            contract_value_usd=9200000,
            target_margin_pct=11,
            notes="Retail shell and tenant fit-out.",
        ),
    )
    permit = create_permit(
        session,
        project,
        PermitCreate(
          name="Building Permit",
          jurisdiction="City of Austin",
          package_name="Shell",
          permit_number="BP-1",
          responsible_owner="PM",
          status="revision_requested",
          submission_due_date=None,
          submitted_at=None,
          approved_at=None,
          revision_requested_at=None,
          inspection_due_date=None,
          expiration_date=None,
          revision_count=2,
          inspection_status="failed",
          current_blocker="Resubmit life-safety details",
          notes="Plan check round two",
          dependencies=[],
          inspections=[],
        ),
    )
    change_event = permit.linked_change_event
    assert change_event is not None
    change_event.cost_impact_usd = 28000
    change_event.schedule_impact_days = 9
    change_event.risk_tags = ["permit_blocker", "schedule_risk"]
    change_event.summary = "Need to resubmit life-safety details."
    change_event.notes = "Pending revised drawings."
    session.add(change_event)
    session.commit()
    create_quote(
        session,
        change_event,
        QuoteCreate(
            subcontractor_name="MEP Systems",
            amount_usd=28500,
            quoted_at=None,
            inclusions="Revised life-safety sheets",
            exclusions="Permit fees",
            is_selected=True,
            notes="Selected",
        ),
    )
    change_order = create_change_order(
        session,
        change_event,
        ChangeOrderCreate(
            kind="owner",
            number="PCO-100",
            title="Life-safety resubmittal",
            amount_usd=28500,
            schedule_impact_days=9,
            description="Resubmittal package after code comments.",
        ),
    )

    permit_score = score_permit_health(permit)
    project_score = score_project_risk(project)
    confidence = score_change_order_confidence(change_order)
    markdown = build_owner_change_order_markdown(project, change_event, change_order)

    assert permit_score.score < 70
    assert project_score.overall_score < 100
    assert confidence == 25.0
    assert "Owner Change Order Package" in markdown
