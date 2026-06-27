@echo off
uv sync
set PYTHONPATH=src
uv run python -m flask --app "server:create_app" run --debug --port 8080