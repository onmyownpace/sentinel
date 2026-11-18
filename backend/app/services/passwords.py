"""Password hashing helpers.

bcrypt is enough for a learning-scale email/password account. There is no
password-reset flow and no complexity policy beyond a short minimum length.
"""

import bcrypt

_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_BYTES = 72


def validate_password_plaintext(password: str) -> str:
    """Return the password when it is acceptable, else raise ValueError."""
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {_MIN_PASSWORD_LENGTH} characters")
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError("Password is too long")
    return password


def hash_password(password: str) -> str:
    """Hash a validated plaintext password for storage."""
    cleaned = validate_password_plaintext(password)
    digest = bcrypt.hashpw(cleaned.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True when the plaintext matches the stored hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
