from pathlib import Path
import os
import json
import logging
from pipecat.services.llm_service import FunctionCallParams

DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
DATA_FILE = DATA_DIR / "job_questions.json"
logger = logging.getLogger(__name__)

# Initialize global question index
CURRENT_QUESTION_INDEX = 0

# Function to get job questions based on position
async def get_job_questions(params: FunctionCallParams):
    """Function to get a specific interview question for a job position."""
    global CURRENT_QUESTION_INDEX
    
    try:
        job_title = params.arguments.get("position", "").strip().lower()

        # Path to job questions JSON file
        job_questions_file = DATA_FILE
        
        # Check if file exists
        if not job_questions_file.exists():
            await params.result_callback({
                "error": True,
                "message": f"Job questions file not found at {job_questions_file}",
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
                "message": f"Invalid JSON in job questions file: {str(e)}",
                "status": "failed"
            })
            return
            
        # Find matching position
        positions = job_data.get("positions", [])
        matched_position = None
        
        # Convert job_title to lowercase for case-insensitive matching
        job_title_lower = job_title.lower()
        
        for pos in positions:
            if job_title_lower in pos.get("title", "").lower():
                matched_position = pos
                break
                
        # If no exact match, try partial match
        if not matched_position:
            for pos in positions:
                if any(word.lower() in pos.get("title", "").lower() for word in job_title.split()):
                    matched_position = pos
                    break
        
        # If still no match, return the first position as default
        if not matched_position and positions:
            matched_position = positions[0]
            logger.warning(f"No matching position found for '{job_title}', using default: {matched_position.get('title')}")
        
        # Return result
        if matched_position:
            questions = matched_position.get("questions", [])
            
            # Check if questions list is empty
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
        logger.exception(f"{error_message} - Exception type: {type(e).__name__}")
        await params.result_callback({
            "error": True,
            "message": error_message,
            "status": "failed"
        })
        return
