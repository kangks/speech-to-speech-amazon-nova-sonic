import re
import json
import subprocess
from mcp.server import FastMCP
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
import os
from pipecat.services.mcp_service import MCPClient
from loguru import logger

async def get_mcp_client() -> MCPClient:
    # Configure the parameters for launching a local Python MCP server
    server_params = StdioServerParameters(
        command="python",
        args=["integration/average_salary_mcp_server.py"],
        cwd=os.getcwd(),
    )

    logger.info(f"Starting MCP server with parameters: {server_params}")

    try:
        mcp = MCPClient(server_params)
        return mcp
    except Exception as e:
        logger.error(f"error setting up mcp")
        logger.exception("error trace:")
        raise e
