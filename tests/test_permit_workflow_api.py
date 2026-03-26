from __future__ import annotations

from fastapi.testclient import TestClient


def test_permit_create_import_and_linked_change_event(
    auth_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project: dict[str, object],
):
    permit_response = auth_client.post(
        f"/api/projects/{seeded_project['id']}/permits",
        headers=auth_headers,
        json={
            "name": "Building Permit",
            "jurisdiction": "City of Austin",
            "package_name": "Core and shell",
            "permit_number": "BP-102",
            "responsible_owner": "Project engineer",
            "status": "revision_requested",
            "submission_due_date": "2026-04-12",
            "inspection_due_date": "2026-04-22",
            "revision_count": 1,
            "inspection_status": "scheduled",
            "current_blocker": "Plan check comments require resubmittal.",
            "notes": "Revision letter received.",
            "dependencies": [],
            "inspections": [],
        },
    )
    assert permit_response.status_code == 201, permit_response.text
    permit = permit_response.json()
    assert permit["linked_change_event_id"] is not None

    project_response = auth_client.get(f"/api/projects/{seeded_project['id']}")
    assert project_response.status_code == 200
    project = project_response.json()
    assert len(project["change_events"]) == 1
    assert project["change_events"][0]["source_type"] == "permit_issue"

    import_response = auth_client.post(
        "/api/permits/import",
        headers=auth_headers,
        json={
            "project_id": seeded_project["id"],
            "csv_content": (
                "name,jurisdiction,package_name,permit_number,status,current_blocker\n"
                "Fire Permit,City of Austin,Mobility,FP-55,submitted,\n"
                "Sign Permit,City of Austin,Exterior,SP-8,revision_requested,Need revised elevations\n"
            ),
        },
    )
    assert import_response.status_code == 201, import_response.text
    payload = import_response.json()
    assert payload["created_count"] == 2

    dashboard_response = auth_client.get("/api/dashboard")
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["permits_at_risk"] >= 2


def test_document_upload_and_download_updates_linked_change_event(
    auth_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project: dict[str, object],
):
    permit_response = auth_client.post(
        f"/api/projects/{seeded_project['id']}/permits",
        headers=auth_headers,
        json={
            "name": "Mechanical Permit",
            "jurisdiction": "City of Austin",
            "package_name": "MEP",
            "permit_number": "MP-9",
            "responsible_owner": "Project engineer",
            "status": "revision_requested",
            "submission_due_date": "2026-05-01",
            "inspection_due_date": "2026-05-08",
            "revision_count": 1,
            "inspection_status": "scheduled",
            "current_blocker": "Revision comments pending response.",
            "notes": "",
            "dependencies": [],
            "inspections": [],
        },
    )
    permit = permit_response.json()

    upload_response = auth_client.post(
        f"/api/permits/{permit['id']}/documents",
        headers=auth_headers,
        files={
            "file": (
                "revision-letter.txt",
                b"Permit number MP-9\nOwner request added scope.\nDelay is 14 calendar day.\nBudget impact $18500.\n",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201, upload_response.text
    document = upload_response.json()
    assert document["extraction_confidence"] > 0.5
    assert document["extracted_fields"]["schedule_impact_days"] == 14

    download_response = auth_client.get(f"/api/documents/{document['id']}/download")
    assert download_response.status_code == 200
    assert b"Budget impact" in download_response.content

    project_response = auth_client.get(f"/api/projects/{seeded_project['id']}")
    change_event = project_response.json()["change_events"][0]
    assert change_event["schedule_impact_days"] == 14
    assert change_event["cost_impact_usd"] == 18500
