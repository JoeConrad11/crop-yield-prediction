"""Modal deployment for the main crop-yield-prediction read API
(api/main.py) -- crops, predictions, comparisons, county/state boundaries,
yield history, SHAP explanations. This is what the Vercel frontend's map
dashboard actually calls; without it deployed somewhere public, the
frontend has nothing but localhost to point NEXT_PUBLIC_API_BASE_URL at.

Separate from modal_app.py (the weekly cron that WRITES predictions into
Supabase) and assignment4/modal_serve.py (the Assignment 4 pipeline demo)
-- three independent Modal apps, each doing one job.

Deploy: modal deploy src/modal_api.py
"""
from pathlib import Path

import modal

REPO_ROOT = Path(__file__).resolve().parent.parent

app = modal.App("crop-yield-prediction-api")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(REPO_ROOT / "requirements.txt"))
    .pip_install("fastapi[standard]")
    .add_local_dir(str(REPO_ROOT / "src"), remote_path="/root/src")
    .add_local_dir(str(REPO_ROOT / "api"), remote_path="/root/api")
    .add_local_dir(str(REPO_ROOT / "data" / "processed"), remote_path="/root/data/processed")
    .add_local_dir(str(REPO_ROOT / "data" / "raw"), remote_path="/root/data/raw")
    .add_local_dir(str(REPO_ROOT / "models"), remote_path="/root/models")
)

secrets = [
    modal.Secret.from_name("crop-yield-env"),      # NASS_API_KEY, GEE_PROJECT_ID
    modal.Secret.from_name("gee-service-account"),   # GEE_SERVICE_ACCOUNT_JSON (field_predict/field_stage only)
    modal.Secret.from_name("supabase-anon"),         # SUPABASE_URL, SUPABASE_ANON_KEY -- read-only, RLS-scoped
]


@app.function(image=image, secrets=secrets, timeout=60)
@modal.asgi_app()
def fastapi_app():
    import os
    import sys

    sys.path.insert(0, "/root")
    os.chdir("/root")

    from api.main import app as web_app  # imported inside the function, not at module load time
    return web_app
