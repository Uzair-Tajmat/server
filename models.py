from sqlalchemy import create_engine
# from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

# Fetch variables
USER = "postgres"
PASSWORD = "ytrtrtPostgres1"
HOST = "db.lklzjspcwmlpbbkamccb.supabase.co"
PORT = "5432"
DBNAME = "postgres"
# Construct the SQLAlchemy connection string
DATABASE_URL = "postgresql+psycopg2://postgres:ytrtrtPostgres1@db.lklzjspcwmlpbbkamccb.supabase.co:5432/postgres?sslmode=require"

# Create the SQLAlchemy engine
engine = create_engine(DATABASE_URL)
# If using Transaction Pooler or Session Pooler, we want to ensure we disable SQLAlchemy client side pooling -
# https://docs.sqlalchemy.org/en/20/core/pooling.html#switching-pool-implementations
# engine = create_engine(DATABASE_URL, poolclass=NullPool)

# Test the connection
try:
    with engine.connect() as connection:
        print("Connection successful!")
except Exception as e:
    print(f"Failed to connect: {e}")