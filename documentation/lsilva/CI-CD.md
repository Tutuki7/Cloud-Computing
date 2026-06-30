# CI/CD Pipeline — CC2526 Group 8 (lsilva)

## Overview

The pipeline runs automatically on every **push** to `lsilva` and on every **Pull Request** targeting `lsilva`.

There are two independent pipeline files — one per microservice:

```
.github/workflows/
├── ci_cd_users.yml    ← Users Service
└── ci_cd_movies.yml   ← Movies Service
```

Each pipeline follows the same 5-stage structure:

```
[push / PR to lsilva]
        │
        ▼
Stage 1 — Lint          (flake8)
        │
        ▼
Stage 2 — Unit Tests    (pytest, no external services)
        │
        ▼
Stage 3 — Integration Tests  (pytest + SQLite + Keycloak mocked)
        │
        ▼
Stage 4 — Build         (docker build, not pushed)
        │
        ▼  ← only on push to lsilva
Stage 5 — Push          (docker push to Docker Hub)
```

Each stage only runs if the previous one passes.

---

## Pipeline files

```
.github/workflows/ci_cd_users.yml
.github/workflows/ci_cd_movies.yml
```

---

## Test structure

```
users/
└── tests/
    ├── conftest.py          ← fixtures, SQLite setup, env vars
    ├── test_unit.py         ← Pydantic validator tests (no DB/Keycloak)
    └── test_integration.py  ← endpoint tests via TestClient

movies/
└── tests/
    ├── conftest.py
    ├── test_unit.py
    └── test_integration.py
```

### Stage 2 — Unit tests
Test Pydantic model validators in complete isolation — no database, no Keycloak, no network.

| Service | Tests |
|---|---|
| users | Password rules, email format, gender enum, terms acceptance |
| movies | Release year (≥ 1874), runtime (> 0), required fields, optional fields |

### Stage 3 — Integration tests
Spin up the FastAPI app with a SQLite database and mock Keycloak calls.

| Service | Tests |
|---|---|
| users | Health, login (mock), register (mock), duplicate detection, get by ID, list with filters, update profile, delete account (404 included), promote/revoke admin, NFR-01 (password storage), NFR-02 (HS256 token rejected) |
| movies | Health, list (title/year/genre filters), create, get, update, soft-delete (404 included), genres, cast CRUD |

---

## GitHub Secrets required

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `LSILVA_DOCKERHUB_USERNAME` | `leonor2004` |
| `LSILVA_DOCKERHUB_TOKEN` | Docker Hub access token (Settings → Security → Access Tokens) |

---

## Running tests locally

### Prerequisites
```bash
pip install -r users/requirements.txt
pip install -r movies/requirements.txt
pip install pytest pytest-mock pytest-cov pyyaml
```

### Unit tests only (no services needed)
```bash
pytest users/tests/test_unit.py -v
pytest movies/tests/test_unit.py -v
```

### Integration tests (SQLite, no external services)
```bash
pytest users/tests/test_integration.py -v
pytest movies/tests/test_integration.py -v
```

### All tests
```bash
pytest users/tests/ -v
pytest movies/tests/ -v
```

### Lint
```bash
pip install flake8
flake8 users/ --max-line-length=120 --exclude=users/tests,users/grpc --ignore=E501,W503,E402,E221,E302
flake8 movies/ --max-line-length=120 --exclude=movies/tests,movies/grpc --ignore=E501,W503,E402,E221,E302
```

---

## How Keycloak is handled in tests

The tests do **not** require a running Keycloak instance. This is intentional: in CI/CD, testing against a live Keycloak would require spinning up and configuring a full realm (realm config, client secrets, roles, users) — fragile and slow. Instead, all Keycloak interactions are mocked at the boundary so that **the application logic is fully exercised** without network dependency.

| Integration test scenario | What is mocked | How |
|---|---|---|
| `POST /login` | Keycloak token endpoint | `patch("users.httpx.post")` returns fake token |
| `POST /users` (register) | Keycloak user creation | `patch("users._create_keycloak_user")` skips HTTP call |
| `PUT /users/{id}` (update) | JWT validation | `patch("users.decode_keycloak_token")` returns controlled payload |
| `DELETE /users/{id}` | JWT validation + Keycloak delete | `decode_keycloak_token` + `_delete_keycloak_user` both patched |
| `PATCH /users/{id}/admin` | JWT validation + role assignment | `decode_keycloak_token` + `_assign_keycloak_role` / `_remove_keycloak_role` patched |
| Movies admin routes | `require_admin` dependency | `app.dependency_overrides[require_admin]` always passes |

This approach validates the correct **behaviour** of each endpoint under different authentication scenarios (valid token, wrong user, missing admin role, etc.) without coupling the tests to an external service.

---

## Notes

- SQLite is used as the test database because it requires no setup and is fully compatible with the SQLAlchemy models used in both services.
- Each test cleans up its data (tables are truncated after every test) to ensure isolation.
- The `DB_URL` environment variable is set to a SQLite file path before any app module is imported, which causes `config.py` to use SQLite instead of PostgreSQL.
- Docker images are only pushed to Docker Hub on a direct push to the `lsilva` branch (not on Pull Requests).
