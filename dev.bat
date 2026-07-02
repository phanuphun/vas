@echo off
uv sync
set PYTHONPATH=src
set VAS_DEV_FAKE_INSTALLED=1
uv run python -m cli db migrate
uv run python -m flask --app "server:create_app" run --debug --port 8080