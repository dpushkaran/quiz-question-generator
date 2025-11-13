from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import openai
import os
import tempfile
import shutil
from typing import Optional, List
import json

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI configuration
openai.api_key = os.getenv("OPENAI_API_KEY")

class RegenerateRequest(BaseModel):
    question_text: str
    feedback: Optional[str] = None
    materials: str

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

@app.post("/generate-questions")
async def generate_questions(materials: dict):
    """Generate quiz questions from uploaded materials."""
    try:
        if not openai.api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        materials_text = "\n\n".join([f"{key}:\n{value}" for key, value in materials.items()])
        
        # Check if previous quizzes are included
        has_previous_quizzes = "quizzes" in materials and materials.get("quizzes", "").strip()
        
        prompt = f"""You are an expert at creating educational quiz questions. Based on the following course materials, generate 5 diverse quiz questions that test understanding of key concepts.

Course Materials:
{materials_text}

CRITICAL INSTRUCTIONS:
1. DO NOT copy or duplicate any questions from previous quizzes. Create entirely NEW and ORIGINAL questions.
2. Use previous quizzes only as a reference for:
   - Understanding the topics and concepts covered
   - Understanding the difficulty level and style
   - Understanding what types of questions are appropriate
3. Generate questions that test the SAME concepts but are COMPLETELY DIFFERENT from any questions in previous quizzes.
4. If a question requires supplemental data (like a dataset, table, figure, code snippet, or data file), you MUST include that data in the "supplemental_data" field.

IMPORTANT: Generate a mix of question types:
- Some questions should be MULTIPLE CHOICE (with options A, B, C, D)
- Some questions should be FREE RESPONSE (short answer questions where students write their answer)

For each question, provide:
1. The question text
2. The question type ("multiple_choice" or "free_response")
3. If multiple choice: options (A, B, C, D)
4. The correct answer (ALWAYS REQUIRED - for multiple choice use the letter, for free response provide the expected answer)
5. A brief explanation
6. If the question requires supplemental data (datasets, tables, figures, code, etc.), include it in "supplemental_data"

Format your response as a JSON array with this structure:

For MULTIPLE CHOICE questions:
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

For FREE RESPONSE questions:
{{
  "question": "Question text here?",
  "question_type": "free_response",
  "options": null,
  "correct_answer": "The expected correct answer or key points that should be included",
  "explanation": "Brief explanation of the correct answer",
  "supplemental_data": null
}}

If a question requires supplemental data (e.g., a dataset, table, figure, code snippet), include it like this:
{{
  "question": "Question that requires data...",
  "question_type": "multiple_choice",
  "options": {{...}},
  "correct_answer": "A",
  "explanation": "...",
  "supplemental_data": {{
    "type": "dataset|table|figure|code|other",
    "description": "Brief description of what the supplemental data is",
    "data": "The actual data, table content, code, or description of where to find it. For datasets, provide CSV-like format or structured data."
  }}
}}

Return ONLY the JSON array, no additional text. Include a mix of both question types. Remember: ALL questions must be ORIGINAL and NOT copied from previous quizzes."""

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert educational content creator."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        response_text = response.choices[0].message.content.strip()
        
        if response_text.startswith("```"):
            response_text = "\n".join(response_text.split("\n")[1:-1])
        
        questions = json.loads(response_text)
        
        # Ensure all questions have supplemental_data field (set to null if not provided)
        for question in questions:
            if "supplemental_data" not in question:
                question["supplemental_data"] = None
        
        return JSONResponse(content={"questions": questions})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating questions: {str(e)}")

@app.post("/regenerate-question")
async def regenerate_question(request: RegenerateRequest):
    """Regenerate a specific question based on feedback."""
    try:
        if not openai.api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        prompt = f"""You are an expert at creating educational quiz questions. 

Original question to improve:
{request.question_text}

"""
        
        if request.feedback:
            prompt += f"Feedback for improvement: {request.feedback}\n\n"
        
        prompt += f"""
Context from course materials:
{request.materials}

CRITICAL: Do NOT copy the original question. Create a NEW question that addresses the feedback while testing similar concepts.

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

Return ONLY the JSON object, no additional text."""

        response = openai.ChatCompletion.create(
            model="gpt-4",
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
