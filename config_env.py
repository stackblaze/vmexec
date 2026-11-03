import os

# Base Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DATA_DIR can be overridden via environment variable (useful for Docker volumes)
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))

# Ensure required directories exist
os.makedirs(DATA_DIR, exist_ok=True)

# Database path
SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'backup_system.db')}"
