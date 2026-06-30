"""
test_unit.py — users-service unit tests.

Tests Pydantic model validators in isolation.
No database or external services are required.
"""
import pytest
from pydantic import ValidationError

# conftest.py has already set env vars and sys.path before this file runs
from users import UserRegister, UserUpdate


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

class TestPasswordValidation:
    VALID_BASE = dict(
        username="testuser",
        email="test@example.com",
        firstName="Test",
        lastName="User",
        termsAccepted=True,
    )

    def test_password_too_short_raises(self):
        """Password shorter than 15 characters must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UserRegister(**self.VALID_BASE, password="Short1!")
        assert "15 characters" in str(exc_info.value)

    def test_password_no_uppercase_raises(self):
        """Password without an uppercase letter must be rejected."""
        with pytest.raises(ValidationError):
            UserRegister(**self.VALID_BASE, password="alllowercase123!abc")

    def test_password_no_digit_raises(self):
        """Password without a digit must be rejected."""
        with pytest.raises(ValidationError):
            UserRegister(**self.VALID_BASE, password="NoDigitsHere!!!!abc")

    def test_password_no_special_char_raises(self):
        """Password without a special character must be rejected."""
        with pytest.raises(ValidationError):
            UserRegister(**self.VALID_BASE, password="NoSpecialChar123456")

    def test_valid_password_accepted(self):
        """A password meeting all rules must be accepted."""
        user = UserRegister(**self.VALID_BASE, password="ValidPass1!extra00")
        assert user.username == "testuser"

    def test_password_exactly_15_chars_valid(self):
        """A password of exactly 15 characters that meets all rules must pass."""
        user = UserRegister(**self.VALID_BASE, password="ValidPass123!ab")
        assert user is not None


# ---------------------------------------------------------------------------
# Email validation
# ---------------------------------------------------------------------------

class TestEmailValidation:
    VALID_BASE = dict(
        username="emailuser",
        password="ValidPass1!extra00",
        firstName="Test",
        lastName="User",
        termsAccepted=True,
    )

    def test_email_missing_at_raises(self):
        """Email without @ must be rejected."""
        with pytest.raises(ValidationError):
            UserRegister(**self.VALID_BASE, email="invalidemail.com")

    def test_email_missing_domain_raises(self):
        """Email without domain must be rejected."""
        with pytest.raises(ValidationError):
            UserRegister(**self.VALID_BASE, email="user@")

    def test_valid_email_accepted(self):
        """A standard email address must be accepted."""
        user = UserRegister(**self.VALID_BASE, email="user@example.com")
        assert user.email == "user@example.com"


# ---------------------------------------------------------------------------
# Gender validation
# ---------------------------------------------------------------------------

class TestGenderValidation:
    VALID_BASE = dict(
        username="genderuser",
        email="gender@example.com",
        password="ValidPass1!extra00",
        firstName="Test",
        lastName="User",
        termsAccepted=True,
    )

    @pytest.mark.parametrize("valid_gender", ["M", "F", "NB", "O"])
    def test_valid_genders_accepted(self, valid_gender):
        """All four valid gender codes must be accepted."""
        user = UserRegister(**self.VALID_BASE, gender=valid_gender)
        assert user.gender == valid_gender

    def test_invalid_gender_raises(self):
        """An unrecognised gender code must be rejected."""
        with pytest.raises(ValidationError):
            UserRegister(**self.VALID_BASE, gender="X")

    def test_gender_none_accepted(self):
        """Gender is optional — None must be accepted."""
        user = UserRegister(**self.VALID_BASE, gender=None)
        assert user.gender is None


# ---------------------------------------------------------------------------
# Terms and conditions
# ---------------------------------------------------------------------------

class TestTermsValidation:
    VALID_BASE = dict(
        username="termsuser",
        email="terms@example.com",
        password="ValidPass1!extra00",
        firstName="Test",
        lastName="User",
    )

    def test_terms_false_raises(self):
        """Registration with termsAccepted=False must be rejected."""
        with pytest.raises(ValidationError):
            UserRegister(**self.VALID_BASE, termsAccepted=False)

    def test_terms_true_accepted(self):
        """Registration with termsAccepted=True must pass."""
        user = UserRegister(**self.VALID_BASE, termsAccepted=True)
        assert user.termsAccepted is True


# ---------------------------------------------------------------------------
# UserUpdate validation
# ---------------------------------------------------------------------------

class TestUserUpdateValidation:
    def test_update_invalid_gender_raises(self):
        """An invalid gender value in an update must be rejected."""
        with pytest.raises(ValidationError):
            UserUpdate(gender="INVALID")

    def test_update_all_none_accepted(self):
        """An empty update (all fields None) must be accepted."""
        update = UserUpdate()
        assert update.username is None
        assert update.gender is None
        assert update.age is None
