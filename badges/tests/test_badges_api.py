import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# ── Shared fake data ──────────────────────────────────────────────────────────

BADGE_1 = {
    "badge_id": 1,
    "title": "First Review",
    "milestone": 10,
    "description": "Awarded after 10 reviews",
}

BADGE_2 = {
    "badge_id": 2,
    "title": "Top Reviewer",
    "milestone": 50,
    "description": None,
}

USER_BADGE = {
    "badge_id": 1,
    "user_id": "42",
    "awarded_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "badge": BADGE_1,
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_grpc_client():
    """Mock for BadgeGrpcClient — controls all badge CRUD responses."""
    client = AsyncMock()
    client.list_badges = AsyncMock(return_value=[BADGE_1, BADGE_2])
    client.get_badge = AsyncMock(return_value=BADGE_1)
    client.create_badge = AsyncMock(return_value=BADGE_1)
    client.update_badge = AsyncMock(return_value={**BADGE_1, "title": "Updated"})
    client.delete_badge = AsyncMock(return_value=True)
    client.get_user_badges = AsyncMock(return_value=[USER_BADGE])
    client.award_badge = AsyncMock(return_value=USER_BADGE)
    return client


@pytest.fixture
def mock_user_client():
    """Mock for UserGrpcClient — used to validate user existence."""
    client = AsyncMock()
    client.validate_user = AsyncMock(return_value=True)
    client.start = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def test_client(mock_grpc_client, mock_user_client):
    """
    Builds a TestClient with both gRPC clients patched.
    The lifespan (start/close) is also mocked so no real connections are made.
    """
    with patch("badges.grpc_client", mock_grpc_client), \
         patch("badges.user_client", mock_user_client):

        from badges import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, mock_grpc_client, mock_user_client


# ── Badge definition routes ───────────────────────────────────────────────────

class TestListBadges:
    def test_returns_all_badges(self, test_client):
        client, grpc, _ = test_client
        response = client.get("/badges")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["badge_id"] == 1
        assert data[1]["badge_id"] == 2

    def test_calls_grpc_list_badges(self, test_client):
        client, grpc, _ = test_client
        client.get("/badges")
        grpc.list_badges.assert_called_once()


class TestGetBadge:
    def test_returns_badge(self, test_client):
        client, grpc, _ = test_client
        response = client.get("/badges/1")
        assert response.status_code == 200
        assert response.json()["badge_id"] == 1
        assert response.json()["title"] == "First Review"

    def test_invalid_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.get("/badges/0")  # ge=1 constraint
        assert response.status_code == 422


class TestCreateBadge:
    def test_creates_badge(self, test_client):
        client, grpc, _ = test_client
        payload = {"title": "First Review", "milestone": 10, "description": "Awarded after 10 reviews"}
        response = client.post("/badges", json=payload)
        assert response.status_code == 201
        assert response.json()["title"] == "First Review"

    def test_missing_title_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/badges", json={"milestone": 10})
        assert response.status_code == 422

    def test_missing_milestone_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/badges", json={"title": "First Review"})
        assert response.status_code == 422

    def test_calls_grpc_with_correct_args(self, test_client):
        client, grpc, _ = test_client
        payload = {"title": "First Review", "milestone": 10, "description": "desc"}
        client.post("/badges", json=payload)
        grpc.create_badge.assert_called_once_with(
            title="First Review", milestone=10, description="desc"
        )


class TestUpdateBadge:
    def test_updates_badge(self, test_client):
        client, grpc, _ = test_client
        response = client.put("/badges/1", json={"title": "Updated"})
        assert response.status_code == 200
        assert response.json()["title"] == "Updated"

    def test_invalid_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.put("/badges/0", json={"title": "X"})
        assert response.status_code == 422


class TestDeleteBadge:
    def test_deletes_badge(self, test_client):
        client, grpc, _ = test_client
        response = client.delete("/badges/1")
        assert response.status_code == 204

    def test_invalid_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.delete("/badges/0")
        assert response.status_code == 422


# ── User badge routes ─────────────────────────────────────────────────────────

class TestGetUserBadges:
    def test_returns_user_badges(self, test_client):
        client, grpc, _ = test_client
        response = client.get("/users/42/badges")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["user_id"] == "42"

    def test_user_not_found_returns_404(self, test_client):
        client, grpc, user = test_client
        user.validate_user = AsyncMock(return_value=False)
        response = client.get("/users/99/badges")
        assert response.status_code == 404


class TestAwardBadge:
    def test_awards_badge(self, test_client):
        client, grpc, _ = test_client
        response = client.post("/users/42/badges", json={"badge_id": 1})
        assert response.status_code == 201
        assert response.json()["badge_id"] == 1
        assert response.json()["user_id"] == "42"

    def test_user_not_found_returns_404(self, test_client):
        client, grpc, user = test_client
        user.validate_user = AsyncMock(return_value=False)
        response = client.post("/users/99/badges", json={"badge_id": 1})
        assert response.status_code == 404

    def test_missing_badge_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/users/42/badges", json={})
        assert response.status_code == 422

    def test_invalid_badge_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/users/42/badges", json={"badge_id": 0})  # ge=1
        assert response.status_code == 422


# ── Health check ──────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_ok(self, test_client):
        client, _, _ = test_client
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["service"] == "badges"
