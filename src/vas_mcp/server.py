from __future__ import annotations

import argparse

from fastmcp import FastMCP

from vas_mcp.service import MCP_PORT, default_mcp_config
from vas_mcp.tools import display, docker, logs, network, shell, system

mcp = FastMCP("vas-mcp")

mcp.mount(system.mcp)
mcp.mount(network.mcp)
mcp.mount(display.mcp)
mcp.mount(docker.mcp)
mcp.mount(logs.mcp)
mcp.mount(shell.mcp)


def run_server(host: str, port: int) -> None:
    print(f"Starting VAS MCP server at http://{host}:{port}")
    mcp.run(transport="sse", host=host, port=port)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mcp_server",
        description="VAS MCP server (system diagnostics + guarded shell execution — see mcp/tools/shell.py).",
    )
    parser.add_argument("--host", default=default_mcp_config().host)
    parser.add_argument("--port", type=int, default=MCP_PORT)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_server(host=args.host, port=args.port)
