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
# from pipecat.services.mcp_service import MCPClient
# from mcp import StdioServerParameters

from dotenv import load_dotenv
from integration.jobs import Jobs
import os

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

async def get_all_jobs(params: FunctionCallParams):
    """Gets list of jobs

    Returns:
        Array[dict]: List of jobs with their details, such as
        [{"id": 100,"title": "AI Consultant"},{"id": 200,"title": "Data Science"}]
    """    
    try:
        # Create an instance of the Jobs class
        jobs_instance = Jobs()
        # Call the instance method
        jobs_list = await jobs_instance.list_jobs()
        print(f"Jobs list: {jobs_list}")
        await params.result_callback({
            "jobs": jobs_list,
            "status": "success"
        })
    except Exception as e:
        print(f"Error fetching jobs: {str(e)}")
        logger.exception(f"Error fetching jobs: {str(e)}")
        await params.result_callback(
            result = {
                "error": True,
                "message": "No job positions found in the data",
                "status": "failed"
            }
        )

async def get_interview_questions(params: FunctionCallParams):
    """Gets details of jobs from the data file server/integration/data/job_questions.json by the job id"""
    from integration.jobs import Jobs
    import os
    
    job_id = params.arguments.get("id")
    if not job_id:
        await params.result_callback(None)
        return
    
    try:
        # Create an instance of the Jobs class
        jobs_instance = Jobs()
        # Call the instance method
        interview_questions = await jobs_instance.get_interview_questions(job_id)
        await params.result_callback({
            "interview_questions": interview_questions,
            "status": "success"
        })
    except Exception as e:
        logger.exception(f"Error fetching interview questions: {str(e)}")
        await params.result_callback(            
            result = {
                "error": True,
                "message": "No interview questions found for the specified job ID",
                "status": "failed"
            }
)

# Define function schemas

get_current_date_time_function_schema = FunctionSchema(
    name="get_current_date_time",
    description="Returns today's date and current time, to help with restaurant bookings if user uses such as next week, and also to help validate if the booking date is in the future. The format is in %Y%m%d_%H%M%S, which is the Year-Year-Year-Year-Month-Month-Day-Day_Hour-Hour-Minute-Minute-Second-Second.",
    properties={},
    required=[],
)

list_jobs_function_schema = FunctionSchema(
    name="ListJobsFunction",
    description="Gets a list of available jobs with their IDs and titles",
    properties={},
    required=[],
)

get_interview_questions_function_schema = FunctionSchema(
    name="InterviewGuestionsFunction",
    description="Gets detailed information about a specific job including description and interview questions",
    properties={
        "id": {
            "type": "string",
            "description": "The ID of the job to retrieve details for",
        },
    },
    required=["id"],
)

# Create tools schema
function_tools_schema = ToolsSchema(standard_tools=[
    get_current_date_time_function_schema,
    list_jobs_function_schema,
    get_interview_questions_function_schema
])

# Function to register all functions with the LLM service
def register_functions(llm_service):
    """Register all functions with the LLM service."""
    llm_service.register_function("get_current_date_time", get_current_date_time)
    llm_service.register_function("ListJobsFunction", get_all_jobs)
    llm_service.register_function("InterviewGuestionsFunction", get_interview_questions)

