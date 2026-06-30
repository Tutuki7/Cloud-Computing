"""
test_integration.py — movies-service integration tests.

Tests the REST API endpoints end-to-end using a SQLite test database.
Keycloak auth is bypassed via FastAPI dependency overrides for admin routes.
"""
import pytest
from sqlalchemy import text

# conftest.py fixtures: client, admin_client, db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_MOVIE = {
    "movie_title": "Integration Test Movie",
    "release_year": 2000,
    "description": "A movie for testing purposes.",
    "runtime": 120,
    "parental_rating": "PG-13",
}


def _seed_genre(db, name="Drama"):
    """Insert a genre directly into the test DB and return its id."""
    from config import GenreTable
    genre = GenreTable(name=name)
    db.add(genre)
    db.commit()
    db.refresh(genre)
    return genre


def _create_movie(admin_client, overrides=None):
    """Helper: create a movie via the admin client."""
    payload = {**VALID_MOVIE, **(overrides or {})}
    return admin_client.post("/movies", json=payload)


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
# Genres
# ---------------------------------------------------------------------------

class TestGenres:
    def test_list_genres_empty(self, client):
        """GET /genres on an empty DB must return an empty list."""
        resp = client.get("/genres")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_genres_returns_seeded_genre(self, client, db):
        """GET /genres must include genres that exist in the DB."""
        _seed_genre(db, "Drama")
        resp = client.get("/genres")
        assert resp.status_code == 200
        names = [g["name"] for g in resp.json()]
        assert "Drama" in names


# ---------------------------------------------------------------------------
# Movie listing
# ---------------------------------------------------------------------------

class TestListMovies:
    def test_list_movies_empty(self, client):
        """GET /movies on an empty DB must return an empty list."""
        resp = client.get("/movies")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_movies_includes_created_movie(self, admin_client):
        """GET /movies must include a movie after it has been created."""
        _create_movie(admin_client)
        resp = admin_client.get("/movies")
        assert resp.status_code == 200
        titles = [m["movie_title"] for m in resp.json()]
        assert VALID_MOVIE["movie_title"] in titles

    def test_list_movies_filter_by_title(self, admin_client):
        """GET /movies?title=... must return only matching movies."""
        _create_movie(admin_client)
        resp = admin_client.get("/movies", params={"title": "Integration"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert all("Integration" in m["movie_title"] for m in data)

    def test_list_movies_filter_by_year(self, admin_client):
        """GET /movies?release_year=... must return only matching movies."""
        _create_movie(admin_client)
        resp = admin_client.get("/movies", params={"release_year": 2000})
        assert resp.status_code == 200
        assert all(m["release_year"] == 2000 for m in resp.json())


# ---------------------------------------------------------------------------
# Movie creation
# ---------------------------------------------------------------------------

class TestCreateMovie:
    def test_create_movie_success(self, admin_client):
        """POST /movies with valid data must return 201."""
        resp = _create_movie(admin_client)
        assert resp.status_code == 201
        data = resp.json()
        assert data["movie_title"] == VALID_MOVIE["movie_title"]
        assert data["is_deleted"] is False
        assert "movie_id" in data

    def test_create_movie_with_genre(self, admin_client, db):
        """POST /movies with a valid genre must associate it."""
        _seed_genre(db, "Action")
        resp = _create_movie(admin_client, {"genres": ["Action"]})
        assert resp.status_code == 201
        assert "Action" in resp.json()["genres"]

    def test_create_movie_requires_auth(self, client):
        """POST /movies without a token must return 403."""
        resp = client.post("/movies", json=VALID_MOVIE)
        assert resp.status_code == 403

    def test_create_movie_missing_title_returns_422(self, admin_client):
        """POST /movies without movie_title must return 422."""
        resp = admin_client.post("/movies", json={"release_year": 2000})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Movie retrieval
# ---------------------------------------------------------------------------

class TestGetMovie:
    def test_get_existing_movie(self, admin_client):
        """GET /movies/{id} for an existing movie must return 200."""
        movie_id = _create_movie(admin_client).json()["movie_id"]
        resp = admin_client.get(f"/movies/{movie_id}")
        assert resp.status_code == 200
        assert resp.json()["movie_id"] == movie_id

    def test_get_nonexistent_movie_returns_404(self, client):
        """GET /movies/99999 must return 404."""
        resp = client.get("/movies/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Movie deletion (soft-delete)
# ---------------------------------------------------------------------------

class TestDeleteMovie:
    def test_delete_movie_hides_from_list(self, admin_client):
        """After DELETE, the movie must not appear in GET /movies."""
        movie_id = _create_movie(admin_client).json()["movie_id"]
        del_resp = admin_client.delete(f"/movies/{movie_id}")
        assert del_resp.status_code == 204

        movies = admin_client.get("/movies").json()
        ids = [m["movie_id"] for m in movies]
        assert movie_id not in ids

    def test_delete_movie_requires_auth(self, client, db):
        """DELETE /movies/{id} without a token must return 403."""
        from config import MovieTable
        movie = MovieTable(movie_title="Auth Test Movie", release_year=2000, is_deleted=False)
        db.add(movie)
        db.commit()
        db.refresh(movie)
        resp = client.delete(f"/movies/{movie.movie_id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Cast
# ---------------------------------------------------------------------------

class TestCast:
    def test_get_cast_empty(self, admin_client):
        """GET /movies/{id}/cast on a new movie must return an empty list."""
        movie_id = _create_movie(admin_client).json()["movie_id"]
        resp = admin_client.get(f"/movies/{movie_id}/cast")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_add_cast_member(self, admin_client):
        """POST /movies/{id}/cast must add a cast member and return 201."""
        movie_id = _create_movie(admin_client).json()["movie_id"]
        resp = admin_client.post(
            f"/movies/{movie_id}/cast",
            json={"cast_name": "Tom Hanks", "role": "Forrest Gump"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["cast_name"] == "Tom Hanks"
        assert data["role"] == "Forrest Gump"

    def test_remove_cast_member(self, admin_client):
        """DELETE /movies/{id}/cast/{cast_id} must remove the cast member."""
        movie_id = _create_movie(admin_client).json()["movie_id"]
        cast_id = admin_client.post(
            f"/movies/{movie_id}/cast",
            json={"cast_name": "Tom Hanks"},
        ).json()["cast_id"]

        del_resp = admin_client.delete(f"/movies/{movie_id}/cast/{cast_id}")
        assert del_resp.status_code == 204

        cast = admin_client.get(f"/movies/{movie_id}/cast").json()
        assert all(c["cast_id"] != cast_id for c in cast)


# ---------------------------------------------------------------------------
# Movie update
# ---------------------------------------------------------------------------

class TestUpdateMovie:
    def test_update_movie_title_success(self, admin_client):
        """PUT /movies/{id} must update the movie title."""
        movie_id = _create_movie(admin_client).json()["movie_id"]
        resp = admin_client.put(
            f"/movies/{movie_id}",
            json={"movie_title": "Updated Title", "runtime": 150},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["movie_title"] == "Updated Title"
        assert data["runtime"] == 150

    def test_update_movie_genre(self, admin_client, db):
        """PUT /movies/{id} with genres must replace the genre list."""
        _seed_genre(db, "Thriller")
        movie_id = _create_movie(admin_client).json()["movie_id"]
        resp = admin_client.put(
            f"/movies/{movie_id}",
            json={"genres": ["Thriller"]},
        )
        assert resp.status_code == 200
        assert "Thriller" in resp.json()["genres"]

    def test_update_nonexistent_movie_returns_404(self, admin_client):
        """PUT /movies/99999 must return 404."""
        resp = admin_client.put(
            "/movies/99999",
            json={"movie_title": "Updated Title"},
        )
        assert resp.status_code == 404

    def test_update_movie_requires_auth(self, client):
        """PUT /movies/{id} without a token must return 403."""
        resp = client.put(
            "/movies/1",
            json={"movie_title": "Updated Title"},
        )
        assert resp.status_code == 403
