# Quiz Question Generator

An LLM-powered pipeline that generates quiz questions from professor course materials (slides and past quizzes) using OpenAI API.

## Features

- 📤 Upload PDF files for slides and past quizzes
- 🤖 AI-powered question generation using GPT-4
- ✏️ Interactive question management:
  - Keep questions you like
  - Discard unwanted questions
  - Regenerate questions with optional feedback
- 📥 Export your final quiz as JSON

## Quick Start

From within this directory (`quiz-question-generator`), you can start the application using the helper scripts:

**Terminal 1 (Backend):**
```bash
./start_backend.sh
```

**Terminal 2 (Frontend):**
```bash
./start_frontend.sh
```

---

## Setup Instructions

### Prerequisites

- Python 3.8+
- Node.js 14+
- OpenAI API Key

### Installation

1. **Set up the backend:**

```bash
# Install Python dependencies
pip3 install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"
```

2. **Set up the frontend:**

```bash
cd frontend
npm install
cd ..
```

### Running the Application

1. **Start the backend server (Terminal 1):**

```bash
cd backend
python3 main.py
```

The backend will run on `http://localhost:8000`

2. **Start the frontend (Terminal 2):**

```bash
cd frontend
npm start
```

The frontend will run on `http://localhost:3000`

### Usage

1. **Upload Materials:** Click on the upload boxes to select PDF files for slides and/or past quizzes
2. **Generate Questions:** Click "Generate Questions" to create 5 quiz questions based on your materials
3. **Manage Questions:** 
   - Click "Keep" to save questions for your final quiz
   - Click "Discard" to remove questions you don't want
   - Enter feedback and click "Regenerate" to improve specific questions
4. **Export:** Once satisfied, click "Export Kept Questions" to download your quiz as JSON

## Project Structure

```
.
├── backend/
│   └── main.py           # FastAPI backend server
├── frontend/
│   ├── src/
│   │   ├── App.js        # Main React component
│   │   ├── App.css       # Styling
│   │   └── index.js      # Entry point
│   └── public/
├── requirements.txt      # Python dependencies
└── README.md
```

## API Endpoints

- `POST /upload` - Upload PDF files
- `POST /generate-questions` - Generate quiz questions from materials
- `POST /regenerate-question` - Regenerate a specific question with feedback

## Notes

- The application requires an active OpenAI API key
- PDF files are processed to extract text content
- Questions are generated in multiple-choice format (A, B, C, D)
- Export format is JSON with all question details
