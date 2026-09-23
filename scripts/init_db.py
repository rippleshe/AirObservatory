from backend.db import DB_PATH, init_db

if __name__ == "__main__":
    init_db()
    print(f"initialized: {DB_PATH}")
