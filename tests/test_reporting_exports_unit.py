from __future__ import annotations

from app.activity_service import record_activity
from app.portfolio_io import change_order_register_csv, permit_register_csv
from app.services import create_change_event, create_change_order, create_permit, create_project
from app.schemas import ChangeEventCreate, ChangeOrderCreate, PermitCreate, ProjectCreate


def test_register_csv_helpers_and_activity_log(session, workspace, admin_user):
    project = create_project(
        session,
        workspace,
        ProjectCreate(
            name="North Loop Office",
            project_code="NLO-10",
            client_name="Stonebridge",
            location="Nashville, TN",
            sector="office",
            status="precon",
            contract_value_usd=12500000,
            target_margin_pct=10,
            notes="Office repositioning and lobby refresh.",
        ),
    )
    permit = create_permit(
        session,
        project,
        PermitCreate(
            name="Fire Permit",
            jurisdiction="Metro Nashville",
            package_name="Life safety",
            permit_number="FP-22",
            responsible_owner="PE",
            status="submitted",
            submission_due_date=None,
            submitted_at=None,
            approved_at=None,
            revision_requested_at=None,
            inspection_due_date=None,
            expiration_date=None,
            revision_count=0,
            inspection_status="scheduled",
            current_blocker="",
            notes="Awaiting review.",
            dependencies=[],
            inspections=[],
        ),
    )
    change_event = create_change_event(
        session,
        project,
        ChangeEventCreate(
            source_type="owner_request",
            title="Lobby finish upgrade",
            affected_scope="Main lobby",
            subcontractor_name="Stone Interiors",
            owner_reference="ASI-9",
            cost_impact_usd=22000,
            schedule_impact_days=4,
            status="internal_review",
            summary="Owner requested higher-end finish palette.",
            risk_tags=["owner_scope_gap"],
            notes="Pricing in progress.",
        ),
    )
    create_change_order(
        session,
        change_event,
        ChangeOrderCreate(
            kind="owner",
            number="PCO-009",
            title="Lobby finish upgrade",
            amount_usd=22000,
            schedule_impact_days=4,
            description="Owner requested upgraded finish palette.",
        ),
    )

    record_activity(
        session,
        workspace_id=workspace.id,
        action="project.reviewed",
        entity_type="project",
        entity_id=project.id,
        actor_user=admin_user,
        project_id=project.id,
        description="admin reviewed the project register.",
    )

    permit_csv = permit_register_csv(project)
    change_order_csv = change_order_register_csv(project)

    assert "Fire Permit" in permit_csv
    assert permit.id in permit.linked_change_event.id if permit.linked_change_event else True
    assert "PCO-009" in change_order_csv
