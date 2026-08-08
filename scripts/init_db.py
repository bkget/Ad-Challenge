import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

conn = psycopg2.connect(dsn="postgresql://postgres:postgres@localhost:5432/postgres")
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cursor = conn.cursor()
try:
    cursor.execute('CREATE DATABASE "Ad-DB"')
    print("Created Ad-DB successfully")
except Exception as e:
    print(f"Error or already exists: {e}")
cursor.close()
conn.close()
