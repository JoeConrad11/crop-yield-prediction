"""Supabase client for the read-only API layer. Uses the anon key
(RLS-scoped, public-read policies in src/supabase_schema.sql) -- never the
service-role key src/supabase_writer.py uses for the Modal cron write path.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


@lru_cache
def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)
