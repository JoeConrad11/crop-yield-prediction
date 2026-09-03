"""Writes predict_live.py / compare_crops.py output into Supabase, so a
scheduled job (Modal) and a future frontend don't need to share a
filesystem. Run supabase_schema.sql once in the Supabase SQL editor before
using this.
"""
import os
import numpy as np
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()


def get_client():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def _records(df: pd.DataFrame) -> list:
    """NaN isn't valid JSON -- Supabase's REST API needs it as null (None)."""
    return df.replace({np.nan: None}).to_dict(orient="records")


def write_live_predictions(df: pd.DataFrame, as_of: str, checkpoint: str):
    client = get_client()
    records = df.copy()
    records["as_of_date"] = as_of
    records["checkpoint"] = checkpoint
    client.table("live_predictions").upsert(
        _records(records),
        on_conflict="as_of_date,crop,state_fips,county_fips",
    ).execute()
    print(f"Wrote {len(records)} rows to live_predictions ({as_of})")


def write_crop_comparison(df: pd.DataFrame, as_of: str):
    client = get_client()
    records = df.copy()
    records["as_of_date"] = as_of
    client.table("crop_profitability").upsert(
        _records(records),
        on_conflict="as_of_date,crop,state_fips,county_fips",
    ).execute()
    print(f"Wrote {len(records)} rows to crop_profitability ({as_of})")
