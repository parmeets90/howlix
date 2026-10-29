from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "howlix-api"}


def test_create_list_and_retrieve_project(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/projects",
        json={"title": "Founder interview", "description": "Find the strongest hooks."},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["title"] == "Founder interview"
    assert created["status"] == "draft"

    list_response = client.get("/api/v1/projects")
    assert list_response.status_code == 200
    assert [project["id"] for project in list_response.json()] == [created["id"]]

    get_response = client.get(f"/api/v1/projects/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == created


def test_missing_project_has_consistent_error(client: TestClient) -> None:
    response = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Project not found",
            "details": None,
        }
    }


def test_blank_title_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"title": "   "})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"

