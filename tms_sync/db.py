"""
db.py
=====
Handles the connection to your PostgreSQL database.
Every sync script imports get_connection() from here.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}


def get_connection():
    """Opens and returns a fresh connection to Postgres."""
    return psycopg2.connect(**DB_CONFIG)
