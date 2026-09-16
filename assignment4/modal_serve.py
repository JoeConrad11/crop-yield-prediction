"""Modal deployment for the Assignment 4 pipeline API.

Ships exactly three files into the image: serve.py, pipeline_def.py,
pipeline.joblib. sklearn is pinned to the exact version recorded in the
bundle's metadata at build time (see build_pipeline.py) so unpickling the
fitted GradientBoostingRegressor/CountyAnomalyTransformer can't silently
break on a version drift.

Deploy: modal deploy assignment4/modal_serve.py
Test once: modal serve assignment4/modal_serve.py
"""
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
SKLEARN_VERSION = "1.9.0"  # must match metadata["sklearn_version"] in pipeline.joblib

app = modal.App("yield-anomaly-pipeline-api")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "fastapi[standard]",
        f"scikit-learn=={SKLEARN_VERSION}",
        "pandas",
        "joblib",
    )
    .add_local_file(str(HERE / "serve.py"), remote_path="/root/app/serve.py")
    .add_local_file(str(HERE / "pipeline_def.py"), remote_path="/root/app/pipeline_def.py")
    .add_local_file(str(HERE / "pipeline.joblib"), remote_path="/root/app/pipeline.joblib")
)


@app.function(image=image)
@modal.asgi_app()
def fastapi_app():
    import sys
    sys.path.insert(0, "/root/app")

    from serve import app as web_app  # imported inside the function, not at module load time
    return web_app
