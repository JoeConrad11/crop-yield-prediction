"""GET /comparisons -- reads crop_profitability and, by default, pivots
server-side into one object per county with a `crops` map keyed by whatever
crop ids are present. `best_crop`/`margin_dollars` are computed here via a
plain max-over-N, not a hardcoded pairwise comparison, so this endpoint's
shape doesn't change when a third crop is added to src/config.py CROPS --
only the `crops` map grows another key. The frontend should always read
`best_crop` from this response rather than recomputing it client-side.
"""
from typing import Optional

from fastapi import APIRouter, Query

from ..db import get_client

router = APIRouter()

_PROFIT_FIELDS = ["yield_bu_acre", "price_per_bu", "cost_per_acre", "revenue_per_acre", "profit_per_acre"]


def _pivot_by_county(rows: list[dict]) -> list[dict]:
    by_county: dict[tuple, dict] = {}
    for row in rows:
        key = (row["state_fips"], row["county_fips"])
        entry = by_county.setdefault(key, {
            "state_fips": row["state_fips"],
            "county_fips": row["county_fips"],
            "county_name": row["county_name"],
            "state_alpha": row["state_alpha"],
            "crops": {},
        })
        entry["crops"][row["crop"]] = {field: row.get(field) for field in _PROFIT_FIELDS}

    out = []
    for entry in by_county.values():
        priced = {
            crop: fields["profit_per_acre"]
            for crop, fields in entry["crops"].items()
            if fields["profit_per_acre"] is not None
        }
        if priced:
            ranked = sorted(priced.items(), key=lambda kv: kv[1], reverse=True)
            entry["best_crop"] = ranked[0][0]
            entry["margin_dollars"] = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else None
        else:
            entry["best_crop"] = None
            entry["margin_dollars"] = None
        out.append(entry)
    return out


@router.get("/comparisons")
def comparisons(
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD, omit for latest"),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
    format: str = Query("by_county", pattern="^(by_county|long)$"),
):
    client = get_client()
    if as_of is None:
        latest = (
            client.table("crop_profitability")
            .select("as_of_date")
            .order("as_of_date", desc=True)
            .limit(1)
            .execute()
        )
        if not latest.data:
            return []
        as_of = latest.data[0]["as_of_date"]

    query = client.table("crop_profitability").select("*").eq("as_of_date", as_of)
    if state:
        query = query.eq("state_fips", state)
    if county:
        query = query.eq("county_fips", county)
    rows = query.execute().data

    if format == "long":
        return rows
    return _pivot_by_county(rows)
