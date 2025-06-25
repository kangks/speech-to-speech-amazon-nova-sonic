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

# Load environment variables
load_dotenv(override=True)

# Job board API URL
JOB_BOARD_API_URL = "https://www.arbeitnow.com/api/job-board-api"

# Cache settings
CACHE_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "cache"
CACHE_FILE = CACHE_DIR / "job_data.json"
CACHE_EXPIRY_SECONDS = 3600  # 1 hour

# Create cache directory if it doesn't exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# State for job questions
CURRENT_QUESTION_INDEX = 0


# Get current date and time
async def get_current_date_time(params: FunctionCallParams):
    await params.result_callback(
        {
            "now": datetime.now().strftime("%Y%m%d_%H%M%S")
        }
    )    

# Cache utility functions
def read_cache():
    """Read job data from cache file if it exists and is valid."""
    try:
        if not CACHE_FILE.exists():
            logger.debug(f"Cache file {CACHE_FILE} does not exist")
            return None
        
        # Check if cache is expired
        cache_mtime = CACHE_FILE.stat().st_mtime
        cache_age = time.time() - cache_mtime
        
        # if cache_age > CACHE_EXPIRY_SECONDS:
        #     logger.debug(f"Cache is expired (age: {cache_age:.2f}s, max: {CACHE_EXPIRY_SECONDS}s)")
        #     return None
        
        # Read and parse cache file
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)
            logger.info(f"Successfully loaded job data from cache (age: {cache_age:.2f}s)")
            return cache_data
            
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing cache file: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error reading cache: {str(e)}")
        return None

def write_cache(data):
    """Write job data to cache file."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f)
        logger.info(f"Successfully wrote job data to cache: {CACHE_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error writing to cache: {str(e)}")
        return False

# Function to fetch Data Science jobs from the job board API
async def fetch_data_science_jobs(params: FunctionCallParams):
    """Function to fetch Data Science jobs from the job board API."""
    try:
        # Extract search parameters if provided (for return format consistency)
        search_term = params.arguments.get("search_term", "Data Science")
        page = params.arguments.get("page", 1)
        
        # Try to get data from cache first
        job_data = None
        cached_data = read_cache()
        job_data = cached_data

        # If job_data is None, initialize it with an empty structure
        if job_data is None:
            job_data = {"data": []}
            logger.info("No cached data available, using empty job data structure")

        if cached_data:
            logger.info("Using cached job data")
            job_data = cached_data
        else:
            # Cache miss or expired, fetch from API
            # Prepare request URL without search parameters (API doesn't support server-side search)
            request_url = f"{JOB_BOARD_API_URL}"
            logger.info(f"Cache miss or expired. Fetching all jobs from API - Request URL: {request_url}")
            
            try:
                # Make API request to get all jobs
                response = requests.get(
                    request_url,
                    timeout=10  # Set a reasonable timeout
                )
                
                # Check if request was successful
                response.raise_for_status()
                
                try:
                    # Parse response data
                    job_data = response.json()
                    
                    # Write to cache for future use
                    write_cache(job_data)
                    
                except json.JSONDecodeError as e:
                    # Handle JSON parsing errors
                    error_message = f"Error parsing job board API response: {str(e)}"
                    logger.error(f"{error_message} - Response content: {response.text[:200]}")
                    await params.result_callback({
                        "error": True,
                        "message": error_message,
                        "status": "failed",
                        "response_code": response.status_code
                    })
                    return
                    
            except requests.exceptions.ConnectionError as e:
                # Handle connection errors
                error_message = f"Connection error while fetching jobs: {str(e)}"
                logger.error(f"{error_message} - URL: {request_url}")
                await params.result_callback({
                    "error": True,
                    "message": error_message,
                    "status": "failed",
                    "error_type": "connection_error"
                })
                return
                
            except requests.exceptions.Timeout as e:
                # Handle timeout errors
                error_message = f"Timeout error while fetching jobs: {str(e)}"
                logger.error(f"{error_message} - URL: {request_url}, Timeout: 10s")
                await params.result_callback({
                    "error": True,
                    "message": error_message,
                    "status": "failed",
                    "error_type": "timeout"
                })
                return
                f
            except requests.exceptions.HTTPError as e:
                # Handle HTTP errors with response details
                status_code = e.response.status_code if hasattr(e, 'response') else "unknown"
                error_message = f"HTTP error while fetching jobs: {str(e)}"
                
                # Try to get error details from response
                error_details = {}
                try:
                    if hasattr(e, 'response') and e.response.text:
                        error_details = e.response.json()
                except json.JSONDecodeError:
                    error_details = {"raw_response": e.response.text[:200]} if hasattr(e, 'response') else {}
                    
                logger.error(f"{error_message} - Status code: {status_code}, URL: {request_url}")
                logger.error(f"Error details: {json.dumps(error_details)}")
                
                await params.result_callback({
                    "error": True,
                    "message": error_message,
                    "status": "failed",
                    "status_code": status_code,
                    "error_details": error_details
                })
                return
                
            except requests.exceptions.RequestException as e:
                # Handle other request errors
                error_message = f"Request error while fetching jobs: {str(e)}"
                logger.error(f"{error_message} - URL: {request_url}")
                await params.result_callback({
                    "error": True,
                    "message": error_message,
                    "status": "failed",
                    "error_type": "request_error"
                })
                return
        
        # Process the job data (either from cache or fresh API response)
        # Client-side filtering for jobs with "Data Science" in the title
        data_science_jobs = []
        # Ensure job_data is not None before accessing it
        all_jobs = [] if job_data is None else job_data.get("data", [])
        
        # Apply pagination after filtering
        start_index = (page - 1) * 10  # Assuming 10 jobs per page
        
        # Filter all jobs first
        filtered_jobs = []
        for job in all_jobs:
            if "Data Science" in job.get("title", ""):
                # Include only relevant job information
                filtered_job = {
                    "title": job.get("title", ""),
                    "company_name": job.get("company_name", ""),
                    "location": job.get("location", ""),
                    "remote": job.get("remote", False),
                    "url": job.get("url", ""),
                    "created_at": job.get("created_at", "")
                }
                filtered_jobs.append(filtered_job)
        
        # Apply pagination to filtered results
        total_filtered = len(filtered_jobs)
        data_science_jobs = filtered_jobs[start_index:start_index + 10] if start_index < total_filtered else []
        
        # Prepare response (maintaining the same format as before)
        result = {
            "jobs": data_science_jobs,
            "count": len(data_science_jobs),
            "total_count": total_filtered,
            "search_term": search_term,
            "page": page,
            "from_cache": cached_data is not None
        }
        
        source = "cache" if cached_data else "API"
        logger.info(f"Found {total_filtered} Data Science jobs from {source} (showing {len(data_science_jobs)} for page {page})")
        await params.result_callback(result)
                
    except Exception as e:
        # Handle any other unexpected errors
        error_message = f"Unexpected error fetching jobs: {str(e)}"
        logger.error(f"{error_message} - Exception type: {type(e).__name__}")
        
        # Return error response
        await params.result_callback({
            "error": True,
            "message": error_message,
            "status": "failed",
            "error_type": "unexpected_error"
        })
            

# Function to get job questions based on position
async def get_job_questions(params: FunctionCallParams):
    """Function to get a specific interview question for a job position."""
    global CURRENT_QUESTION_INDEX
    
    try:
        # Extract parameters
        position = params.arguments.get("position", "").strip().lower()
        
        if not position:
            await params.result_callback({
                "error": True,
                "message": "Position parameter is required",
                "status": "failed"
            })
            return
            
        # Path to job questions JSON file
        job_questions_file = CACHE_DIR / "job_questions.json"
        
        # Check if file exists
        if not job_questions_file.exists():
            await params.result_callback({
                "error": True,
                "message": f"Job questions file not found: {job_questions_file}",
                "status": "failed"
            })
            return
            
        # Read and parse job questions file
        try:
            with open(job_questions_file, 'r') as f:
                job_data = json.load(f)
        except json.JSONDecodeError as e:
            await params.result_callback({
                "error": True,
                "message": f"Error parsing job questions file: {str(e)}",
                "status": "failed"
            })
            return
            
        # Find matching position
        positions = job_data.get("positions", [])
        matched_position = None
        
        for pos in positions:
            if position in pos.get("title", "").lower():
                matched_position = pos
                break
                
        # If no exact match, try partial match
        if not matched_position:
            for pos in positions:
                if any(word in pos.get("title", "").lower() for word in position.split()):
                    matched_position = pos
                    break
        
        # If still no match, return the first position as default
        if not matched_position and positions:
            matched_position = positions[0]
            logger.warning(f"No matching position found for '{position}', using default: {matched_position.get('title')}")
        
        # Return result
        if matched_position:
            questions = matched_position.get("questions", [])
            
            # Check if question_index is valid
            if not questions:
                await params.result_callback({
                    "error": True,
                    "message": f"No questions found for position: {matched_position.get('title')}",
                    "status": "failed"
                })
                return
                
            # Check if current question index is valid
            if not questions:
                await params.result_callback({
                    "error": True,
                    "message": f"No questions found for position: {matched_position.get('title')}",
                    "status": "failed"
                })
                return
                
            # Reset index if it's out of range
            if CURRENT_QUESTION_INDEX < 0 or CURRENT_QUESTION_INDEX >= len(questions):
                CURRENT_QUESTION_INDEX = 0
                
            # Return only the specific question
            specific_question = questions[CURRENT_QUESTION_INDEX]
            
            # Increment the question index for next call
            CURRENT_QUESTION_INDEX = (CURRENT_QUESTION_INDEX + 1) % len(questions)
            result = {
                "question": specific_question.get("question", ""),
                "expectation": specific_question.get("expectation", ""),
                "status": "success"
            }
        else:
            result = {
                "error": True,
                "message": "No job positions found in the data",
                "status": "failed"
            }

        logger.info(f"result: {result}")
            
        await params.result_callback(result)
        
    except Exception as e:
        # Handle any unexpected errors
        error_message = f"Unexpected error getting job questions: {str(e)}"
        logger.error(f"{error_message} - Exception type: {type(e).__name__}")
        
        # Return error response
        await params.result_callback({
            "error": True,
            "message": error_message,
            "status": "failed",
            "error_type": "unexpected_error"
        })

# now
get_current_date_time_function = FunctionSchema(
    name="get_current_date_time",
    description="Returns today's date and current time, to help with restaurant bookings if user uses such as next week, and also to help validate if the booking date is in the future. The format is in %Y%m%d_%H%M%S, which is the Year-Year-Year-Year-Month-Month-Day-Day_Hour-Hour-Minute-Minute-Second-Second.",
    properties={},
    required=[],
)

# Define job board function schema
job_board_function = FunctionSchema(
    name="fetch_data_science_jobs",
    description="Fetch Data Science job listings from the job board API",
    properties={
        "search_term": {
            "type": "string",
            "description": "Search term to filter jobs (defaults to 'Data Science')",
            "optional": True,
        },
        "page": {
            "type": "integer",
            "description": "Page number for pagination (defaults to 1)",
            "optional": True,
        },
    },
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
    job_board_function,
    job_questions_function
])

# Function to register all functions with the LLM service
def register_functions(llm_service):
    """Register all functions with the LLM service."""
    llm_service.register_function("get_current_date_time", get_current_date_time)
    # llm_service.register_function("fetch_data_science_jobs", fetch_data_science_jobs)
    llm_service.register_function("get_job_questions", get_job_questions)