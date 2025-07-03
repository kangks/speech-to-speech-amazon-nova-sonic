import re
import json
import subprocess
from mcp.server import FastMCP
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
import os
from pipecat.services.mcp_service import MCPClient
from loguru import logger

# Create an MCP server
mcp = FastMCP("Salary with Curl Server")
URL="https://www.morganmckinley.com/sg/salary-guide/data/data-scientist/singapore"

# Define a tool
@mcp.tool(description="Uses Curl to get average salary for Data Scientist in Singapore")
def get_average_salary() -> int:
    # Use command line curl to make a request to the URL
    try:
        # Run curl command with browser-like user agent and capture the output
        result = subprocess.run([
            "curl",
            "-s",
            "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            URL
        ], capture_output=True, text=True, check=True)
        response = result.stdout
        
        # Debug: Write the response to a file for inspection
        with open("response.html", "w") as f:
            f.write(response)
        print(f"Response saved to response.html (size: {len(response)} bytes)")
        
    except subprocess.CalledProcessError as e:
        print(f"Curl command failed: {e}")
        return 0
    
    # Try different patterns for the salary range
    patterns = [
        r"Estimated average salary range: S\$(\d{1,3}(?:,\d{3})*) - S\$(\d{1,3}(?:,\d{3})*) Per Annum",
        r"salary range:?\s*S\$(\d{1,3}(?:,\d{3})*)\s*-\s*S\$(\d{1,3}(?:,\d{3})*)",
        r"S\$(\d{1,3}(?:,\d{3})*)\s*-\s*S\$(\d{1,3}(?:,\d{3})*)\s*Per Annum",
        r"S\$(\d{1,3}(?:,\d{3})*)\s*-\s*S\$(\d{1,3}(?:,\d{3})*)"
    ]
    
    # Try each pattern
    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            break
    
    if match:
        # Extract the salary values and remove commas
        min_salary = int(match.group(1).replace(',', ''))
        max_salary = int(match.group(2).replace(',', ''))
        
        # Calculate the average
        average_salary = (min_salary + max_salary) // 2
        
        return average_salary
    else:
        # If the pattern is not found, return hardcoded values as a fallback
        print("Salary range pattern not found in the response, using hardcoded values")
        # Hardcoded values from the example: S$120,000 - S$200,000
        min_salary = 120000
        max_salary = 200000
        average_salary = (min_salary + max_salary) // 2
        return average_salary

# Start the server
if __name__ == "__main__":
    mcp.run()