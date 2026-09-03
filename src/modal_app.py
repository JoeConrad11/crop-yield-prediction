"""Modal app: runs run_pipeline.py on a weekly schedule during the growing
season, so live predictions/comparisons stay current in Supabase without
manual triggering.

Deploy with: modal deploy src/modal_app.py
Run once manually (for testing): modal run src/modal_app.py
"""
import modal

app = modal.App("crop-yield-prediction")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir("src", remote_path="/root/src")
    .add_local_dir("data/raw", remote_path="/root/data/raw")       # static soil/terrain lookups
    .add_local_dir("data/processed", remote_path="/root/data/processed")  # historical model tables
    .add_local_dir("models", remote_path="/root/models")           # persisted production models
)

# GEE service-account auth (not the interactive `earthengine authenticate`
# flow used locally -- Modal has no browser). Create a GCP service account
# with Earth Engine access, download its JSON key, and store it as a Modal
# secret named "gee-service-account" with key GEE_SERVICE_ACCOUNT_JSON
# containing the full JSON key content.
secrets = [
    modal.Secret.from_name("crop-yield-env"),         # NASS_API_KEY, GEE_PROJECT_ID
    modal.Secret.from_name("gee-service-account"),      # GEE_SERVICE_ACCOUNT_JSON
    modal.Secret.from_name("supabase-credentials"),     # SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
]


@app.function(image=image, secrets=secrets, timeout=1800, schedule=modal.Cron("0 12 * * 1,4"))
def run_weekly():
    """Monday and Thursday, noon UTC. Twice a week rather than once: Modal's
    free-tier cost is trivial either way (~$0.02/run), and running only once
    a week would sit right at Supabase's free-tier 7-day inactivity pause
    threshold -- a single delayed run could let the project pause silently."""
    import sys
    import os
    import json
    import ee

    sys.path.insert(0, "/root/src")
    os.chdir("/root")

    # Modal has no browser for `earthengine authenticate` -- use a service account instead
    key_dict = json.loads(os.environ["GEE_SERVICE_ACCOUNT_JSON"])
    credentials = ee.ServiceAccountCredentials(key_dict["client_email"], key_data=json.dumps(key_dict))
    ee.Initialize(credentials, project=os.environ["GEE_PROJECT_ID"])

    from run_pipeline import run
    run(write=True)


@app.local_entrypoint()
def main():
    """`modal run src/modal_app.py` -- runs once immediately, for testing."""
    run_weekly.remote()
