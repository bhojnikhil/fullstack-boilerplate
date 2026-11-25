"""Export the contract without starting a server or connecting to Postgres."""
import json
import os
from pathlib import Path

from app.core.config import Settings
from app.factory import create_app

os.environ.clear()
settings = Settings(env="development", _env_file=None)
schema = create_app(settings).openapi()
Path(__file__).resolve().parent.parent.joinpath("packages/api-client/openapi.json").write_text(
    json.dumps(schema, indent=2, sort_keys=True) + "\n"
)
