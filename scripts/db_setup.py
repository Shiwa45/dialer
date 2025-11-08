import os
import sys
import psycopg2

DB_NAME = os.environ.get('DB_NAME', 'autodialer_db')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'Shiwansh@123')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = int(os.environ.get('DB_PORT', '5432'))

def main():
    try:
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname='postgres')
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM pg_database WHERE datname=%s', (DB_NAME,))
        exists = cur.fetchone()
        if not exists:
            cur.execute(f'CREATE DATABASE {DB_NAME}')
            print(f'Created database {DB_NAME}')
        else:
            print(f'Database {DB_NAME} already exists')
    except Exception as e:
        print('ERROR:', e)
        sys.exit(1)

if __name__ == '__main__':
    main()

