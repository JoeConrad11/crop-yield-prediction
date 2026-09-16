"""FastAPI service serving the crop-yield-prediction pipeline's Supabase
output to the frontend. Read-only -- writes still happen via
src/supabase_writer.py from the Modal cron (src/run_pipeline.py).

Run locally: uvicorn api.main:app --reload (from the repo root).
"""
import sys
from pathlib import Path

# src/ isn't an installed package -- its own modules import each other as
# `from config import ...` (bare, not `from src.config import ...`), so we
# put src/ on sys.path the same way running a src/ script directly would,
# rather than duplicating CROPS/STATES here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api.routers import (  # noqa: E402
    comparisons, crops, explain, field_predict, field_stage, geo, history, predictions,
)

app = FastAPI(title="Crop Yield Prediction API")

app.add_middleware(
    CORSMiddleware,
    # `next dev` picks whatever port is free (3000, 3001, ...) when the
    # default is taken, so match any localhost/127.0.0.1 port in dev.
    # Also match any *.vercel.app origin -- the deployed frontend gets a
    # fresh per-deployment hash URL each time (frontend-<hash>-...) on top
    # of its stable alias, so a single hardcoded origin isn't enough.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+|https://.*\.vercel\.app",
    # POST is only used by field_predict.router -- everything else here is
    # still read-only GET.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(crops.router)
app.include_router(predictions.router)
app.include_router(comparisons.router)
app.include_router(geo.router)
app.include_router(history.router)
app.include_router(explain.router)
app.include_router(field_predict.router)
app.include_router(field_stage.router)


@app.get("/health")
def health():
    return {"status": "ok"}
