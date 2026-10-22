"""Password hashing (bcrypt: salted, adaptive cost)."""
import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def password_problem(password: str):
    """Return an error string if the password is weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password.isalpha() or password.isdigit():
        return "Password must mix letters with digits or symbols."
    return None


_DUMMY = None


def dummy_verify(password: str):
    """Burn comparable CPU time for unknown usernames (reduces user-enumeration timing signal)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("dummy-password")
    verify_password(password, _DUMMY)
