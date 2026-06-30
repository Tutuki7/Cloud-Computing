"""
test_unit.py — movies-service unit tests.

Tests Pydantic model validators in isolation.
No database or external services are required.
"""
import pytest
from pydantic import ValidationError

# conftest.py has already set env vars and sys.path before this file runs
from movies import MovieCreate, MovieUpdate


# ---------------------------------------------------------------------------
# Release year validation
# ---------------------------------------------------------------------------

class TestReleaseYearValidation:
    VALID_BASE = dict(movie_title="Test Movie")

    def test_release_year_before_1874_raises(self):
        """Release year before 1874 must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MovieCreate(**self.VALID_BASE, release_year=1800)
        assert "1874" in str(exc_info.value)

    def test_release_year_exactly_1874_accepted(self):
        """Release year of exactly 1874 must be accepted."""
        movie = MovieCreate(**self.VALID_BASE, release_year=1874)
        assert movie.release_year == 1874

    def test_release_year_current_accepted(self):
        """A modern release year must be accepted."""
        movie = MovieCreate(**self.VALID_BASE, release_year=2024)
        assert movie.release_year == 2024

    def test_update_release_year_before_1874_raises(self):
        """An invalid release year in an update must also be rejected."""
        with pytest.raises(ValidationError):
            MovieUpdate(release_year=1000)

    def test_update_release_year_none_accepted(self):
        """An update with no release_year (None) must pass."""
        update = MovieUpdate(release_year=None)
        assert update.release_year is None


# ---------------------------------------------------------------------------
# Runtime validation
# ---------------------------------------------------------------------------

class TestRuntimeValidation:
    VALID_BASE = dict(movie_title="Test Movie", release_year=2000)

    def test_runtime_zero_raises(self):
        """Runtime of 0 must be rejected."""
        with pytest.raises(ValidationError):
            MovieCreate(**self.VALID_BASE, runtime=0)

    def test_runtime_negative_raises(self):
        """A negative runtime must be rejected."""
        with pytest.raises(ValidationError):
            MovieCreate(**self.VALID_BASE, runtime=-10)

    def test_runtime_positive_accepted(self):
        """A positive runtime (in minutes) must be accepted."""
        movie = MovieCreate(**self.VALID_BASE, runtime=120)
        assert movie.runtime == 120

    def test_runtime_none_accepted(self):
        """Runtime is optional — None must be accepted."""
        movie = MovieCreate(**self.VALID_BASE, runtime=None)
        assert movie.runtime is None


# ---------------------------------------------------------------------------
# MovieCreate required fields
# ---------------------------------------------------------------------------

class TestMovieCreateRequiredFields:
    def test_missing_title_raises(self):
        """movie_title is required — omitting it must raise ValidationError."""
        with pytest.raises(ValidationError):
            MovieCreate(release_year=2000)

    def test_missing_release_year_raises(self):
        """release_year is required — omitting it must raise ValidationError."""
        with pytest.raises(ValidationError):
            MovieCreate(movie_title="Test Movie")

    def test_minimal_valid_movie(self):
        """A movie with only the required fields must be accepted."""
        movie = MovieCreate(movie_title="Minimal Movie", release_year=1999)
        assert movie.movie_title == "Minimal Movie"
        assert movie.genres is None
        assert movie.description is None


# ---------------------------------------------------------------------------
# MovieUpdate — all fields optional
# ---------------------------------------------------------------------------

class TestMovieUpdateValidation:
    def test_empty_update_accepted(self):
        """An empty MovieUpdate (no fields) must be accepted."""
        update = MovieUpdate()
        assert update.movie_title is None
        assert update.genres is None

    def test_partial_update_accepted(self):
        """A MovieUpdate with only some fields must be accepted."""
        update = MovieUpdate(movie_title="New Title", runtime=90)
        assert update.movie_title == "New Title"
        assert update.runtime == 90
        assert update.description is None
