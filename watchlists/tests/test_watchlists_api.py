"""
Tests for the Watchlists REST API (watchlists.py)

Strategy:
- The FastAPI app depends on two gRPC clients: WatchlistGrpcClient and UserGrpcClient.
- We never start a real gRPC server or database here.
- Instead, we patch both clients with AsyncMock so tests are fast and isolated.
- The TestClient from httpx (via starlette) is used to call the routes directly.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# ── Shared fake data ──────────────────────────────────────────────────────────

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)

WATCHLIST_1 = {
    "watchlist_id": 1,
    "user_id": "42",
    "title": "My Favourites",
    "created_at": NOW,
    "updated_at": NOW,
}

WATCHLIST_2 = {
    "watchlist_id": 2,
    "user_id": "42",
    "title": "Watch Later",
    "created_at": NOW,
    "updated_at": NOW,
}

WATCHLIST_DETAIL = {
    **WATCHLIST_1,
    "movies": [
        {"watchlist_id": 1, "movie_id": 10, "added_at": NOW},
    ],
}

WATCHLIST_MOVIE = {
    "watchlist_id": 1,
    "movie_id": 10,
    "added_at": NOW,
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_grpc_client():
    """Mock for WatchlistGrpcClient — controls all watchlist CRUD responses."""
    client = AsyncMock()
    client.list_watchlists = AsyncMock(return_value=[WATCHLIST_1, WATCHLIST_2])
    client.get_watchlist = AsyncMock(return_value=WATCHLIST_DETAIL)
    client.create_watchlist = AsyncMock(return_value=WATCHLIST_1)
    client.update_watchlist = AsyncMock(return_value={**WATCHLIST_1, "title": "Updated Title"})
    client.delete_watchlist = AsyncMock(return_value=True)
    client.get_user_watchlists = AsyncMock(return_value=[WATCHLIST_1, WATCHLIST_2])
    client.add_movie = AsyncMock(return_value=WATCHLIST_MOVIE)
    client.remove_movie = AsyncMock(return_value=True)
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
    with patch("watchlists.grpc_client", mock_grpc_client), \
         patch("watchlists.user_client", mock_user_client):

        from watchlists import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, mock_grpc_client, mock_user_client


# ── Watchlist routes ──────────────────────────────────────────────────────────

class TestListWatchlists:
    def test_returns_all_watchlists(self, test_client):
        client, grpc, _ = test_client
        response = client.get("/watchlists")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["watchlist_id"] == 1
        assert data[1]["watchlist_id"] == 2

    def test_calls_grpc_list_watchlists(self, test_client):
        client, grpc, _ = test_client
        client.get("/watchlists")
        grpc.list_watchlists.assert_called_once()


class TestGetWatchlist:
    def test_returns_watchlist_with_movies(self, test_client):
        client, grpc, _ = test_client
        response = client.get("/watchlists/1")
        assert response.status_code == 200
        data = response.json()
        assert data["watchlist_id"] == 1
        assert data["title"] == "My Favourites"
        assert len(data["movies"]) == 1
        assert data["movies"][0]["movie_id"] == 10

    def test_invalid_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.get("/watchlists/0")  # ge=1 constraint
        assert response.status_code == 422


class TestCreateWatchlist:
    def test_creates_watchlist(self, test_client):
        client, grpc, _ = test_client
        payload = {"user_id": "42", "title": "My Favourites"}
        response = client.post("/watchlists", json=payload)
        assert response.status_code == 201
        assert response.json()["title"] == "My Favourites"
        assert response.json()["user_id"] == "42"

    def test_missing_title_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/watchlists", json={"user_id": "42"})
        assert response.status_code == 422

    def test_missing_user_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/watchlists", json={"title": "My Favourites"})
        assert response.status_code == 422

    def test_user_not_found_returns_404(self, test_client):
        client, grpc, user = test_client
        user.validate_user = AsyncMock(return_value=False)
        response = client.post("/watchlists", json={"user_id": "99", "title": "My Favourites"})
        assert response.status_code == 404

    def test_calls_grpc_with_correct_args(self, test_client):
        client, grpc, _ = test_client
        client.post("/watchlists", json={"user_id": "42", "title": "My Favourites"})
        grpc.create_watchlist.assert_called_once_with(user_id="42", title="My Favourites")


class TestUpdateWatchlist:
    def test_updates_watchlist(self, test_client):
        client, grpc, _ = test_client
        response = client.put("/watchlists/1", json={"title": "Updated Title"})
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    def test_missing_title_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.put("/watchlists/1", json={})
        assert response.status_code == 422

    def test_invalid_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.put("/watchlists/0", json={"title": "X"})
        assert response.status_code == 422


class TestDeleteWatchlist:
    def test_deletes_watchlist(self, test_client):
        client, grpc, _ = test_client
        response = client.delete("/watchlists/1")
        assert response.status_code == 204

    def test_invalid_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.delete("/watchlists/0")
        assert response.status_code == 422


class TestAddMovie:
    def test_adds_movie(self, test_client):
        client, grpc, _ = test_client
        response = client.post("/watchlists/1/movies", json={"movie_id": 10})
        assert response.status_code == 201
        assert response.json()["movie_id"] == 10
        assert response.json()["watchlist_id"] == 1

    def test_missing_movie_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/watchlists/1/movies", json={})
        assert response.status_code == 422

    def test_invalid_movie_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/watchlists/1/movies", json={"movie_id": 0})  # ge=1
        assert response.status_code == 422

    def test_invalid_watchlist_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.post("/watchlists/0/movies", json={"movie_id": 1})
        assert response.status_code == 422

    def test_calls_grpc_with_correct_args(self, test_client):
        client, grpc, _ = test_client
        client.post("/watchlists/1/movies", json={"movie_id": 10})
        grpc.add_movie.assert_called_once_with(watchlist_id=1, movie_id=10)


class TestRemoveMovie:
    def test_removes_movie(self, test_client):
        client, grpc, _ = test_client
        response = client.delete("/watchlists/1/movies/10")
        assert response.status_code == 204

    def test_invalid_watchlist_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.delete("/watchlists/0/movies/10")
        assert response.status_code == 422

    def test_invalid_movie_id_returns_422(self, test_client):
        client, _, _ = test_client
        response = client.delete("/watchlists/1/movies/0")
        assert response.status_code == 422


# ── User watchlist routes ─────────────────────────────────────────────────────

class TestGetUserWatchlists:
    def test_returns_user_watchlists(self, test_client):
        client, grpc, _ = test_client
        response = client.get("/users/42/watchlist")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["user_id"] == "42"

    def test_user_not_found_returns_404(self, test_client):
        client, grpc, user = test_client
        user.validate_user = AsyncMock(return_value=False)
        response = client.get("/users/99/watchlist")
        assert response.status_code == 404


# ── Health check ──────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_ok(self, test_client):
        client, _, _ = test_client
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["service"] == "watchlists"
