from datetime import datetime, timedelta
import json
import os
import requests
import sys
import time
from pathlib import Path
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams
from dotenv import load_dotenv

from integration.interviewer_api import get_job_questions

# Load environment variables
load_dotenv(override=True)

# Get current date and time
async def get_current_date_time(params: FunctionCallParams):
    await params.result_callback(
        {
            "now": datetime.now().strftime("%Y%m%d_%H%M%S")
        }
    )    
# now
get_current_date_time_function = FunctionSchema(
    name="get_current_date_time",
    description="Returns today's date and current time, to help with restaurant bookings if user uses such as next week, and also to help validate if the booking date is in the future. The format is in %Y%m%d_%H%M%S, which is the Year-Year-Year-Year-Month-Month-Day-Day_Hour-Hour-Minute-Minute-Second-Second.",
    properties={},
    required=[],
)

# Define job questions function schema
job_questions_function = FunctionSchema(
    name="get_job_questions",
    description="Get a specific interview question for a job position. Each call returns the next question in sequence.",
    properties={
        "position": {
            "type": "string",
            "description": "The job position title to get interview questions for (e.g., 'Data Science', 'Java developer', 'AI Consultant')",
        },
    },
    required=["position"],
)

# Create tools schema
tools = ToolsSchema(standard_tools=[
    get_current_date_time_function,
    job_questions_function
])

# Function to register all functions with the LLM service
def register_functions(llm_service):
    """Register all functions with the LLM service."""
    llm_service.register_function("get_current_date_time", get_current_date_time)
    # llm_service.register_function("fetch_data_science_jobs", fetch_data_science_jobs)
    llm_service.register_function("get_job_questions", get_job_questions)