"""
test_integration.py — users-service integration tests.

Tests the REST API endpoints end-to-end using a SQLite in-memory database.
Keycloak calls are mocked so no running Keycloak instance is required.
"""
import pytest
from unittest.mock import patch

# conftest.py fixtures: client, db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_USER = {
    "username": "integrationuser",
    "email": "integration@example.com",
    "password": "ValidPass1!extra00",
    "firstName": "Integration",
    "lastName": "User",
    "termsAccepted": True,
}


def _register(client, overrides=None):
    """Helper: register a user, mocking Keycloak."""
    payload = {**VALID_USER, **(overrides or {})}
    with patch("users._create_keycloak_user", return_value="mock-kc-id"):
        return client.post("/users", json=payload)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        """GET /health must return 200 with status ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# User registration
# ---------------------------------------------------------------------------

class TestUserRegistration:
    def test_register_user_success(self, client):
        """POST /users with valid data must create a user and return 201."""
        resp = _register(client)
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == VALID_USER["username"]
        assert data["email"] == VALID_USER["email"]
        assert data["is_admin"] is False
        assert "user_id" in data
        assert "password" not in data  # password must not be exposed

    def test_register_duplicate_username_returns_409(self, client):
        """Registering with a username that already exists must return 409."""
        _register(client)
        resp = _register(client, {"email": "other@example.com"})
        assert resp.status_code == 409

    def test_register_duplicate_email_returns_409(self, client):
        """Registering with an email that already exists must return 409."""
        _register(client)
        resp = _register(client, {"username": "otheruser"})
        assert resp.status_code == 409

    def test_register_weak_password_returns_422(self, client):
        """POST /users with a weak password must return 422."""
        resp = client.post("/users", json={**VALID_USER, "password": "weak"})
        assert resp.status_code == 422

    def test_register_terms_not_accepted_returns_422(self, client):
        """POST /users with termsAccepted=false must return 422."""
        resp = client.post("/users", json={**VALID_USER, "termsAccepted": False})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# User retrieval
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_get_existing_user(self, client):
        """GET /users/{id} for an existing user must return 200."""
        reg = _register(client)
        user_id = reg.json()["user_id"]

        resp = client.get(f"/users/{user_id}")
        assert resp.status_code == 200
        assert resp.json()["user_id"] == user_id

    def test_get_nonexistent_user_returns_404(self, client):
        """GET /users/{id} for a non-existent ID must return 404."""
        resp = client.get("/users/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# User listing
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_list_users_returns_list(self, client):
        """GET /users must return a JSON array."""
        resp = client.get("/users")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_users_includes_registered_user(self, client):
        """GET /users must include a user after registration."""
        _register(client)
        resp = client.get("/users")
        usernames = [u["username"] for u in resp.json()]
        assert VALID_USER["username"] in usernames

    def test_list_users_filter_by_username(self, client):
        """GET /users?username=... must filter results."""
        _register(client)
        resp = client.get("/users", params={"username": "integrationuser"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert all("integrationuser" in u["username"] for u in data)

    def test_list_users_invalid_gender_returns_400(self, client):
        """GET /users with an invalid gender must return 400."""
        resp = client.get("/users", params={"gender": "INVALID"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client):
        """POST /login with valid credentials must return a token."""
        with patch("users.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "access_token": "fake-access-token",
                "refresh_token": "fake-refresh-token",
                "token_type": "Bearer",
                "expires_in": 300,
            }
            resp = client.post("/login", json={"username": "testuser", "password": "testpass"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "fake-access-token"
        assert data["token_type"] == "Bearer"

    def test_login_invalid_credentials_returns_401(self, client):
        """POST /login with wrong credentials must return 401."""
        with patch("users.httpx.post") as mock_post:
            mock_post.return_value.status_code = 401
            resp = client.post("/login", json={"username": "wrong", "password": "wrong"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# User update
# ---------------------------------------------------------------------------

class TestUpdateUser:
    def test_update_own_profile_success(self, client):
        """PUT /users/{id} with a valid token must update the user."""
        user_id = _register(client).json()["user_id"]
        with patch("users.decode_keycloak_token", return_value={"preferred_username": VALID_USER["username"]}):
            resp = client.put(
                f"/users/{user_id}",
                json={"age": 30},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert resp.status_code == 200
        assert resp.json()["age"] == 30

    def test_update_another_user_returns_403(self, client):
        """PUT /users/{id} with a token for a different user must return 403."""
        user_id = _register(client).json()["user_id"]
        with patch("users.decode_keycloak_token", return_value={"preferred_username": "otheruser"}):
            resp = client.put(
                f"/users/{user_id}",
                json={"age": 30},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert resp.status_code == 403

    def test_update_nonexistent_user_returns_404(self, client):
        """PUT /users/99999 must return 404."""
        with patch("users.decode_keycloak_token", return_value={"preferred_username": "anyuser"}):
            resp = client.put(
                "/users/99999",
                json={"age": 30},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# User deletion
# ---------------------------------------------------------------------------

class TestDeleteUser:
    def test_delete_own_account_success(self, client):
        """DELETE /users/{id} with a valid token must delete the user."""
        user_id = _register(client).json()["user_id"]
        with patch("users.decode_keycloak_token", return_value={"preferred_username": VALID_USER["username"]}), \
             patch("users._delete_keycloak_user"):
            resp = client.delete(
                f"/users/{user_id}",
                headers={"Authorization": "Bearer fake-token"},
            )
        assert resp.status_code == 204

    def test_delete_another_user_returns_403(self, client):
        """DELETE /users/{id} with a token for a different user must return 403."""
        user_id = _register(client).json()["user_id"]
        with patch("users.decode_keycloak_token", return_value={"preferred_username": "otheruser"}):
            resp = client.delete(
                f"/users/{user_id}",
                headers={"Authorization": "Bearer fake-token"},
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin promotion
# ---------------------------------------------------------------------------

class TestSetAdmin:
    def test_promote_to_admin_success(self, client):
        """PATCH /users/{id}/admin with admin token must set is_admin=true."""
        user_id = _register(client).json()["user_id"]
        with patch("users.decode_keycloak_token", return_value={
            "preferred_username": "admin",
            "realm_access": {"roles": ["admin"]},
        }), patch("users._assign_keycloak_role"):
            resp = client.patch(
                f"/users/{user_id}/admin",
                params={"is_admin": True},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True

    def test_promote_without_admin_role_returns_403(self, client):
        """PATCH /users/{id}/admin without admin role must return 403."""
        user_id = _register(client).json()["user_id"]
        with patch("users.decode_keycloak_token", return_value={
            "preferred_username": "normaluser",
            "realm_access": {"roles": []},
        }):
            resp = client.patch(
                f"/users/{user_id}/admin",
                params={"is_admin": True},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert resp.status_code == 403
