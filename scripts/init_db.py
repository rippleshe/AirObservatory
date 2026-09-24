from backend.config import get_settings
from backend.db import init_db

if __name__ == "__main__":
    init_db()
    print(f"initialized: {get_settings().resolved_database_path}")
