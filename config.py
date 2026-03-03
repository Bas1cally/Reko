import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "reko-protokoll-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'reko.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "xlsx", "docx", "pptx"}

    # Group password for authentication
    GROUP_PASSWORD = os.environ.get("REKO_PASSWORD", "reko2026")

    # Archive path (OneDrive/Teams sync folder)
    ARCHIVE_PATH = os.environ.get(
        "REKO_ARCHIVE_PATH", os.path.join(BASE_DIR, "archiv")
    )

    # Schedule: Archive on Wednesday 18:00, new protocol on Wednesday 18:01
    ARCHIVE_DAY = "wed"
    ARCHIVE_HOUR = 18
    ARCHIVE_MINUTE = 0
