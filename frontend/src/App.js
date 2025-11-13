import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [materials, setMaterials] = useState({});
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(null);
  const [feedback, setFeedback] = useState({});
  const [uploadStatus, setUploadStatus] = useState({});

  const handleFileUpload = async (e, materialType) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadStatus(prev => ({ ...prev, [materialType]: 'uploading' }));
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await axios.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setMaterials(prev => ({
        ...prev,
        [materialType]: response.data.content
      }));
      setUploadStatus(prev => ({ ...prev, [materialType]: 'success' }));
    } catch (error) {
      setUploadStatus(prev => ({ ...prev, [materialType]: 'error' }));
      alert('Error uploading file: ' + error.message);
    }
  };

  const handleGenerateQuestions = async () => {
    if (Object.keys(materials).length === 0) {
      alert('Please upload at least one material file');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post('/generate-questions', materials);
      setQuestions(response.data.questions.map((q, i) => ({ ...q, id: Date.now() + i })));
    } catch (error) {
      alert('Error generating questions: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeep = (questionId) => {
    setQuestions(prev => prev.map(q => 
      q.id === questionId ? { ...q, status: q.status === 'kept' ? undefined : 'kept' } : q
    ));
  };

  const handleDiscard = (questionId) => {
    setQuestions(prev => prev.filter(q => q.id !== questionId));
  };

  const handleRegenerate = async (questionId) => {
    const question = questions.find(q => q.id === questionId);
    if (!question) return;

    setRegenerating(questionId);
    try {
      const materialsText = Object.values(materials).join('\n\n');
      const fb = feedback[questionId] || '';
      
      const response = await axios.post('/regenerate-question', {
        question_text: question.question,
        feedback: fb,
        materials: materialsText
      });

      setQuestions(prev => prev.map(q => 
        q.id === questionId ? { ...response.data.question, id: questionId } : q
      ));
    } catch (error) {
      alert('Error regenerating question: ' + error.message);
    } finally {
      setRegenerating(null);
      setFeedback(prev => {
        const newFeedback = { ...prev };
        delete newFeedback[questionId];
        return newFeedback;
      });
    }
  };

  const handleExport = () => {
    const keptQuestions = questions.filter(q => q.status === 'kept');
    if (keptQuestions.length === 0) {
      alert('No questions to export. Please keep at least one question.');
      return;
    }

    const exportData = {
      totalQuestions: keptQuestions.length,
      questions: keptQuestions.map(q => ({
        question: q.question,
        question_type: q.question_type || (q.options ? 'multiple_choice' : 'free_response'),
        options: q.options || null,
        correct_answer: q.correct_answer,
        explanation: q.explanation,
        supplemental_data: q.supplemental_data || null
      }))
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'quiz_questions.json';
    a.click();
  };

  const keptCount = questions.filter(q => q.status === 'kept').length;
  const totalQuestions = questions.length;

  return (
    <div className="App">
      <header className="App-header">
        <div className="header-content">
          <div className="header-title">
            <h1>Quiz Question Generator</h1>
            <p className="subtitle">AI-Powered Question Creation for Educators</p>
          </div>
          {totalQuestions > 0 && (
            <div className="header-stats">
              <div className="stat-item">
                <span className="stat-label">Total Questions</span>
                <span className="stat-value">{totalQuestions}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Kept</span>
                <span className="stat-value kept">{keptCount}</span>
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="App-main">
        <section className="upload-section">
          <div className="section-title">
            <h2>Course Materials</h2>
            <p className="section-description">Upload your lecture slides and past quiz materials to generate questions</p>
          </div>
          <div className="upload-grid">
            <div className={`upload-box ${materials.slides ? 'uploaded' : ''} ${uploadStatus.slides === 'uploading' ? 'uploading' : ''}`}>
              <div className="upload-icon">
                {uploadStatus.slides === 'success' ? '✓' : uploadStatus.slides === 'uploading' ? '⏳' : '📄'}
              </div>
              <h3>Lecture Slides</h3>
              <p className="upload-hint">PDF format recommended</p>
              <label className="file-input-label">
                <input 
                  type="file" 
                  accept=".pdf" 
                  onChange={(e) => handleFileUpload(e, 'slides')}
                  className="file-input"
                />
                <span className="file-input-button">
                  {materials.slides ? 'Replace File' : 'Choose File'}
                </span>
              </label>
              {materials.slides && (
                <p className="upload-status success">
                  <span className="status-icon">✓</span> File uploaded successfully
                </p>
              )}
              {uploadStatus.slides === 'error' && (
                <p className="upload-status error">
                  <span className="status-icon">✗</span> Upload failed
                </p>
              )}
            </div>
            <div className={`upload-box ${materials.quizzes ? 'uploaded' : ''} ${uploadStatus.quizzes === 'uploading' ? 'uploading' : ''}`}>
              <div className="upload-icon">
                {uploadStatus.quizzes === 'success' ? '✓' : uploadStatus.quizzes === 'uploading' ? '⏳' : '📝'}
              </div>
              <h3>Past Quizzes</h3>
              <p className="upload-hint">PDF format recommended</p>
              <label className="file-input-label">
                <input 
                  type="file" 
                  accept=".pdf" 
                  onChange={(e) => handleFileUpload(e, 'quizzes')}
                  className="file-input"
                />
                <span className="file-input-button">
                  {materials.quizzes ? 'Replace File' : 'Choose File'}
                </span>
              </label>
              {materials.quizzes && (
                <p className="upload-status success">
                  <span className="status-icon">✓</span> File uploaded successfully
                </p>
              )}
              {uploadStatus.quizzes === 'error' && (
                <p className="upload-status error">
                  <span className="status-icon">✗</span> Upload failed
                </p>
              )}
            </div>
          </div>
          <div className="generate-section">
            <button 
              onClick={handleGenerateQuestions}
              disabled={loading || Object.keys(materials).length === 0}
              className="generate-btn"
            >
              {loading ? (
                <>
                  <span className="spinner"></span>
                  Generating Questions...
                </>
              ) : (
                <>
                  <span className="btn-icon">✨</span>
                  Generate Questions
                </>
              )}
            </button>
            {Object.keys(materials).length === 0 && (
              <p className="generate-hint">Upload at least one file to generate questions</p>
            )}
          </div>
        </section>

        {questions.length > 0 && (
          <section className="questions-section">
            <div className="section-header">
              <div className="section-title">
                <h2>Generated Questions</h2>
                <p className="section-description">
                  Review and manage your questions. Keep the ones you want to include in your quiz.
                </p>
              </div>
              <button onClick={handleExport} className="export-btn" disabled={keptCount === 0}>
                <span className="btn-icon">📥</span>
                Export Quiz ({keptCount} {keptCount === 1 ? 'question' : 'questions'})
              </button>
            </div>
            
            <div className="questions-list">
              {questions.map((question, index) => (
                <div key={question.id} className={`question-card ${question.status === 'kept' ? 'kept' : ''}`}>
                  <div className="question-number">Question {index + 1}</div>
                  <div className="question-header">
                    <h3>{question.question}</h3>
                    <div className="question-header-right">
                      {question.question_type && (
                        <span className="question-type-badge">
                          {question.question_type === 'multiple_choice' ? 'Multiple Choice' : 'Free Response'}
                        </span>
                      )}
                      {question.status === 'kept' && (
                        <span className="kept-badge">✓ Kept</span>
                      )}
                    </div>
                  </div>
                  
                  {question.question_type === 'multiple_choice' && question.options && (
                    <div className="options-container">
                      <div className="options-label">Answer Choices:</div>
                      <div className="options">
                        {Object.entries(question.options).map(([key, value]) => (
                          <div key={key} className={`option ${key === question.correct_answer ? 'correct' : ''}`}>
                            <span className="option-label">{key}.</span>
                            <span className="option-text">{value}</span>
                            {key === question.correct_answer && (
                              <span className="correct-badge">Correct Answer</span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {question.question_type === 'free_response' && (
                    <div className="correct-answer-container">
                      <div className="correct-answer-label">Expected Answer:</div>
                      <div className="correct-answer-text">{question.correct_answer}</div>
                    </div>
                  )}
                  
                  {!question.question_type && question.options && (
                    <div className="options-container">
                      <div className="options-label">Answer Choices:</div>
                      <div className="options">
                        {Object.entries(question.options).map(([key, value]) => (
                          <div key={key} className={`option ${key === question.correct_answer ? 'correct' : ''}`}>
                            <span className="option-label">{key}.</span>
                            <span className="option-text">{value}</span>
                            {key === question.correct_answer && (
                              <span className="correct-badge">Correct Answer</span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {!question.question_type && !question.options && question.correct_answer && (
                    <div className="correct-answer-container">
                      <div className="correct-answer-label">Correct Answer:</div>
                      <div className="correct-answer-text">{question.correct_answer}</div>
                    </div>
                  )}
                  
                  {question.supplemental_data && (
                    <div className="supplemental-data-container">
                      <div className="supplemental-data-label">
                        📊 Supplemental Data Required ({question.supplemental_data.type || 'data'}):
                      </div>
                      {question.supplemental_data.description && (
                        <div className="supplemental-data-description">
                          {question.supplemental_data.description}
                        </div>
                      )}
                      <div className="supplemental-data-content">
                        <pre>{question.supplemental_data.data}</pre>
                      </div>
                    </div>
                  )}
                  
                  <div className="explanation">
                    <div className="explanation-label">Explanation:</div>
                    <div className="explanation-text">{question.explanation}</div>
                  </div>

                  <div className="question-actions">
                    <div className="action-buttons">
                      <button 
                        onClick={() => handleKeep(question.id)}
                        className={`action-btn keep-btn ${question.status === 'kept' ? 'active' : ''}`}
                      >
                        <span className="btn-icon">{question.status === 'kept' ? '✓' : '+'}</span>
                        {question.status === 'kept' ? 'Kept' : 'Keep Question'}
                      </button>
                      
                      <button 
                        onClick={() => handleDiscard(question.id)}
                        className="action-btn discard-btn"
                      >
                        <span className="btn-icon">🗑</span>
                        Discard
                      </button>
                    </div>
                    
                    <div className="regenerate-section">
                      <div className="regenerate-label">Improve this question:</div>
                      <div className="regenerate-controls">
                        <textarea
                          placeholder="Provide feedback to improve this question (e.g., 'Make it more challenging' or 'Focus on concept X')..."
                          value={feedback[question.id] || ''}
                          onChange={(e) => setFeedback(prev => ({
                            ...prev,
                            [question.id]: e.target.value
                          }))}
                          className="feedback-input"
                          rows="2"
                        />
                        <button 
                          onClick={() => handleRegenerate(question.id)}
                          disabled={regenerating === question.id}
                          className="regenerate-btn"
                        >
                          {regenerating === question.id ? (
                            <>
                              <span className="spinner small"></span>
                              Regenerating...
                            </>
                          ) : (
                            <>
                              <span className="btn-icon">🔄</span>
                              Regenerate
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
