# Import various modules
import json
from datetime import datetime, timedelta
import os
import uuid
import time
import random
import openai
from openai import OpenAI
import PyPDF2
import docx
from io import BytesIO, StringIO
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from .data_manager import DataManager
import logging
import re

# Configuration log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("learning_system.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Morandi color scheme
MORANDI_COLORS = {
    "primary": "#6264A7",      
    "secondary": "#0078D4",    
    "accent": "#00B42A",       
    "light": "#F4F4F4",        
    "success": "#00B42A",      
    "warning": "#FFB900",      
    "text": "#333333",         
    "card_bg": "#FFFFFF",      
    "bg": "#F8F9FA"            
}

# an auxiliary function for handling file uploads
def extract_text_from_file(uploaded_file):
    """Extract the text content from different types of files"""
    try:
        if uploaded_file.type == "application/pdf":
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
                
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = docx.Document(uploaded_file)
            text = "\n".join([para.text for para in doc.paragraphs])
            
        elif uploaded_file.type == "text/plain":
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            text = stringio.read()
            
        else:
            return {"status": "error", "message": f"Unsupported file types: {uploaded_file.type}"}
            
        # Limit the text length to avoid it being too long
        return {"status": "success", "text": text[:5000]}
    except Exception as e:
        logger.error(f"The file content extraction failed: {str(e)}")
        return {"status": "error", "message": f"The file content cannot be extracted: {str(e)}"}

# Core module implementation
class MockUserManager:
    """User management class,handling user authentication and information management"""
    def authenticate_user(self, username, password):
        """Verify the user's identity"""
        return {"id": 1, "username": username, "email": f"{username}@example.com", "full_name": username}
    
    def register_user(self, username, password, email, full_name, interests, learning_style):
        """Register a new user"""
        return 1

    def get_user_profile(self, user_id):
        """Obtain the user's personal information"""
        return {
            "interests": "Mathematics, Science, Literature",
            "learning_style": "Visual"
        }

    def update_user_profile(self, user_id, **kwargs):
        """Update the user's personal information"""
        pass

# Learning path engine(with persistent storage)
class MockLearningEngine:
    """The learning engine class,handles the generation of learning paths, progress tracking, and learning analysis"""
    def __init__(self):
        self.data_dir = "data"
        self.paths_file = os.path.join(self.data_dir, "learning_paths.json")
        self._ensure_data_dir()
        self.data_manager = DataManager()

    def _ensure_data_dir(self):
        """Make sure the data directory exists"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def get_learning_paths(self, user_id):
        """Obtain all the learning paths of the user"""
        try:
            return self.data_manager.execute_query('''
                SELECT * FROM learning_paths 
                WHERE user_id = %s 
                ORDER BY created_at DESC
            ''', (user_id,))
        except Exception as e:
            logger.error(f"Failed to obtain the learning path: {str(e)}")
            return []

    def get_learning_path(self, path_id, user_id):
        """Get details of a specific learning path"""
        try:
            paths = self.data_manager.execute_query('''
                SELECT * FROM learning_paths 
                WHERE id = %s AND user_id = %s
            ''', (path_id, user_id))
            return paths[0] if paths else None
        except Exception as e:
            logger.error(f"Failed to obtain a specific learning path: {str(e)}")
            return None
    
    def delete_learning_path(self, path_id, user_id):
        """Delete the specific learning path of a particular user"""
        try:
            self.data_manager.execute_query('''
                DELETE FROM learning_paths 
                WHERE id = %s AND user_id = %s
            ''', (path_id, user_id))
        except Exception as e:
            logger.error(f"Failed to delete the learning path: {str(e)}")
    
    def create_learning_path(self, user_id, subject, difficulty, target_days, ai_agent, default=True):
        """Create structured learning path, giving priority to AI-generated ones, and use the default paths when they fail"""
        try:
            target_date = (datetime.now() + timedelta(days=target_days)).strftime("%Y-%m-%d")
            user_profile = self.data_manager.execute_query('''
                SELECT interests, learning_style FROM users WHERE id = %s
            ''', (user_id,))
            
            if not user_profile:
                logger.warning(f"The user does not exist: {user_id}")
                return None
            
            user_interests = user_profile[0]['interests'] or "General interests"
            learning_style = user_profile[0]['learning_style'] or "Visual"
            path_content = self._generate_ai_learning_path(subject, user_interests, learning_style, difficulty, target_days, ai_agent)
            
            if not path_content:
                logger.warning(f"The AI failed to generate the learning path and used the default path: {subject}")
                # Generate the default path as a backup
                path_content = self._generate_default_learning_path(subject, difficulty, target_days)
            
            # Save to the database
            path_id = self.data_manager.execute_query('''
                INSERT INTO learning_paths 
                (user_id, subject, difficulty_level, content, target_completion_date, created_at, last_updated)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            ''', (
                user_id, 
                subject, 
                difficulty, 
                json.dumps(path_content),
                target_date,
            ))
            
            return path_id, default
        except Exception as e:
            logger.error(f"Failed to create the learning path: {str(e)}")
            return None, False

    def _generate_default_learning_path(self, subject, difficulty, target_days):
        """Generate a default learning path as a backup for failed AI generation"""
        return {
            "topics": [
                {
                    "name": f"{subject} Basic knowledge",
                    "description": f"Introduce the basic concepts and principles of Introduction to {subject} to lay a foundation for subsequent learning.",
                    "duration_days": max(1, int(target_days * 0.3)),
                    "resources": [
                        {
                            "title": f"{subject} A beginner's guide",
                            "type": "Article",
                            "description": f"A comprehensive introduction to the basic knowledge of {subject}",
                            "platform": "Learning platform",
                            "url": f"https://example.com/search?q={subject}+basics"
                        }
                    ],
                    "practice_exercises": [
                        {
                            "question": f"Explain the basic concepts of {subject}",
                            "difficulty": difficulty,
                            "estimated_time_minutes": 20,
                            "answer": f"{subject} the basic concepts include...",
                            "explanation": f"This question assesses the understanding of the core concepts of {subject}..."
                        }
                    ]
                }
            ],
            "milestones": [
                {
                    "expected_completion_day": int(target_days / 2),
                    "name": f"{subject} Mid-term assessment",
                    "assessment_criteria": f"Be able to explain the key concepts of {subject} and solve basic problems"
                }
            ],
            "learning_strategies": [
                f"Spend time every day reviewing the core concepts of {subject}",
                "Do exercises to consolidate what you have learned"
            ]
        }

    def _generate_ai_learning_path(self, subject, user_interests, learning_style, difficulty, target_days, ai_agent):
        """Use AI to generate personalized learning paths, including correctly formatted urls"""
        prompt = f"""
        You are a world-class educational curriculum designer, skilled at creating structured learning paths.
        Design a comprehensive learning path based on the following parameters:
        - Theme：{subject}
        - Difficulty level：{difficulty}
        - Target completion time：{target_days}day
        - User interest：{user_interests}
        - Learning style：{learning_style}

        The learning path must include educational resources suitable for learners of {learning_style}.
        The learning path must be logically progressive, starting from basic concepts and gradually advancing to more complex topics.
        It should include the following components:
        
        1. 3 to 5 main themes, comprehensively covering the discipline
        - Each topic must have a clear and descriptive title
        - Provide a detailed explanation of the content covered by this topic (3-5 sentences)
        - Appropriate duration allocation (the total is approximately {target_days} days)
        - 3-5 high-quality learning resources, including:
            * Descriptive title
            * Resource types (videos, articles, interactions, etc.)
            * A detailed description of content/value
            * Source/Platform name (e.g., Coursera, YouTube, Medium, Khan Academy)
            * The URL format is [Platform base URL] + search query related to the resource
            - Example：
                - https://www.coursera.org/search?query={subject}+fundamentals
                - https://www.youtube.com/results?search_query={subject}+tutorial
                - https://medium.com/search?q={subject}+advanced+techniques
        
        - 2 to 3 practice questions, including:
            * Clear and challenging questions
            * Difficulty rating (matching the overall difficulty level)
            * Estimated completion time (minutes)
            * Detailed answer
            * A comprehensive explanation of the solution/concept
        
        2. 2-3 key milestones, including:
        - Expected completion date (relative to the start)
        - Descriptive milestone name
        - Specific assessment criteria (quantified as much as possible)
        
        3. Three to four learning strategies, specifically tailored for the following aspects:
        - The unique challenges of this discipline
        - The specified difficulty level
        - Best knowledge retention

        Format your response in a valid JSON format with the exact structure as follows:
        {{
            "topics": [
                {{
                    "name": "Theme Name",
                    "description": "Detailed topic description",
                    "duration_days": 3,
                    "resources": [
                        {{
                            "title": "Resource Title",
                            "type": "Resource type",
                            "description": "Resource content description",
                            "platform": "Platform name",
                            "url": "https://platform.com/search?q={subject}+specific+terms"
                        }}
                    ],
                    "practice_exercises": [
                        {{
                            "question": "Exercise text",
                            "difficulty": "Difficulty level",
                            "estimated_time_minutes": 25,
                            "answer": "Complete answer text",
                            "explanation": "A detailed explanation of the concept"
                        }}
                    ]
                }}
            ],
            "milestones": [
                {{
                    "expected_completion_day": 7,
                    "name": "Milestone name",
                    "assessment_criteria": "Specific achievement requirements"
                }}
            ],
            "learning_strategies": ["Strategy1", "Strategy2", "Strategy3"]
        }}
        
        Key requirements
        - All urls must follow the platform base URL + search query format shown in the example
        - The URL must be valid and point to the relevant content
        - Maintain consistency with the specified JSON structure
        - Ensure that the content is rigorous in education and suitable for the difficulty level
        """
        
        messages = [
            {"role": "system", "content": "You are a professional educational curriculum designer, creating structured and progressive learning paths. Your output must be valid JSON, strictly following the specified format. The URL should adopt the platform's basic + search query format."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = ai_agent._call_api(messages, response_format={"type": "json_object"})
            if not response or not isinstance(response, str):
                logger.warning(f"AI returned invalid response for learning path: {response}")
                return None
            
            # Verify the URL format in the response
            path_content = json.loads(response.strip())
            if "topics" in path_content:
                for topic in path_content["topics"]:
                    if "resources" in topic:
                        for resource in topic["resources"]:
                            if "url" in resource:
                                # Check whether the URL contains search query parameters
                                if "search?" not in resource["url"] and "query=" not in resource["url"]:
                                    logger.warning(f"URL {resource['url']} does not meet the required search format")
            return path_content
        except json.JSONDecodeError as e:
            logger.error(f"AI learning path JSON parsing failed: {e}, Response: {response[:200]}...")
            return None
        except Exception as e:
            logger.error(f"AI learning path generation failed: {e}, Response: {str(response)[:200]}...")
            return None

    def update_viewed_resource(self, user_id, path_id, topic_name, resource_name, duration_minutes=0):
        """Update the viewing status of learning resources (optimistic lock + short transaction)"""
        try:
            duration_minutes = max(0.0, float(duration_minutes))  # Ensure the duration is legal
            max_retries = 3
            retry_delay = 0.5

            for attempt in range(max_retries):
                # 1. First, query the current record (including the version number. You need to add the Version field to the learning_activities table first).
                query = """
                    SELECT id, content, total_minutes, version 
                    FROM learning_activities 
                    WHERE user_id = %s AND path_id = %s AND topic_name = %s
                    LIMIT 1
                """
                result = self.data_manager.execute_query(query, (user_id, path_id, topic_name))

                # 2. Prepare to update the data
                if result:
                    # The record exists: updated
                    record = result[0]
                    # Enhance the robustness of JSON parsing
                    content_str = record.get('content', '{}')
                    if not content_str or not isinstance(content_str, str):
                        content_dict = {}
                    else:
                        try:
                            content_dict = json.loads(content_str)
                        except json.JSONDecodeError as e:
                            logger.error(f"Content JSON parsing failed: {e}, Content: {content_str[:100]}...")
                            content_dict = {}
                    
                    current_total = float(record['total_minutes'])
                    current_version = record['version']

                    # Update only when the resource is not marked (to avoid duplicate operations)
                    if content_dict.get(resource_name) is None:
                        content_dict[resource_name] = 1
                        updated_content = json.dumps(content_dict)
                        new_total = current_total + duration_minutes

                        # 3. Intra-transaction update execution (with optimistic lock)
                        try:
                            row_count = self.data_manager.execute_query("""
                                UPDATE learning_activities 
                                SET content = %s, total_minutes = %s, activity_date = NOW(), version = version + 1
                                WHERE id = %s AND version = %s
                            """, (updated_content, new_total, record['id'], current_version))

                            if row_count == 1:
                                self.data_manager.commit_transaction()
                                return {"status": "success"}
                            else:
                                # Version conflict, roll back and retry
                                self.data_manager.rollback_transaction()
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delay * (attempt + 1))
                                    continue
                                raise Exception("Version conflict, update failed")
                        except Exception as e:
                            self.data_manager.rollback_transaction()
                            raise e
                    else:
                        # The resource has been marked and no update is required
                        return {"status": "success", "message": "The resource has been marked."}

                else:
                    # Record does not exist: Insert a new record
                    initial_content = json.dumps({resource_name: 1})
                    self.data_manager.execute_query("""
                        INSERT INTO learning_activities 
                        (user_id, path_id, topic_name, content, total_minutes, activity_date, version)  
                        VALUES (%s, %s, %s, %s, %s, NOW(), 1)
                    """, (user_id, path_id, topic_name, initial_content, duration_minutes))
                    return {"status": "success"}

            return {"status": "error", "message": "Reach the maximum number of retries"}

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed：{str(e)}")
            return {"status": "error", "message": "Data format error"}
        except Exception as e:
            logger.error(f"Failed to update the viewing status of the resource：{str(e)}")
            return {"status": "error", "message": str(e)}
    
    def check_resource_viewed(self, user_id, path_id, topic_name, resource_name):
        """Check whether the viewing status of the specified resource is 1 (watched)"""
        try:
            # Query the records under this user, path, and topic
            query = """
                SELECT content FROM learning_activities 
                WHERE user_id = %s AND path_id = %s AND topic_name = %s
                """
            result = self.data_manager.execute_query(query, (user_id, path_id, topic_name))
            
            if not result:
                # The record does not exist and is regarded as not viewed
                return False
            
            # Parse the content field (in JSON format)
            content_json = result[0]
            content_str = content_json.get('content', '{}')
            if not content_str or not isinstance(content_str, str):
                logger.warning(f"Invalid content format for learning activity: {content_json}")
                return False
            
            try:
                inner_content = json.loads(content_str)
            except json.JSONDecodeError as e:
                logger.error(f"Content JSON parsing failed: {e}, Content: {content_str[:100]}...")
                return False

            # Check if the resource status is 1 (if it exists and the value is 1, return True)
            return inner_content.get(resource_name, 0) == 1
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed：{str(e)}")
            return False
        except Exception as e:
            logger.error(f"Failed to query the viewing status of the resource：{str(e)}")
            return False

    def update_learning_progress(self, path_id, user_id, new_progress):
        """Update the learning progress (optimistic locking + retry, solve lock waiting)"""
        try:
            # 1. Ensure that the progress is within the legal range (0-1)
            new_progress = max(0.0, min(1.0, new_progress))
            max_retries = 3  # Retry up to 3 times (for occasional conflicts)
            retry_delay = 0.5  # Retry interval (seconds)

            for attempt in range(max_retries):
                # 2. Query the current version number outside the transaction (unlocked to avoid resource occupation)
                path_data = self.data_manager.execute_query('''
                    SELECT version FROM learning_paths 
                    WHERE id = %s AND user_id = %s
                ''', (path_id, user_id))
            
                if not path_data:
                    logger.warning(f"path {path_id} It doesn't exist. Progress cannot be updated")
                    return 0
            
                current_version = path_data[0]['version']  #Get the current version

                # 3. Only updates are performed within the transaction (minimizing lock holding time)
                try:
                    # The core of optimistic locking: The WHERE condition contains version, and only updates the records that have not been modified
                    row_count = self.data_manager.execute_query('''
                        UPDATE learning_paths 
                        SET progress = %s, last_updated = NOW(), version = version + 1  -- The version number is incremented
                        WHERE id = %s AND user_id = %s AND version = %s  -- Update only when the version matches
                    ''', (new_progress, path_id, user_id, current_version))

                    if row_count == 1:
                        # The update was successful. Commit the transaction
                        self.data_manager.commit_transaction()
                        logger.info(f"path {path_id} Progress update successful（version：{current_version}→{current_version+1}）")
                        return row_count
                    elif row_count == 0:
                        # Version mismatch. Roll back and try again
                        self.data_manager.rollback_transaction()
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))  # Exponential retreat waiting
                            logger.warning(f"path {path_id} Version conflict，Try again the {attempt+1} th time")
                            continue
                        else:
                            logger.error(f"path {path_id} version conflict，the maximum number of retries has been reached.")
                            return 0

                except Exception as e:
                    # For other errors, roll back the transaction
                    self.data_manager.rollback_transaction()
                    logger.error(f"The progress update transaction failed：{str(e)}")
                    return 0

        except Exception as e:
            logger.error(f"There are always errors in updating the learning progress：{str(e)}")
            return 0
    
    def add_topic_questions(self, path_id, paths, topic_name, questions, user_id):
        """Add topic questions to the learning path (delete full deletion + optimistic lock, solve lock waiting)"""
        try:
            # 1. Out-of-transaction preprocessing: Find the target path and modify the content (lock-free operation)
            target_path = None
            for path in paths:
                if 'id' in path and path['id'] == path_id:
                    target_path = path
                    break
            if not target_path:
                logger.warning(f"Target path {path_id} doesn't exist")
                return 0

            # Parse and modify the content (place time-consuming operations outside the transaction)
            content_str = target_path.get('content', '{}')
            if not content_str or not isinstance(content_str, str):
                logger.error(f"Invalid content format for path {path_id}")
                return 0
            
            try:
                content_dict = json.loads(content_str)
            except json.JSONDecodeError as e:
                logger.error(f"Path content JSON parsing failed: {e}, Content: {content_str[:100]}...")
                return 0
            
            topics = content_dict.get('topics', [])
            topic_found = False
            for topic in topics:
                if topic.get('name') == topic_name:
                    topic['questions'] = questions
                    topic_found = True
                    break
            if not topic_found:
                logger.warning(f"path {path_id}, the topic was not found in the text, {topic_name}")
                return 0
            updated_content = json.dumps(content_dict)  # Serialization in advance reduces transaction time

            # 2. Optimistic lock update: Only update the target path
            max_retries = 3
            retry_delay = 0.5
            for attempt in range(max_retries):
                # Query the current version of the target path outside the transaction
                path_data = self.data_manager.execute_query('''
                    SELECT version FROM learning_paths 
                    WHERE id = %s AND user_id = %s
                ''', (path_id, user_id))
                if not path_data:
                    logger.error(f"path {path_id} Version query failed")
                    return 0
                current_version = path_data[0]['version']

                try:
                    row_count = self.data_manager.execute_query('''
                        UPDATE learning_paths 
                        SET content = %s, last_updated = NOW(), version = version + 1  -- Version increment
                        WHERE id = %s AND user_id = %s AND version = %s  -- Update only when the version matches
                    ''', (updated_content, path_id, user_id, current_version))

                    if row_count == 1:
                        self.data_manager.commit_transaction()
                        logger.info(f"path {path_id} ,the topic question has been added successfully（version：{current_version}→{current_version+1}）")
                        return row_count
                    elif row_count == 0:
                        # Version conflict, roll back and retry
                        self.data_manager.rollback_transaction()
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))
                            logger.warning(f"path {path_id} version conflict，retry {attempt+1} times")
                            continue
                        else:
                            logger.error(f"path {path_id} version conflict，the maximum number of retries has been reached")
                            return 0

                except Exception as e:
                    self.data_manager.rollback_transaction()
                    logger.error(f"The transaction to add the topic issue failed：{str(e)}")
                    return 0

        except Exception as e:
            logger.error(f"There are always errors in adding topic questions：{str(e)}")
            return 0
               
    def get_assessments_by_topic(self, user_id, subject, topic):
        """Query assessment records based on user ID, subject and topic"""
        try:
            results = self.data_manager.execute_query('''
                SELECT * FROM assessments 
                WHERE user_id = %s AND subject = %s AND topic_name = %s
            ''', (user_id, subject, topic))
            
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Failed to obtain the topic evaluation record：{str(e)}")
            return None
    
    def insert_assessment_from_state(self, user_id, subject, topic, current_state):
        """Insert the evaluation results from the front-end status data"""
        if not current_state.get('submitted'):
            logger.warning("The assessment has not been submitted, so the result cannot be inserted")
            return {"status": "error", "message": "The assessment was not submitted."}
        try:
            # Verify whether current_state is a serializable object
            if not isinstance(current_state, dict):
                logger.error(f"Invalid current_state format: {type(current_state)}")
                return {"status": "error", "message": "Invalid assessment data format"}
            
            existing_records = self.data_manager.execute_query('''
                SELECT id FROM assessments 
                WHERE user_id = %s AND subject = %s AND topic_name = %s
            ''', (user_id, subject, topic))
            if existing_records:  
                self.data_manager.execute_query('''
                    DELETE FROM assessments 
                    WHERE user_id = %s AND subject = %s AND topic_name = %s
                ''', (user_id, subject, topic))

            assessment_id = self.data_manager.execute_query('''
                INSERT INTO assessments  
                (user_id, subject, topic_name, content, taken_at)  
                VALUES (%s, %s, %s, %s, NOW())
            ''', (user_id, subject, topic, json.dumps(current_state)))
            
            return {"status": "success", "id": assessment_id}
            
        except json.JSONDecodeError as e:
            logger.error(f"Current_state JSON serialization failed: {e}, Data: {str(current_state)[:100]}...")
            return {"status": "error", "message": "Assessment data serialization failed"}
        except Exception as e:
            logger.error(f"The insertion of the evaluation result failed: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def insert_plan_from_json(self, user_id, path_id, study_schedules):
        """Insert the study plan into the database"""
        try:
            # Verify whether study_schedules is a serializable object
            if not isinstance(study_schedules, (dict, list)):
                logger.error(f"Invalid study_schedules format: {type(study_schedules)}")
                return {"status": "error", "message": "Invalid study plan format"}
            
            existing = self.data_manager.execute_query('''
                SELECT 1 FROM study_schedules 
                WHERE user_id = %s AND path_id = %s
                LIMIT 1
            ''', (user_id, path_id))
            
            if existing:  
                self.data_manager.execute_query('''
                    DELETE FROM study_schedules 
                    WHERE user_id = %s AND path_id = %s
                ''', (user_id, path_id))
            
            schedule_id = self.data_manager.execute_query('''
                    INSERT INTO study_schedules 
                    (user_id, path_id, schedule_json, created_at)
                    VALUES (%s, %s, %s, NOW())
                ''', (user_id, path_id, json.dumps(study_schedules)))
            
            return {"status": "success", "id": schedule_id}
        except json.JSONDecodeError as e:
            logger.error(f"Study_schedules JSON serialization failed: {e}, Data: {str(study_schedules)[:100]}...")
            return {"status": "error", "message": "Study plan serialization failed"}
        except Exception as e:
            logger.error(f"The insertion of the study plan failed: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_plan(self, user_id, path_id):
        """Obtain the user's study plan"""
        try:
            results = self.data_manager.execute_query('''
                    SELECT * FROM study_schedules 
                    WHERE user_id = %s AND path_id = %s
            ''', (user_id, path_id))
            
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Failed to obtain the study plan: {str(e)}")
            return None

    # Real-time timing method
    def init_study_timer(self, user_id, path_id, topic_name):
        """
        Initialization timing (called when the web page is opened) : Create a learning activity record of the current user - path - topic
        If a record already exists, return directly to avoid duplicate creation
        """
        try:
            # Check whether the record of this user-path-topic already exists
            query = """
                SELECT id FROM learning_activities 
                WHERE user_id = %s AND path_id = %s AND topic_name = %s
                LIMIT 1
            """
            result = self.data_manager.execute_query(query, (user_id, path_id, topic_name))
            
            if result:
                # Existing records: Return the record ID (for subsequent updates)
                return {"status": "success", "activity_id": result[0]["id"]}
            
            # No record: Insert the initial record (initial duration 0, content marked as "auto_timer")
            insert_query = """
                INSERT INTO learning_activities 
                (user_id, path_id, topic_name, content, total_minutes, activity_date)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """
            activity_id = self.data_manager.execute_query(
                insert_query, 
                (user_id, path_id, topic_name, json.dumps({"status": "auto_timer"}), 0.0)
            )
            
            return {"status": "success", "activity_id": activity_id}
        
        except Exception as e:
            logger.error(f"The initialization timing failed：{str(e)}")
            return {"status": "error", "message": str(e)}

    def update_study_timer(self, user_id, path_id, topic_name, add_minutes):
        """Real-time update timing (supplement optimistic locking to avoid multi-connection conflicts)"""
        try:
            add_minutes = round(float(add_minutes), 2)
            if add_minutes < 0.01:
                return {"status": "error", "message": "The newly added duration must be greater than 0.01 minutes"}
        
            max_retries = 3
            retry_delay = 0.5
            for attempt in range(max_retries):
                # 1. Query the current record (including version number)
                query = """
                    SELECT id, total_minutes, version 
                    FROM learning_activities 
                    WHERE user_id = %s AND path_id = %s AND topic_name = %s
                    LIMIT 1
                """
                result = self.data_manager.execute_query(query, (user_id, path_id, topic_name))
                if not result:
                    init_result = self.init_study_timer(user_id, path_id, topic_name)
                    if init_result["status"] != "success":
                        return init_result
                    # Re-query the initialized record
                    result = self.data_manager.execute_query(query, (user_id, path_id, topic_name))
                    if not result:
                        return {"status": "error", "message": "There is still no record after initializing the timing"}
            
                record = result[0]
                new_total = float(record['total_minutes']) + add_minutes
                current_version = record['version']

                try:
                    row_count = self.data_manager.execute_query("""
                        UPDATE learning_activities 
                        SET total_minutes = %s, activity_date = NOW(), version = version + 1
                        WHERE id = %s AND version = %s
                    """, (new_total, record['id'], current_version))

                    if row_count == 1:
                        self.data_manager.commit_transaction()
                        total_time = self.get_total_study_time(user_id)
                        return {"status": "success", "total_study_time": round(total_time, 2)}
                    else:
                        self.data_manager.rollback_transaction()
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        raise Exception("Version conflict, update duration failed")
                except Exception as e:
                    self.data_manager.rollback_transaction()
                    raise e

            return {"status": "error", "message": "Reach the maximum number of retries"}
        except Exception as e:
            logger.error(f"Failed to update the timing：{str(e)}")
            return {"status": "error", "message": str(e)}

    def get_total_study_time(self, user_id):
        """
        Obtain the total learning duration of the user (for real-time display) : Calculate the total total_minutes of all learning activities of this user
        Return: Total duration (unit: minutes)
        """
        try:
            query = """
                SELECT COALESCE(SUM(total_minutes), 0) AS total 
                FROM learning_activities 
                WHERE user_id = %s
            """
            result = self.data_manager.execute_query(query, (user_id,))
            # Make sure to return a floating-point number
            return float(result[0]["total"]) if result else 0.0
        
        except Exception as e:
            logger.error(f"Failed to query the total duration：{str(e)}")
            return 0.0

    # Learn to analyze statistical logic
    def get_learning_analytics(self, user_id, completed_paths):
        """Obtain user learning analysis data"""
        try:
            # 1. Query all evaluation records from the database (persistent data)
            db_assessments = self.data_manager.execute_query('''
                SELECT id, user_id, subject, topic_name, content, taken_at 
                FROM assessments 
                WHERE user_id = %s
            ''', (user_id,))
            
            # 2. Parse the database evaluation data into the standard format
            assessment_results = []
            for db_assessment in db_assessments:
                try:
                    content_str = db_assessment.get('content', '{}')
                    if not content_str or not isinstance(content_str, str):
                        logger.warning(f"Invalid content for assessment {db_assessment['id']}")
                        continue
                    content = json.loads(content_str)  # Parse the JSON stored in the database
                    valid_scores = [s for s in content.get('scores', []) if isinstance(s, (int, float))]
                    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
                    
                    assessment_results.append({
                        "user_id": user_id,
                        "subject": db_assessment['subject'],
                        "topic": db_assessment['topic_name'],  
                        "score": avg_score,
                        "date": db_assessment['taken_at'].strftime("%Y-%m-%d"),
                        "difficulty": "Intermediate"
                    })
                except json.JSONDecodeError as e:
                    logger.error(f"Assessment data parsing failed（ID: {db_assessment['id']}）: {e}, Content: {content_str[:100]}...")
                    continue

            # 3. The logic for reading other data remains unchanged
            activities_query = '''
                SELECT topic_name, DATE_FORMAT(activity_date, '%%Y-%%m-%%d') AS date, total_minutes  
                FROM learning_activities 
                WHERE user_id = %s 
                ORDER BY activity_date DESC
            '''
            real_activities = self.data_manager.execute_query(activities_query, (user_id,))
            
            streaks_query = '''
                SELECT current_streak_days, longest_streak_days 
                FROM study_streaks 
                WHERE user_id = %s
            '''
            real_streaks = self.data_manager.execute_query(streaks_query, (user_id,))
            streak_data = real_streaks[0] if real_streaks else {"current_streak_days": 0, "longest_streak_days": 0}

            total_study_time = self.get_total_study_time(user_id)

            return {
                "streaks": streak_data,
                "paths": self.get_learning_paths(user_id),
                "activities": real_activities,
                "assessments": assessment_results,  # Now use database data
                "total_study_time": total_study_time
            }
        except Exception as e:
            logger.error(f"Failed to obtain the learning analysis data：{str(e)}")
            return {"status": "error", "message": str(e)}

class MockAssessmentManager:
    """Evaluation management category, handling the generation of practice questions and the assessment of answers"""
    import re  

    def generate_practice_exercises(self, subject, topic, difficulty_level, ai_agent, num_exercises=3):
        """Generate practice questions based on the learning topic (with JSON error tolerance)"""
        prompt = f"""
        You are an education expert and need to create random practice questions (in English) for the following learning topics.：
        Subject: {subject}
        Theme: {topic}
        Difficulty: {difficulty_level}
        The number of questions: {num_exercises}

        Requirement
        1.Each generated question must be different from the previous result to avoid repetitive questions or similar options.
        2. The problem expressions are diverse, and the order of the options is randomly arranged.
        3. Cover the key concepts of the theme, with difficulty matching the specified level;
        4. The question should not be "excluded multiple choice questions (also called negative screening questions), and the exceptional options that" do not meet the requirements of the question stem and are not within the scope of the question stem "can not be found from multiple options.
        
        
        Return the result in JSON format. The structure is as follows:
        {{
            "exercises": [
                {{
                    "question": "Title text",
                    "type": "Single-choice question",
                    "options": ["Options1", "Options2", "Options3", "Options4"],  
                    "correct_option": 0,
                    "explanation": "Answer Analysis",
                    "difficulty": "Beginner/Intermediate/Advanced",
                    "estimated_time_minutes": 10-30
                }}
            ]
        }}
        Ensure JSON syntax is valid: no trailing commas, closed quotes, correct commas between elements.
        """

        messages = [
            {"role": "system", "content": "You are an education expert, creating high-quality learning random practice questions. Your output must be VALID JSON - no trailing commas, closed quotes, correct commas between array/object elements."},
            {"role": "user", "content": prompt}
        ]

        def fix_common_json_errors(json_str):
            """Fix common JSON syntax errors"""
            json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
            # Remove the redundant trailing commas
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            # Fix the unclosed double quotation marks
            quote_count = json_str.count('"')
            if quote_count % 2 != 0:
                json_str = json_str.rstrip().rstrip('"') + '"'
            # Replace Chinese parentheses with English parentheses
            json_str = json_str.replace('（', '(').replace('）', ')')
            return json_str

        try:
            response = ai_agent._call_api(messages, response_format={"type": "json_object"})
            if not response or not isinstance(response, str):
                logger.warning(f"AI returned invalid response for practice exercises: {response}")
                raise ValueError("Invalid AI response format")
            
            # Clean up and fix the response
            clean_response = response.strip().strip('`').strip('json').strip()
            fixed_response = fix_common_json_errors(clean_response)
            
            # Try to parse the repaired JSON
            data = json.loads(fixed_response)
            
            # Verify the structure and supplement the missing fields
            if "exercises" not in data or not isinstance(data["exercises"], list):
                logger.warning(f"AI response missing 'exercises' field: {data}")
                raise ValueError("Missing exercises field")
            
            # Make sure that each exercise field is complete
            valid_exercises = []
            for exercise in data["exercises"]:
                required_fields = ["question", "type", "options", "correct_option", "explanation", "difficulty", "estimated_time_minutes"]
                if all(field in exercise for field in required_fields):
                    # Make sure the number of options is 4
                    if len(exercise["options"]) < 4:
                        exercise["options"] += [f"Option {i+1}" for i in range(len(exercise["options"]), 4)]
                    elif len(exercise["options"]) > 4:
                        exercise["options"] = exercise["options"][:4]
                    # Ensure that the correct option index is legal
                    exercise["correct_option"] = max(0, min(3, int(exercise["correct_option"])))
                    valid_exercises.append(exercise)
            
            if not valid_exercises:
                logger.warning("No valid exercises found after validation")
                raise ValueError("No valid exercises")
            
            return {"status": "success", "exercises": valid_exercises[:num_exercises]}
        
        except json.JSONDecodeError as e:
            logger.error(f"Practice questions JSON parsing failed (after fix): {e}, Response: {fixed_response[:300]}...")
        except ValueError as e:
            logger.error(f"Exercise validation failed: {e}")
        except Exception as e:
            logger.error(f"Failed to generate the practice questions: {str(e)}")
        
        # Return the default practice questions when parsing fails (to avoid function crash)
        default_exercises = self._get_default_exercises(subject, topic, difficulty_level, num_exercises)
        return {"status": "success", "exercises": default_exercises, "message": "Used default exercises due to AI response error"}

    def _get_default_exercises(self, subject, topic, difficulty_level, num_exercises):
        """Generate default practice questions as a demotion solution"""
        default_options = [
            f"{topic} ,Network issue. Please regenerate",
            f"{topic} ,Network issue. Please regenerate",
            f"{topic} ,Network issue. Please regenerate",
            f"{topic} ,Network issue. Please regenerate"
        ]
        exercises = []
        for i in range(num_exercises):
            exercises.append({
                "question": f"What is the key principle of {topic} in {subject}? (Q{i+1})",
                "type": "multiple_choice",
                "options": default_options.copy(),
                "correct_option": i % 4,
                "explanation": f"This question tests understanding of {topic}'s core principles in {subject}. The correct answer is option {default_options[i%4]}.",
                "difficulty": difficulty_level.capitalize() if difficulty_level else "Intermediate",
                "estimated_time_minutes": 15 + i * 5
            })
        return exercises
    
    def evaluate_answer(self, subject, topic, question, user_answer, difficulty_level, ai_agent):
        """Use AI to evaluate open-ended answers"""
        prompt = f"""
        You are an AI education expert and need to evaluate students' responses to the following questions (in English).：
        Subject: {subject}
        Theme: {topic}
        Difficulty: {difficulty_level}
        Question: {question}
        user answer: {user_answer}
        
        Please evaluate according to the following criteria:
        Based on the analysis of the question, if the answer is correct, there will be points.

      
        Return the result in JSON format：
        {{
            "score": 0.0-1.0,
            "feedback": "Specific feedback and improvement suggestions for the answers",
            "explanation": "Explanation of the problem (as concise as possible)"
        }}
        """
        
        messages = [
            {"role": "system", "content": "You are an AI education expert who assesses students' learning outcomes and provides constructive feedback. Your output must be valid JSON with score (0.0-1.0), feedback, and explanation fields."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = ai_agent._call_api(messages, response_format={"type": "json_object"})
            if not response or not isinstance(response, str):
                logger.warning(f"AI returned invalid response for answer evaluation: {response}")
                # Return the default evaluation result
                return {
                    "status": "success",
                    "data": {
                        "score": 0,
                        "feedback": "Network issue, resolution failed. Please refer to the correct answer",
                        "explanation": f"Complete some evaluations to obtain personalized suggestions on {topic}"
                    }
                }
            
            # Clean up the response content
            clean_response = response.strip().strip('`').strip('json').strip()
            evaluation_data = json.loads(clean_response)
            
            # Verify the necessary fields
            required_fields = ["score", "feedback", "explanation"]
            if not all(field in evaluation_data for field in required_fields):
                logger.warning(f"Evaluation response missing required fields: {evaluation_data}")
                raise ValueError("Missing required evaluation fields")
            
            # Verify the score range
            if not isinstance(evaluation_data["score"], (int, float)) or evaluation_data["score"] < 0 or evaluation_data["score"] > 1:
                logger.warning(f"Invalid score value: {evaluation_data['score']}")
                evaluation_data["score"] = 0.7
            
            return {"status": "success", "data": evaluation_data}
        except json.JSONDecodeError as e:
            logger.error(f"Answer evaluation JSON parsing failed: {e}, Response: {response[:200]}...")
        except ValueError as e:
            logger.error(f"Invalid evaluation data: {e}")
        except Exception as e:
            logger.error(f"The evaluation answer failed: {str(e)}")
        
        # Return the default evaluation logic when the parsing fails
        return {
            "status": "success",
            "data": {
                "score": 0,
                "feedback": "Network issue, resolution failed. Please refer to the correct answer",
                "explanation": f"Complete some evaluations to obtain personalized suggestions on {topic}"
            }
        }
    
    def save_assessment_result(self, assessment_results, user_id, subject, topic, score, feedback, difficulty_level):
        """Save the assessment results"""
        try:
            assessment_results.append({
                "user_id": user_id,
                "subject": subject,
                "topic": topic,
                "score": score,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "difficulty": difficulty_level,
                "feedback": feedback
            })
            return assessment_results
        except Exception as e:
            logger.error(f"Failed to save the assessment result: {str(e)}")
            return None
    
    def get_weakness_areas(self, user_id, assessment_results, activities=None):
            """Analyze the areas of weakness（动态生成 learning_patterns）"""
            try:
                # 1. Receive learning activity data (optional parameter, the user's learning records passed in when externally called)
                activities = activities or []
                
                # 2. Filter the valid evaluation data of the current user
                user_assessments = []
                for a in assessment_results:
                    if all(key in a for key in ["user_id", "topic", "score"]) and a["user_id"] == user_id:
                        score = max(0.0, min(1.0, float(a["score"])))
                        user_assessments.append({
                            "topic": a["topic"],
                            "score": score,
                            "subject": a.get("subject", "Unknown"),
                            "assessment_date": a.get("date", datetime.now().strftime("%Y-%m-%d"))
                        })
                
                # 3. Return the default structure (including default learning_patterns) when there is no evaluation data
                if not user_assessments:
                    return {
                        "strong_topics": [],
                        "weak_topics": [],
                        "recommendations": {
                            "strategies": ["No assessment data is available. Complete some evaluations to obtain personalized suggestions."]
                        },
                        "learning_patterns": {
                            "time_score_correlation": 0.65,
                            "optimal_duration": 45,
                            "optimal_time": "3 p.m. to 5 p.m"
                        }
                    }
                
                # 4. Calculate the strength of the topic 
                topic_scores = {}
                for assessment in user_assessments:
                    topic = assessment["topic"]
                    if topic not in topic_scores:
                        topic_scores[topic] = []
                    topic_scores[topic].append(assessment["score"])
                
                strong_topics = [
                    {"topic": t, "avg_score": round(sum(s)/len(s), 2)} 
                    for t, s in topic_scores.items() 
                    if sum(s)/len(s) >= 0.8
                ]
                weak_topics = [
                    {"topic": t, "avg_score": round(sum(s)/len(s), 2)} 
                    for t, s in topic_scores.items() 
                    if sum(s)/len(s) < 0.7
                ]
                
                # 5. Generate personalized suggestions 
                recommendations = []
                for weak in weak_topics:
                    recommendations.append(f"For '{weak['topic']}'（Average score{weak['avg_score']}），Strengthen the consolidation of basic concepts and targeted practice")
                for strong in strong_topics:
                    recommendations.append(f"For '{strong['topic']}'（Average score{strong['avg_score']}），One can try cross-topic associative learning to expand the boundaries of knowledge")
                
                # 6. Dynamic computational learning mode
                learning_patterns = self._calculate_learning_patterns(user_assessments, activities)
                
                return {
                    "strong_topics": strong_topics,
                    "weak_topics": weak_topics,
                    "recommendations": {"strategies": recommendations},
                    "learning_patterns": learning_patterns
                }
            except Exception as e:
                logger.error(f"Failure in analyzing weaknesses: {str(e)}")
                return {"status": "error", "message": str(e)}

    def _calculate_learning_patterns(self, user_assessments, activities):
            """Auxiliary method: Dynamically calculate the learning mode indicators based on the actual user data"""
            # Initialize the default value (as a fallback when data is insufficient)
            patterns = {
                "time_score_correlation": 0.62,
                "optimal_duration": 50,
                "optimal_time": "2.30 p.m. to 4.30 p.m"
            }
            
            # Return the default value directly when there is no learning activity data
            if not activities:
                return patterns
            
            # 1. Calculate the "correlation between learning time and score" (between 0 and 1, the closer to 1, the stronger the correlation)
            topic_duration_map = {}
            for activity in activities:
                topic = activity.get("topic_name")
                duration = float(activity.get("total_minutes", 0))
                if topic and duration > 0:
                    if topic not in topic_duration_map:
                        topic_duration_map[topic] = 0
                    topic_duration_map[topic] += duration
            
            # Filter topics that have both scores and duration
            correlated_data = []
            for assessment in user_assessments:
                topic = assessment["topic"]
                if topic in topic_duration_map and topic_duration_map[topic] > 0:
                    correlated_data.append({
                        "duration": topic_duration_map[topic] / 60,  # Convert to hours
                        "score": assessment["score"]
                    })
            
            # Calculate the Pearson correlation coefficient
            if len(correlated_data) >= 2:
                durations = [d["duration"] for d in correlated_data]
                scores = [d["score"] for d in correlated_data]
                avg_duration = sum(durations) / len(durations)
                avg_score = sum(scores) / len(scores)
                
                numerator = sum((d - avg_duration) * (s - avg_score) for d, s in zip(durations, scores))
                denominator = (sum((d - avg_duration)**2 for d in durations) * sum((s - avg_score)**2 for s in scores))**0.5
                
                if denominator != 0:
                    correlation = abs(numerator / denominator)
                    patterns["time_score_correlation"] = round(correlation, 2)
            
            # 2. Calculate the "optimal single learning duration"
            valid_durations = [
                float(activity.get("total_minutes", 0)) 
                for activity in activities 
                if float(activity.get("total_minutes", 0)) > 10  # Filter out invalid records that are less than 10 minutes
            ]
            if valid_durations:
                valid_durations.sort()
                mid_idx = len(valid_durations) // 2
                patterns["optimal_duration"] = int(valid_durations[mid_idx])
            
            # 3. Calculate the "optimal learning time period"
            hour_counts = {}
            for activity in activities:
                activity_date = activity.get("date")
                if activity_date:
                    try:
                        # Parse the hours in the date (supports formats "YYYY-MM-DD" or "YYYY-MM-DD HH:MM")
                        if " " in activity_date:
                            hour = int(activity_date.split(" ")[1].split(":")[0])
                        else:
                            # When there is no time, infer based on the corresponding topic score (high score → afternoon, low score → morning)
                            topic = activity.get("topic_name")
                            topic_score = next((a["score"] for a in user_assessments if a["topic"] == topic), 0)
                            hour = 15 if topic_score >= 0.8 else 10
                        if 0 <= hour < 24:
                            hour_counts[hour] = hour_counts.get(hour, 0) + 1
                    except:
                        continue
            
            # Mapping period
            if hour_counts:
                optimal_hour = max(hour_counts, key=hour_counts.get)
                if 9 <= optimal_hour <= 11:
                    patterns["optimal_time"] = "9 a.m. to 12 p.m"
                elif 12 <= optimal_hour <= 14:
                    patterns["optimal_time"] = "12 p.m. to 3 p.m"
                elif 15 <= optimal_hour <= 17:
                    patterns["optimal_time"] = "3 p.m. to 6 p.m"
                elif 18 <= optimal_hour <= 21:
                    patterns["optimal_time"] = "6 p.m. to 9 p.m"
            
            return patterns

# Real AI agent class
class DeepSeekAIAgent:
    """DeepSeek AI agent, handling AI-related learning assistance functions"""
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-chat"
        self.temperature = 2  # Reduce randomness and enhance the stability of the JSON format
        self.max_retries = 3
        self.retry_delay = 2  # Initial retry delay (in seconds)

    def _call_api(self, messages, response_format=None):
        """Call the DeepSeek API with a retry mechanism"""
        if not self.api_key:
            logger.warning("The DeepSeek API cannot be invoked without providing the API key")
            return None
            
        client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        
        for attempt in range(self.max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    response_format=response_format,
                    timeout=60  # 60-second timeout
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"API call failed (Try {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    # Exponential backoff retry
                    delay = self.retry_delay * (2 ** attempt)
                    logger.info(f"Wait {delay} seconds, try again...")
                    time.sleep(delay)
                    continue
                return None
        return None

    def generate_motivational_message(self, user_id, context):
        """Generate learning motivation information"""
        prompt = f"""
        The student's recent study situation: {context}
        Create a short and inspiring learning motivation message.
        Stay positive and inspiring, and don't take too long.
        Focus on persistence, progress rather than perfection, and the value of continuous effort.
        
        Return the result in JSON format, including the following keys:
        {{
            "message": "<Incentive information>",
            "quote": "<Inspirational quotes related to study>"
        }}
        """
        
        messages = [
            {"role": "system", "content": "You are an AI learning assistant, helping students stay motivated. Your output must be valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_api(messages, response_format={"type": "json_object"})
            if not response or not isinstance(response, str):
                logger.warning(f"AI returned invalid response for motivational message: {response}")
                raise ValueError("Invalid response")
            
            return {"status": "success", "data": json.loads(response.strip())}
        except json.JSONDecodeError as e:
            logger.error(f"Motivational message JSON parsing failed: {e}, Response: {response[:200]}...")
        except Exception as e:
            logger.error(f"Failed to generate incentive information: {str(e)}")
        
        # Return the default value when it fails
        return {
            "status": "success",
            "data": {
                "message": "Keep up the good work! Make a little progress every day and you will see huge changes.",
                "quote": "Learning is not filling a bucket, but lighting a fire."
            }
        }

    def generate_study_reminder(self, user_id):
        """Generate learning reminders"""
        prompt = """
        Create a friendly study reminder.
        Keep it simple but helpful. It includes suggestions for the content to be focused on next.
        
        Return the result in JSON format, including the following keys:
        {
            "reminder": "<Reminder message>",
            "suggested_focus": "<Suggested content to pay attention to>"
        }
        """
        
        messages = [
            {"role": "system", "content": "You are an AI learning assistant, helping students plan their studies. Your output must be valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_api(messages, response_format={"type": "json_object"})
            if not response or not isinstance(response, str):
                logger.warning(f"AI returned invalid response for study reminder: {response}")
                raise ValueError("Invalid response")
            
            return {"status": "success", "data": json.loads(response.strip())}
        except json.JSONDecodeError as e:
            logger.error(f"Study reminder JSON parsing failed: {e}, Response: {response[:200]}...")
        except Exception as e:
            logger.error(f"Failed to generate a learning reminder: {str(e)}")
        
        # Return the default value when it fails
        return {
            "status": "success",
            "data": {
                "reminder": "Don't forget today's study! Thirty minutes a day can make a significant difference.",
                "suggested_focus": "Review the content learned yesterday"
            }
        }

    def generate_study_schedule(self, deadline=None, hours_per_day=120, topics=None, subject=None, focus=None):
        """Generate a learning plan based on the user's learning path"""
        subject = subject if subject else "various subject"
        topics_str = str(topics) if topics else "various topics"
        focus = focus if focus else "various focus areas"
        deadline_str = f"by {deadline.strftime('%Y-%m-%d')}" if deadline else "in the next two weeks"
        
        prompt = f"""
        Create a daily study plan for students
        ▪ Subject: {subject}
        ▪ Topics: {topics_str}
        ▪ Hours: {hours_per_day} minutes
        ▪ Deadline: {deadline_str}
        ▪ Focus: {focus}
        
        The plan should include:
        ▪ Balanced learning modules
        ▪ Review Session
        ▪ Short break
        ▪ Clear theme arrangement
        Take a week as a cycle and arrange a different study plan for each day
        
        Return the result in JSON format, including the following structure:
        {{
            "daily_schedule": [
                {{
                    "day": "Monday",
                    "study_blocks": [
                        {{
                            "subject": "<Subject>",
                            "topic": "<topic>",
                            "duration_minutes": <minutes>,
                            "focus_area": "<area>"
                        }}
                    ]
                }},
                {{
                    "day": "Tuesday",
                    "study_blocks": [
                        {{
                            "subject": "<Subject>",
                            "topic": "<topic>",
                            "duration_minutes": <minutes>,
                            "focus_area": "<area>"
                        }}
                    ]
                }},
                {{
                    "day": "Wednesday",
                    "study_blocks": [
                        {{
                            "subject": "<Subject>",
                            "topic": "<topic>",
                            "duration_minutes": <minutes>,
                            "focus_area": "<area>"
                        }}
                    ]
                }},
                {{
                    "day": "Thursday",
                    "study_blocks": [
                        {{
                            "subject": "<Subject>",
                            "topic": "<topic>",
                            "duration_minutes": <minutes>,
                            "focus_area": "<area>"
                        }}
                    ]
                }},
                {{
                    "day": "Friday",
                    "study_blocks": [
                        {{
                            "subject": "<Subject>",
                            "topic": "<topic>",
                            "duration_minutes": <minutes>,
                            "focus_area": "<area>"
                        }}
                    ]
                }},
                {{
                    "day": "Saturday",
                    "study_blocks": [
                        {{
                            "subject": "<Subject>",
                            "topic": "<topic>",
                            "duration_minutes": <minutes>,
                            "focus_area": "<area>"
                        }}
                    ]
                }},
                {{
                    "day": "Sunday",
                    "study_blocks": [
                        {{
                            "subject": "<Subject>",
                            "topic": "<topic>",
                            "duration_minutes": <minutes>,
                            "focus_area": "<area>"
                        }}
                    ]
                }}
            ],
            "productivity_tips": [
                "<Efficiency Tip 1>",
                "<Efficiency Tip 2>"
            ]
        }}
        """
        
        messages = [
            {"role": "system", "content": "You are an AI learning assistant, creating personalized study plans for students. Your output must be valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_api(messages, response_format={"type": "json_object"})
            if not response or not isinstance(response, str):
                logger.warning(f"AI returned invalid response for study schedule: {response}")
                raise ValueError("Invalid response")
            
            return {"status": "success", "data": json.loads(response.strip())}
        except json.JSONDecodeError as e:
            logger.error(f"Study schedule JSON parsing failed: {e}, Response: {response[:200]}...")
        except Exception as e:
            logger.error(f"The generation of the study plan failed: {str(e)}")
        
        # Return the default value when it fails
        first_topic = "Basic knowledge"
        return {
            "status": "success",
            "data": {
                "daily_schedule": [
                    {
                        "day": "Monday",
                        "study_blocks": [
                            {
                                "subject": subject,
                                "topic": first_topic,
                                "duration_minutes": 60,
                                "focus_area": "Concept Review"
                            },
                            {
                                "subject": subject,
                                "topic": "Practice Exercises",
                                "duration_minutes": 40,
                                "focus_area": "Problem Solving"
                            },
                            {
                                "subject": "Break",
                                "topic": "Rest",
                                "duration_minutes": 13,
                                "focus_area": "Relaxation"
                            }
                        ]
                    },
                    {
                        "day": "Tuesday",
                        "study_blocks": [
                            {
                                "subject": subject,
                                "topic": "Advanced Concepts",
                                "duration_minutes": 60,
                                "focus_area": "Deep Understanding"
                            },
                            {
                                "subject": subject,
                                "topic": "Case Studies",
                                "duration_minutes": 40,
                                "focus_area": "Application"
                            }
                        ]
                    }
                ],
                "productivity_tips": [
                    "Take a 5-minute break every 25 minutes of study",
                    "Review the previous content before starting a new topic"
                ]
            }
        }

    def handle_assistance_request(self, user_id, subject, topic, question):
        """Handle requests for learning assistance"""
        prompt = f"""
        Students need help.:
        Subject: {subject}
        Topic: {topic}
        Question: {question}
        
        Please provide a detailed answer, including:
        ▪ A clear answer to the question
        ▪ Key concepts that need to be understood
        ▪ Additional resources for further study
        ▪ Follow-up questions for deepening understanding
        
        Return the result in JSON format, including the following keys:
        {{
            "answer": "<Detailed answer>",
            "key_concepts": ["Concept1", "Concept2", ...],
            "additional_resources": [
                {{
                    "title": "<Resource Title>",
                    "description": "<Resource description>",
                    "url": "<Resource URL>"
                }}
            ],
            "follow_up_questions": ["question1", "question2", ...]
        }}
        """
        
        messages = [
            {"role": "system", "content": "You are an AI mentor, providing detailed explanations and learning resources. Your output must be valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_api(messages, response_format={"type": "json_object"})
            if not response or not isinstance(response, str):
                logger.warning(f"AI returned invalid response for assistance request: {response}")
                raise ValueError("Invalid response")
            
            return {"status": "success", "data": json.loads(response.strip())}
        except json.JSONDecodeError as e:
            logger.error(f"Assistance request JSON parsing failed: {e}, Response: {response[:200]}...")
        except Exception as e:
            logger.error(f"Failed to handle the help request: {str(e)}")
        
        # Return the default value when it fails
        return {
            "status": "success",
            "data": {
                "answer": f"Basic {subject}, {topic}: {question}. This concept can be divided into three main parts: 1) Basic elements, 2) practical applications, and 3) common misunderstandings. Understanding these components will help you master the material more effectively.",
                "key_concepts": [f"{topic} basics", f"advanced {subject} concepts"],
                "additional_resources": [
                    {
                        "title": f"{topic}: A Complete Guide",
                        "description": f"Comprehensive resources covering all aspects of {subject} {topic}",
                        "url": f"https://example.com/{subject.lower()}/{topic.lower()}"
                    }
                ],
                "follow_up_questions": [
                    f"How to connect {topic} with other {subject} concepts?",
                    f"What are the common mistakes when using {topic}?"
                ]
            }
        }
    
    def chat(self, messages):
        """Handle dialogue interactions with students"""
        system_message = {
            "role": "system", 
            "content": "You are an AI learning assistant, named ASC (Adaptive Study Companion). You help students learn various subjects, answer questions and provide explanations. Please keep your answers clear and detailed, and answer users' questions in Chinese."
        }
        
        # Build a complete dialogue history (including system messages)
        full_conversation = [system_message] + messages
        
        try:
            response = self._call_api(full_conversation)
            if not response:
                return {"status": "error", "message": "The AI response cannot be obtained"}
            
            # Return a plain text reply
            return {"status": "success", "response": response}
        except Exception as e:
            logger.error(f"Dialogue interaction error: {str(e)}")
            return {"status": "error", "message": f"An error occurred during AI interaction: {str(e)}"}

class MockAssistanceTracker:
    """Learn the help tracker to record and query help requests"""
    @staticmethod
    def record_assistance_request(assistance_requests, user_id, subject, topic, question):
        """Record help requests"""
        try:
            request = {
                "id": len(assistance_requests) + 1,
                "user_id": user_id,
                "subject_area": subject,
                "topic": topic,
                "question": question,
                "request_time": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            assistance_requests.append(request)
            return assistance_requests
        except Exception as e:
            logger.error(f"Record the failed help request: {str(e)}")
            return None
    
    @staticmethod
    def get_recent_requests(assistance_requests, user_id, limit=5):
        """Get the most recent help request"""
        try:
            user_requests = [r for r in assistance_requests if r["user_id"] == user_id]
            return sorted(user_requests, key=lambda x: x["request_time"], reverse=True)[:limit]
        except Exception as e:
            logger.error(f"Failed to obtain the latest help request: {str(e)}")
            return []

class MockPDFGenerator:
    """PDF generator, generating certificates and study reports"""
    @staticmethod
    def generate_certificate(recipient_name, course_name, completion_date, logo_path=None):
        """Generate the PDF of the completion certificate"""
        try:
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            width, height = letter
            
            c.setFillColorRGB(0.95, 0.95, 1.0)
            c.rect(0, 0, width, height, fill=1)
            c.setStrokeColorRGB(0.2, 0.4, 0.8)
            c.setLineWidth(2)
            c.rect(1*inch, 1*inch, width-2*inch, height-2*inch)
            
            c.setFont("Helvetica-Bold", 36)
            c.setFillColorRGB(0.1, 0.1, 0.5)
            c.drawCentredString(width/2, height - 2.5*inch, "CERTIFICATE OF COMPLETION")
            
            c.setFont("Helvetica-Bold", 24)
            c.drawCentredString(width/2, height - 3.5*inch, "Adaptive Study Companion")
            
            c.setFont("Helvetica", 16)
            c.drawCentredString(width/2, height - 5*inch, "This is to certify that")
            
            c.setFont("Helvetica-Bold", 28)
            c.drawCentredString(width/2, height - 6*inch, recipient_name)
            
            c.setFont("Helvetica", 16)
            c.drawCentredString(width/2, height - 7*inch, f"has successfully completed the course:")
            
            c.setFont("Helvetica-Bold", 20)
            c.drawCentredString(width/2, height - 7.75*inch, course_name)
            
            c.setFont("Helvetica", 12)
            c.drawString(2*inch, 3*inch, f"Date: {completion_date}")
            
            cert_number = f"CERT-{uuid.uuid4().hex[:8].upper()}"
            c.drawString(width - 4*inch, 3*inch, f"Certificate Number: {cert_number}")
            
            c.setFont("Helvetica", 14)
            c.drawString(width - 4*inch, 4.5*inch, "Authorized Signature")
            c.line(width - 4*inch, 4.3*inch, width - 2*inch, 4.3*inch)
            
            c.save()
            buffer.seek(0)
            return {"status": "success", "buffer": buffer, "cert_number": cert_number}
        except Exception as e:
            logger.error(f"Failed to generate the certificate: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def generate_study_report(user_id, username, analytics):
        """Generate a PDF study report"""
        try:
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            width, height = letter
            
            c.setFont("Helvetica-Bold", 24)
            c.drawCentredString(width/2, height - 1*inch, "Learning Progress Report")
            
            c.setFont("Helvetica", 16)
            c.drawString(1.5*inch, height - 2.5*inch, f"Student: {username}")
            c.drawString(1.5*inch, height - 3*inch, f"Report Date: {datetime.now().strftime('%Y-%m-%d')}")
            
            c.setFont("Helvetica-Bold", 18)
            c.drawString(1.5*inch, height - 4.5*inch, "Study Statistics")
            
            c.setFont("Helvetica", 14)
            # Use the total learning duration calculated in real time in analytics
            total_minutes = float(analytics.get("total_study_time", 0))
            c.drawString(2*inch, height - 5.5*inch, f"Current path learning time: {total_minutes // 60}h {total_minutes % 60:.0f}m")
            
            if analytics['streaks']:
                c.drawString(2*inch, height - 6*inch, f"Current Streak: {analytics['streaks']['current_streak_days']} days")
                c.drawString(2*inch, height - 6.5*inch, f"Longest Streak: {analytics['streaks']['longest_streak_days']} days")
            
            c.setFont("Helvetica-Bold", 18)
            c.drawString(1.5*inch, height - 8*inch, "Learning Paths")
            
            y_position = height - 9*inch
            for i, path in enumerate(analytics['paths'][:3]):
                c.drawString(2*inch, y_position, f"{path['subject']}: {path['progress']*100:.1f}% complete")
                y_position -= 0.5*inch
                if y_position < 1*inch:
                    c.showPage()
                    y_position = height - 1.5*inch
            
            c.save()
            buffer.seek(0)
            return {"status": "success", "buffer": buffer}
        except Exception as e:
            logger.error(f"Failed to generate the learning report: {str(e)}")
            return {"status": "error", "message": str(e)}

class MockLearningAnalytics:
    """Learning analysis category, generating visualization charts of learning data"""
    @staticmethod
    def generate_activity_heatmap(activities):
        """Generate a heat map of learning activities"""
        try:
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            hours = list(range(24))
            
            z = np.zeros((7, 24))
            for activity in activities:
                day_idx = np.random.randint(0, 7)
                hour_idx = np.random.randint(10, 23)
                # Convert the duration to hours
                total_minutes = float(activity["total_minutes"])
                z[day_idx, hour_idx] += total_minutes / 60
            
            fig = go.Figure(data=go.Heatmap(
                z=z,
                x=hours,
                y=days,
                colorscale=[MORANDI_COLORS['light'], MORANDI_COLORS['primary'], MORANDI_COLORS['accent']],
                colorbar=dict(title="Hours Studied")
            ))
            
            fig.update_layout(
                title="Study Activity Heatmap",
                xaxis_title="Hour of Day",
                yaxis_title="Day of Week",
                height=600,
                font=dict(size=16)
            )
            return {"status": "success", "figure": fig}
        except Exception as e:
            logger.error(f"Failed to generate the activity heat map: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def generate_progress_chart(paths):
        """Generate a learning progress chart"""
        try:
            fig = go.Figure()
            for path in paths:
                dates = pd.date_range(end=datetime.now(), periods=3)
                progress = np.linspace(0, path['progress'], 3)
                
                fig.add_trace(go.Scatter(
                    x=dates,
                    y=progress*100,
                    mode='lines+markers',
                    name=path['subject'],
                    line=dict(color=MORANDI_COLORS['primary'], width=4),
                    marker=dict(size=3)
                ))
            
            fig.update_layout(
                title="Learning Progress Over Time",
                xaxis_title="Date",
                yaxis_title="Progress (%)",
                yaxis=dict(range=[0, 100]),
                height=600,
                font=dict(size=16)
            )
            return {"status": "success", "figure": fig}
        except Exception as e:
            logger.error(f"Failed to generate the progress chart: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def generate_assessment_radar(assessments):
        """Generate a radar chart for evaluating performance"""
        try:
            topics = list(set(a['topic'] for a in assessments))
            scores = [sum(a['score'] for a in assessments if a['topic'] == t)/
                      sum(1 for a in assessments if a['topic'] == t) for t in topics]
            
            if not topics:
                return {"status": "error", "message": "There is no assessment data available to generate a radar chart"}
                
            fig = go.Figure()
            
            fig.add_trace(go.Scatterpolar(
                r=[s*100 for s in scores],
                theta=topics,
                fill='toself',
                name='Performance',
                line=dict(color=MORANDI_COLORS['primary'], width=4)
            ))
            
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 100],
                        tickfont=dict(size=14)
                    ),
                    angularaxis=dict(
                        tickfont=dict(size=14)
                    )
                ),
                title="Assessment Performance by Topic",
                height=600,
                font=dict(size=16)
            )
            return {"status": "success", "figure": fig}
        except Exception as e:
            logger.error(f"The generation of the assessment radar chart failed: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def identify_learning_patterns(activities, assessments):
        """Identify learning patterns and trends"""
        try:
            if not activities or not assessments:
                return {"status": "warning", "message": "Lack of activity or assessment data", "data": {}}
                
            activity_df = pd.DataFrame(activities)
            topic_scores = {}
            for topic in activity_df['topic_name'].unique():
                topic_assessments = [a for a in assessments if a['topic'] == topic]
                if topic_assessments:
                    avg_score = sum(a['score'] for a in topic_assessments) / len(topic_assessments)
                    topic_scores[topic] = avg_score
            
            sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)[:6]
            
            return {
                "status": "success",
                "data": {
                    'top_topics': [{'topic': t, 'avg_score': s} for t, s in sorted_topics],
                    'time_score_correlation': 0.6
                }
            }
        except Exception as e:
            logger.error(f"Failed to identify the learning mode: {str(e)}")
            return {"status": "error", "message": str(e)}