import asyncio
import os
import sys
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("qiskit-mcp-server")

# Import tools
from qiskit_mcp_server.qiskit_tools import register_tools
register_tools(mcp)

def main():
    """Entry point for the MCP server."""
    print("Starting Qiskit MCP Server...", file=sys.stderr)
    mcp.run()

if __name__ == "__main__":
    main()
