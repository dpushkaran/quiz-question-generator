from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI
import os
import tempfile
import shutil
from typing import Optional, List
import json
import logging
import re

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("quiz-generator")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI configuration
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key) if openai_api_key else None

class RegenerateRequest(BaseModel):
    question_text: str
    feedback: Optional[str] = None
    materials: str

class SummaryRequest(BaseModel):
    slides_text: str

def _extract_json_payload(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:-1]).strip()
    json_match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    return cleaned


def _parse_question_format(raw_text: str) -> dict:
    """Parse the custom Question/Answerlist/Solution format into a structured dict.
    
    Format matches finetune_data.jsonl:
    - Multiple Choice: Question, Answerlist (options), Solution, Answerlist (True/False markers)
    - Free Response: Question, Solution (no Answerlist before Solution)
    """
    result = {
        "question": "",
        "question_type": "free_response",
        "options": None,
        "correct_answer": "",
        "explanation": "",
        "supplemental_data": None
    }
    
    try:
        text = raw_text.strip()
        
        # Extract question text - handle both "Question\n========" and "Question\n========"
        question_match = re.search(r'Question\n=+\n?(.*?)(?=\n\nAnswerlist\n-+|\n\nSolution\n=+|$)', text, re.DOTALL)
        if question_match:
            result["question"] = question_match.group(1).strip()
        
        # Find positions of key sections
        # Look for Answerlist before Solution (indicates multiple choice)
        first_answerlist_match = re.search(r'\n\nAnswerlist\n-+\n', text)
        solution_match = re.search(r'\n\nSolution\n=+\n?', text)
        
        first_answerlist_pos = first_answerlist_match.start() if first_answerlist_match else -1
        solution_pos = solution_match.start() if solution_match else -1
        
        # Determine if multiple choice (Answerlist appears before Solution)
        is_multiple_choice = first_answerlist_pos != -1 and (solution_pos == -1 or first_answerlist_pos < solution_pos)
        
        if is_multiple_choice:
            result["question_type"] = "multiple_choice"
            
            # Extract answer options (between first Answerlist and Solution)
            answerlist_content_start = first_answerlist_match.end()
            if solution_pos != -1:
                answerlist_text = text[answerlist_content_start:solution_pos]
            else:
                answerlist_text = text[answerlist_content_start:]
            
            # Parse options - lines starting with "* "
            options = {}
            option_labels = ["A", "B", "C", "D", "E", "F", "G", "H"]
            option_lines = [line.strip() for line in answerlist_text.split("\n") if line.strip().startswith("*")]
            
            for i, line in enumerate(option_lines[:len(option_labels)]):
                # Remove leading "* " from the option text
                option_text = line[1:].strip() if line.startswith("*") else line.strip()
                options[option_labels[i]] = option_text
            
            result["options"] = options if options else None
            
            # Extract Solution section
            if solution_match:
                solution_content_start = solution_match.end()
                solution_text = text[solution_content_start:].strip()
                
                # Check for second Answerlist in solution (contains True/False/Correct/Incorrect markers)
                second_answerlist_match = re.search(r'\n\nAnswerlist\n-+\n', solution_text)
                if not second_answerlist_match:
                    # Try without double newline
                    second_answerlist_match = re.search(r'\nAnswerlist\n-+\n', solution_text)
                
                if second_answerlist_match:
                    # Explanation is text before the second Answerlist
                    result["explanation"] = solution_text[:second_answerlist_match.start()].strip()
                    
                    # Parse correct answer markers
                    markers_text = solution_text[second_answerlist_match.end():]
                    marker_lines = [line.strip() for line in markers_text.split("\n") if line.strip().startswith("*")]
                    
                    for i, line in enumerate(marker_lines[:len(option_labels)]):
                        marker_text = line[1:].strip().lower() if line.startswith("*") else line.strip().lower()
                        # Check for various correct indicators: "true", "correct", "right"
                        # But not "incorrect", "false", "not correct"
                        is_correct = False
                        if "incorrect" not in marker_text and "false" not in marker_text:
                            if "correct" in marker_text or "true" in marker_text or "right" in marker_text:
                                is_correct = True
                        
                        if is_correct:
                            result["correct_answer"] = option_labels[i]
                            break
                else:
                    # No second Answerlist - entire solution is the explanation
                    result["explanation"] = solution_text
        else:
            # Free response question
            result["question_type"] = "free_response"
            
            if solution_match:
                solution_content_start = solution_match.end()
                solution_text = text[solution_content_start:].strip()
                result["correct_answer"] = solution_text
                result["explanation"] = solution_text
        
        # Fallback: if no question was extracted, use the whole text
        if not result["question"]:
            result["question"] = raw_text.strip()
            
    except Exception as e:
        logger.error(f"Error parsing question format: {e}")
        # Fallback: return the raw text as the question
        result["question"] = raw_text.strip()
    
    return result

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and extract text from slides/quizzes."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_path = tmp_file.name
    
    try:
        import PyPDF2
        text_content = ""
        with open(tmp_path, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page in pdf_reader.pages:
                text_content += page.extract_text() + "\n"
        
        os.unlink(tmp_path)
        return JSONResponse(content={"content": text_content})
    
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.post("/generate-slides-summary")
async def generate_slides_summary(request: SummaryRequest):
    """Generate a summary and topic list from slides text."""
    try:
        if not openai_api_key or client is None:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")

        slides_text = request.slides_text.strip()
        if not slides_text:
            raise HTTPException(status_code=400, detail="Slides text is empty")

        prompt = f"""You are an expert at analyzing educational content. Based on the following lecture slides, create:

1. A comprehensive summary of approximately 450 words that captures the key concepts, main ideas, and important information covered in the slides.
2. A complete list of all topics covered in the slides.

Lecture Slides Content:
{slides_text}

Please provide your response as a JSON object with this exact structure:
{{
  "summary": "Your 450-word summary here. Make sure it's comprehensive and captures all key concepts.",
  "topics": [
    "Topic 1",
    "Topic 2",
    "Topic 3",
    ...
  ]
}}

The topics list should include ALL major topics, concepts, and themes covered in the slides. Be thorough and comprehensive.

Return ONLY the JSON object, no additional text."""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert educational content analyzer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )

        response_text = response.choices[0].message.content.strip()
        json_payload = _extract_json_payload(response_text)
        summary_data = json.loads(json_payload)
        
        return JSONResponse(content=summary_data)

    except json.JSONDecodeError as e:
        logger.exception("Failed to parse summary JSON")
        raise HTTPException(
            status_code=500,
            detail=f"Summary response was not valid JSON: {str(e)}"
        )
    except Exception as e:
        logger.exception("Unexpected error generating summary")
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")

@app.post("/generate-questions")
async def generate_questions(materials: dict):
    """Generate quiz questions from uploaded materials."""
    try:
        if not openai_api_key or client is None:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        # Build materials text - use summary for slides if available, otherwise use raw text
        materials_parts = []
        for key, value in materials.items():
            if key == "slides_summary" and value:
                # If slides_summary exists, use it instead of raw slides
                materials_parts.append(f"Lecture Slides Summary:\n{value}")
            elif key == "slides_topics" and value:
                # Add topics list
                if isinstance(value, list):
                    topics_text = "\n".join([f"- {topic}" for topic in value])
                else:
                    topics_text = value
                materials_parts.append(f"Topics Covered:\n{topics_text}")
            elif key not in ["slides", "slides_summary", "slides_topics"]:
                # Include quizzes and other materials as-is
                materials_parts.append(f"{key}:\n{value}")
        
        materials_text = "\n\n".join(materials_parts)
        
        # Check if previous quizzes are included
        has_previous_quizzes = "quizzes" in materials and materials.get("quizzes", "").strip()
        
        base_prompt = f"""You are an expert at creating educational quiz questions. Based on the following course materials, generate ONE quiz question that tests understanding of key concepts.

Course Materials:
{materials_text}

CRITICAL INSTRUCTIONS:
1. DO NOT copy or duplicate any questions from previous quizzes. Create entirely NEW and ORIGINAL questions.
2. DO NOT copy any VALUES, NUMBERS, DATASETS, EXAMPLES, or DATA from previous quizzes. All numerical values, sample data, datasets, examples, scenarios, and any other data used in your questions must be COMPLETELY NEW and DIFFERENT from previous quizzes.
3. Use previous quizzes only as a reference for:
   - Understanding the topics and concepts covered
   - Understanding the difficulty level and style
   - Understanding what types of questions are appropriate
4. Generate questions that test the SAME concepts but are COMPLETELY DIFFERENT from any questions in previous quizzes, using:
   - Different numerical values
   - Different datasets and sample data
   - Different examples and scenarios
   - Different variable names and contexts
   - Different specific details while maintaining the same conceptual focus
5. If a question requires supplemental data (like a dataset, table, figure, code snippet, or data file), you MUST include that data in the "supplemental_data" field. This supplemental data must also be ORIGINAL and not copied from previous quizzes.
6. If previous generated questions are provided below, do NOT duplicate them. Make this question distinct.
7. You may create EITHER a multiple choice question OR a free response question. Choose the format that best suits the concept being tested.

IMPORTANT: Use the exact output format below (matching our fine-tuning data). Do NOT output JSON.

=== FORMAT A: MULTIPLE CHOICE ===
Use this format for questions with discrete answer options:

Question
========
<question text>

Answerlist
----------
* <answer option 1>
* <answer option 2>
* <answer option 3>
* <answer option 4>

Solution
========
<optional explanation text>

Answerlist
----------
* <Correct or Incorrect>
* <Correct or Incorrect>
* <Correct or Incorrect>
* <Correct or Incorrect>

Multiple Choice Rules:
- Always output 4 answer options.
- Exactly one option must be marked Correct; the other three must be Incorrect.
- Keep formatting exactly as shown (headings, separators, bullets, and blank lines).

=== FORMAT B: FREE RESPONSE ===
Use this format for open-ended questions, calculations, fill-in-the-blank, or short answer:

Question
========
<question text>

Solution
========
<detailed answer and explanation>

Free Response Rules:
- No Answerlist section for the question.
- Solution should contain the expected answer and explanation.
- Good for: calculations, derivations, fill-in-the-blank, short answer, and conceptual explanations.

=== GENERAL RULES ===
- Return ONLY the formatted question, no additional text.
- Choose the format that best tests the concept (use free response for calculations and open-ended questions; use multiple choice for factual recall and concept recognition).

REMEMBER: 
- ALL questions must be ORIGINAL and NOT copied from previous quizzes
- ALL values, numbers, datasets, examples, and data must be NEW and DIFFERENT from previous quizzes
- Create fresh scenarios, examples, and data while testing the same concepts"""

        questions = []
        for i in range(5):
            previous_questions = ""
            if questions:
                # Extract just the question text from each previous response for deduplication
                prev_q_texts = []
                for q in questions:
                    # q is now a parsed dict with 'question' key
                    q_text = q.get("question", "")
                    if q_text:
                        prev_q_texts.append(f"- {q_text[:200]}...")  # Truncate for brevity
                previous_questions = "\n\nPreviously generated questions:\n" + "\n".join(prev_q_texts)

            prompt = base_prompt + previous_questions

            response = client.chat.completions.create(
                model="ft:gpt-4.1-2025-04-14:polsley:stats-quiz-topics-v1-retry-due-to-funds-2:D5dbzZ3u",
                messages=[
                    {"role": "system", "content": "You are an expert educational content creator."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )

            response_text = response.choices[0].message.content.strip()
            # Parse the formatted text into a structured dict
            parsed_question = _parse_question_format(response_text)
            questions.append(parsed_question)

        return JSONResponse(content={"questions": questions})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating questions: {str(e)}")

@app.post("/regenerate-question")
async def regenerate_question(request: RegenerateRequest):
    """Regenerate a specific question based on feedback."""
    try:
        if not openai_api_key or client is None:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        prompt = f"""You are an expert at creating educational quiz questions. 

Original question to improve:
{request.question_text}

"""
        
        if request.feedback:
            # Check if feedback contains multiple sections (previous feedback history)
            if "--- Previous Feedback ---" in request.feedback:
                prompt += f"""Feedback for improvement (includes previous feedback history):
{request.feedback}

IMPORTANT: The feedback above may contain multiple sections separated by "--- Previous Feedback ---". 
Please consider ALL feedback provided - both previous feedback and the most recent feedback - when regenerating the question.
Address all concerns and improvements mentioned across all feedback sections.\n\n"""
            else:
                prompt += f"Feedback for improvement: {request.feedback}\n\n"
        
        prompt += f"""
Context from course materials:
{request.materials}

Regenerate this question as a JSON object. You can create either a multiple choice or free response question.

For MULTIPLE CHOICE questions, use this structure:
{{
  "question": "Question text here?",
  "question_type": "multiple_choice",
  "options": {{
    "A": "Option A",
    "B": "Option B",
    "C": "Option C",
    "D": "Option D"
  }},
  "correct_answer": "A",
  "explanation": "Brief explanation of the correct answer",
  "supplemental_data": null
}}

For FREE RESPONSE questions, use this structure:
{{
  "question": "Question text here?",
  "question_type": "free_response",
  "options": null,
  "correct_answer": "The expected correct answer or key points that should be included",
  "explanation": "Brief explanation of the correct answer",
  "supplemental_data": null
}}

If the question requires supplemental data (dataset, table, figure, code, etc.), include it in "supplemental_data":
{{
  "supplemental_data": {{
    "type": "dataset|table|figure|code|other",
    "description": "Brief description",
    "data": "The actual data or content"
  }}
}}

IMPORTANT: Always include the "correct_answer" field regardless of question type. If no supplemental data is needed, set "supplemental_data" to null.

REMEMBER: 
- Create a NEW question, not a copy of the original
- Use NEW values, numbers, datasets, examples, and data - do not reuse any values from the original question
- Test the same concepts but with completely different specifics

Return ONLY the JSON object, no additional text."""

        response = client.chat.completions.create(
            model="ft:gpt-4.1-2025-04-14:polsley:stats-quiz-topics-v1-retry-due-to-funds-2:D5dbzZ3u",
            messages=[
                {"role": "system", "content": "You are an expert educational content creator."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        response_text = response.choices[0].message.content.strip()
        
        if response_text.startswith("```"):
            response_text = "\n".join(response_text.split("\n")[1:-1])
        
        question = json.loads(response_text)
        
        # Ensure supplemental_data field exists
        if "supplemental_data" not in question:
            question["supplemental_data"] = None
        
        return JSONResponse(content={"question": question})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error regenerating question: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
