import os
from datetime import datetime
from pathlib import Path
import psycopg2

DB_URL = os.getenv("DB_URL") or (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

DATA_DIR = Path("data")
INIT_SQL_PATH = Path("init.sql")


# Load order respecting foreign keys
LOAD_ORDER = [
    "movies.csv", "genres.csv", "movie_genres.csv",
    "movie_cast.csv", "genre_families.csv", "genre_family_members.csv"
]

SERIAL_TABLES = [
    ("movies", "movie_id"), ("genre_families", "family_id")
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

def avg_setup(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE temp_ratings (
                rating_id INTEGER,
                user_id INTEGER,
                movie_id INTEGER,
                rating NUMERIC(2,1),
                review TEXT,
                tag TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                is_quarantined BOOLEAN
            );
        """)
        with open(DATA_DIR / "ratings.csv", "r", encoding="utf-8-sig") as f:
            header = f.readline().strip()
            cur.copy_expert(f"""
                COPY temp_ratings ({header}) FROM STDIN WITH (
                    FORMAT CSV, DELIMITER ',', NULL ''
                )
            """, f)
        cur.execute("""
            UPDATE movies m
            SET avg_rating = r.avg_r
            FROM (
                SELECT movie_id, ROUND(AVG(rating), 2) as avg_r
                FROM temp_ratings
                GROUP BY movie_id
            ) r
            WHERE m.movie_id = r.movie_id;
        """)

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
        avg_setup(conn)

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