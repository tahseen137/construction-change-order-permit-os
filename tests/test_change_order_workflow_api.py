from __future__ import annotations

from fastapi.testclient import TestClient


def test_full_change_order_approval_chain(
    auth_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project: dict[str, object],
):
    change_event_response = auth_client.post(
        f"/api/projects/{seeded_project['id']}/change-events",
        headers=auth_headers,
        json={
            "source_type": "owner_request",
            "title": "Owner adds upgraded facade package",
            "affected_scope": "Envelope",
            "subcontractor_name": "Skyline Glass",
            "owner_reference": "ASI-014",
            "cost_impact_usd": 185000,
            "schedule_impact_days": 11,
            "status": "internal_review",
            "summary": "Owner requested laminated facade upgrade after permit submission.",
            "risk_tags": ["owner_scope_gap", "unpriced_exposure"],
            "notes": "Need pricing and approval.",
        },
    )
    assert change_event_response.status_code == 201, change_event_response.text
    change_event = change_event_response.json()

    rfq_response = auth_client.post(
        f"/api/change-events/{change_event['id']}/rfqs",
        headers=auth_headers,
        json={
            "subcontractor_name": "Skyline Glass",
            "scope_summary": "Price the revised laminated facade package.",
            "status": "sent",
            "due_at": "2026-04-20",
            "notes": "Urgent turnaround requested.",
        },
    )
    assert rfq_response.status_code == 201

    quote_response = auth_client.post(
        f"/api/change-events/{change_event['id']}/quotes",
        headers=auth_headers,
        json={
            "subcontractor_name": "Skyline Glass",
            "amount_usd": 187500,
            "quoted_at": "2026-04-18",
            "inclusions": "Material, freight, install labor",
            "exclusions": "Night shift premium",
            "is_selected": True,
            "notes": "Best value quote.",
        },
    )
    assert quote_response.status_code == 201
    assert quote_response.json()["is_selected"] is True

    change_order_response = auth_client.post(
        f"/api/change-events/{change_event['id']}/change-orders",
        headers=auth_headers,
        json={
            "kind": "owner",
            "number": "PCO-014",
            "title": "Facade laminate upgrade",
            "amount_usd": 187500,
            "schedule_impact_days": 11,
            "description": "Owner-directed facade laminate upgrade after permit submission.",
        },
    )
    assert change_order_response.status_code == 201, change_order_response.text
    change_order = change_order_response.json()

    submit_response = auth_client.post(
        f"/api/change-orders/{change_order['id']}/submit-approval",
        headers=auth_headers,
    )
    assert submit_response.status_code == 200, submit_response.text
    submitted = submit_response.json()
    assert submitted["status"] == "pending_approval"
    assert len(submitted["approvals"]) == 3

    for approval_step in submitted["approvals"]:
        approve_response = auth_client.post(
            f"/api/change-orders/{change_order['id']}/approval-steps/{approval_step['id']}/decision",
            headers=auth_headers,
            json={"status": "approved", "decision_notes": "Looks good."},
        )
        assert approve_response.status_code == 200, approve_response.text

    detail_response = auth_client.get(f"/api/projects/{seeded_project['id']}")
    project = detail_response.json()
    approved_order = project["change_events"][0]["change_orders"][0]
    assert approved_order["status"] == "approved"

    package_response = auth_client.get(f"/api/change-orders/{change_order['id']}/package.md")
    assert package_response.status_code == 200
    assert "Owner Change Order Package" in package_response.json()["markdown"]
