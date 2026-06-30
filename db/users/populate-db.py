import os
import hashlib
from datetime import datetime
from pathlib import Path
import psycopg2

DB_URL = os.getenv("DB_URL") or (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

DATA_DIR = Path("data")
INIT_SQL_PATH = Path("init.sql")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Load order respecting foreign keys
LOAD_ORDER = [
    "users.csv", "user_oauth.csv", "user_sessions.csv"
]

SERIAL_TABLES = [
    ("users", "user_id"), ("user_sessions", "session_id")
]

def get_conn():
    return psycopg2.connect(DB_URL)

def create_schema(conn):
    print("creating schema from init.sql...")
    with conn.cursor() as cur, open(INIT_SQL_PATH, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    print("schema created successfully.")

def copy_csv_to_postgres(conn, csv_file):
    table_name = csv_file.replace(".csv", "")
    csv_path = DATA_DIR / csv_file
    print(f"loading {table_name}...")

    with conn.cursor() as cur, open(csv_path, "r", encoding="utf-8-sig") as f:
        header_line = f.readline().strip()

        copy_sql = f"""
            COPY {table_name} ({header_line}) FROM STDIN WITH (
                FORMAT CSV, DELIMITER ',', QUOTE '"', ESCAPE '"', NULL '', HEADER FALSE
            )
        """
        cur.copy_expert(copy_sql, f)
    print(f"loaded {table_name}")

def reset_sequences(conn):
    print("\nresetting sequences...")
    with conn.cursor() as cur:
        for table, column in SERIAL_TABLES:
            try:
                cur.execute(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', '{column}'),
                        COALESCE((SELECT MAX({column}) FROM {table}), 0) + 1,
                        false
                    )
                """)
                print(f"  reset sequence for {table}.{column}")
            except Exception as e:
                print(f"  skipping {table}.{column}: {e}")
    print("sequences reset complete.")

def create_admin(conn):
    print("\ncreating admin user if not exists...")
    hashed = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
    now = datetime.now()

    with conn.cursor() as cur:
        print("  adding is_admin column to users table...")
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
        """)

        cur.execute(
            "SELECT user_id FROM users WHERE username = %s OR email = %s",
            (ADMIN_USERNAME, ADMIN_EMAIL)
        )
        existing = cur.fetchone()

        if existing:
            print(f"  admin '{ADMIN_USERNAME}' already exists, skipping")
        else:
            cur.execute("""
                INSERT INTO users (username, email, password, gender, age, is_admin, created_at, updated_at)
                VALUES (%s, %s, %s, NULL, NULL, TRUE, %s, %s)
            """, (ADMIN_USERNAME, ADMIN_EMAIL, hashed, now, now))
            print(f"  admin '{ADMIN_USERNAME}' created successfully.")


def main():
    print("starting db setup and population...")
    conn = get_conn()
    conn.autocommit = False

    try:
        create_schema(conn)
        conn.commit()

        for csv_file in LOAD_ORDER:
            csv_path = DATA_DIR / csv_file
            if csv_path.exists():
                copy_csv_to_postgres(conn, csv_file)
            else:
                print(f"missing CSV: {csv_file}")

        reset_sequences(conn)
        create_admin(conn)

        conn.commit()
        print(f"\n db setup complete")

    except Exception as e:
        conn.rollback()
        print("\n Error during import:")
        print(e)

    finally:
        conn.close()

if __name__ == "__main__":
    main()