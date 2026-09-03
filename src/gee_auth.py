"""Centralized Earth Engine initialization, called once by every fetch/predict
script instead of each one calling ee.Initialize() itself.

Supports two auth paths:
- Local dev: interactive `earthengine authenticate` (run once per machine),
  picked up automatically by ee.Initialize(project=...).
- Modal (or any headless environment): a service-account JSON key passed via
  the GEE_SERVICE_ACCOUNT_JSON env var (no browser available there).
"""
import os
import json
import ee
from dotenv import load_dotenv

load_dotenv()

_initialized = False


def ensure_initialized():
    global _initialized
    if _initialized:
        return
    project = os.environ["GEE_PROJECT_ID"]
    service_account_json = os.environ.get("GEE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        key_dict = json.loads(service_account_json)
        credentials = ee.ServiceAccountCredentials(key_dict["client_email"], key_data=service_account_json)
        ee.Initialize(credentials, project=project)
    else:
        ee.Initialize(project=project)
    _initialized = True
