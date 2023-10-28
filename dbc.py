import psycopg2
from urllib.parse import urlparse
from psycopg2 import pool
import os
try:
    from secrets import DB_URL 
except Exception:
    DB_URL = os.getenv('DB_URL')

def print_db():
    print (DB_URL)

def db_connect(url):
    """Returns a database connection object."""
    conn = psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    return conn


def get_cursor(db_access):
    """To get cursor for interacting with database."""
    if db_access['conn'].closed:
        db_access['conn'] = db_connect(db_access['url'])
        db_access['cur'] = db_access['conn'].cursor()
    return db_access['cur']


def connect():
    dburl = DB_URL
    url = urlparse(dburl)
    try:
        conn = db_connect(url)
        #cur = conn.cursor()
        return conn
    except Exception:
        print('Could not connect to the database!')


def connect_pool():
    dburl = DB_URL
    url = urlparse(dburl)
    try:
        connection = pool.ThreadedConnectionPool(1, 25,
                                                          database=url.path[1:],
                                                          user=url.username,
                                                          password=url.password,
                                                          host=url.hostname,
                                                          port=url.port
                                                          )
        return connection
    except (Exception, psycopg2.DatabaseError) as error:
        print("Error while connecting to PostgreSQL", error)


if __name__ == "__main__":
    #print_db()
    connect()
