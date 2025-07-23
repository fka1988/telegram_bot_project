import os
import psycopg2
from urllib.parse import urlparse

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

url = urlparse(DATABASE_URL)
conn = psycopg2.connect(
    dbname=url.path[1:],
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port,
    sslmode='require'
)
cur = conn.cursor()


def init_db():
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            test_code VARCHAR(10) PRIMARY KEY,
            teacher_id BIGINT NOT NULL,
            key TEXT NOT NULL,
            feedback_mode VARCHAR(50) NOT NULL
        )
    """)
    conn.commit()


def save_test(test_code, teacher_id, key, feedback_mode):
    cur.execute(
        "INSERT INTO tests (test_code, teacher_id, key, feedback_mode) VALUES (%s, %s, %s, %s)",
        (test_code, teacher_id, key, feedback_mode),
    )
    conn.commit()


def get_test(test_code):
    cur.execute("SELECT teacher_id, key, feedback_mode FROM tests WHERE test_code = %s", (test_code,))
    return cur.fetchone()


def get_teacher_tests(teacher_id):
    cur.execute("SELECT test_code, key FROM tests WHERE teacher_id = %s", (teacher_id,))
    return cur.fetchall()
