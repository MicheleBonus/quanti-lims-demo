import os
import secrets

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _get_secret_key() -> str:
    """Return SECRET_KEY from env, or generate and persist one."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    key_file = os.path.join(BASE_DIR, ".secret_key")
    if os.path.exists(key_file):
        with open(key_file) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(key_file, "w") as f:
        f.write(key)
    return key


class Config:
    SECRET_KEY = _get_secret_key()
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'quanti_lims.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ADMIN_BACKUP_TOKEN = os.environ.get("ADMIN_BACKUP_TOKEN")
