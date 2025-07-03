from pathlib import Path
from typing import List, Dict, Any
import json
import os
from loguru import logger

class Jobs:
    def __init__(self):
        self.DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
        self.DATA_FILE = self.DATA_DIR / "job_questions.json"

    async def list_jobs(self) -> List[Dict[str, Any]]:
        """Gets list of jobs

        Returns:
            Array[dict]: List of jobs with their details, such as 
            [{"id": 100,"title": "AI Consultant"},{"id": 200,"title": "Data Science"}]
        """
        DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
        DATA_FILE = DATA_DIR / "job_questions.json"

        # Check if file exists
        if not DATA_FILE.exists():
            return None

        # Read and parse job questions file
        try:
            with open(DATA_FILE, 'r') as f:
                job_data = json.load(f)
        except json.JSONDecodeError as e:
            logger.exception(f"Invalid JSON in job questions file: {str(e)}")
            # If JSON is invalid, return an error response  
            return None
        
        return job_data.get("jobs", [])

    async def get_interview_questions(self, id:str) -> Dict:
        """Gets details of jobs from the data file server/integration/data/job_questions.json by the job id

        Args:
            id: job id
        returns:
        {
        "id": 100,
        "title": "AI Consultant",
        "description": "As an AI Consultant, you will develop and lead training programs on AI technologies, help organizations integrate AI solutions, and provide expertise on modern AI architectures including LLMs, RAG systems, and agent frameworks. You'll need strong technical knowledge combined with excellent communication skills to translate complex concepts for diverse audiences.",
        "questions": [
            {
            "question": "Can you explain your experience implementing Large Language Models (LLMs) in enterprise environments?",
            "expectation": "Answer should include specific LLM implementations, challenges faced, solutions developed, and business outcomes achieved."
            },
            {
            "question": "How would you approach designing a training program on AI for non-technical business stakeholders?",
            "expectation": "Answer should cover needs assessment, content simplification strategies, practical examples, and methods to measure understanding."
            },
            {
            "question": "What strategies have you used to evaluate the ROI of AI implementations?",
            "expectation": "Answer should mention specific metrics, measurement frameworks, and examples of how ROI was calculated for past projects."
            },
            {
            "question": "Describe your experience with Retrieval Augmented Generation (RAG) systems and their practical applications.",
            "expectation": "Answer should demonstrate understanding of RAG architecture, implementation experience, and specific use cases where it provided value."
            },
            {
            "question": "How do you stay current with rapidly evolving AI technologies and regulations like the AI Act?",
            "expectation": "Answer should include specific information sources, learning methods, and examples of applying new knowledge in practice."
            }
        ]
        }
        """
        DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
        DATA_FILE = DATA_DIR / "job_questions.json"

        # Check if file exists
        if not DATA_FILE.exists():
            return None

        # Read and parse job questions file
        try:
            with open(DATA_FILE, 'r') as f:
                job_data = json.load(f)
        except json.JSONDecodeError as e:
            logger.exception(f"Invalid JSON in job questions file: {str(e)}")
            return None
        
        # Find the job with the matching id
        positions = job_data.get("positions", [])
        for position in positions:
            if str(position.get("id")) == id:
                return position
        
        # Return None if no matching job is found
        return None