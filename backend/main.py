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
        
        prompt = f"""You are an expert at creating educational quiz questions. Based on the following course materials, generate 5 diverse quiz questions that test understanding of key concepts.

Course Materials:
{materials_text}

IMPORTANT: Generate a mix of question types:
- Some questions should be MULTIPLE CHOICE (with options A, B, C, D)
- Some questions should be FREE RESPONSE (short answer questions where students write their answer)

For each question, provide:
1. The question text
2. The question type ("multiple_choice" or "free_response")
3. If multiple choice: options (A, B, C, D)
4. The correct answer (ALWAYS REQUIRED - for multiple choice use the letter, for free response provide the expected answer)
5. A brief explanation

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
  "explanation": "Brief explanation of the correct answer"
}}

For FREE RESPONSE questions:
{{
  "question": "Question text here?",
  "question_type": "free_response",
  "options": null,
  "correct_answer": "The expected correct answer or key points that should be included",
  "explanation": "Brief explanation of the correct answer"
}}

Return ONLY the JSON array, no additional text. Include a mix of both question types."""

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
  "explanation": "Brief explanation of the correct answer"
}}

For FREE RESPONSE questions, use this structure:
{{
  "question": "Question text here?",
  "question_type": "free_response",
  "options": null,
  "correct_answer": "The expected correct answer or key points that should be included",
  "explanation": "Brief explanation of the correct answer"
}}

IMPORTANT: Always include the "correct_answer" field regardless of question type.

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
        return JSONResponse(content={"question": question})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error regenerating question: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
