import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [materials, setMaterials] = useState({});
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(null);
  const [feedback, setFeedback] = useState({}); // Stores current input per question
  const [feedbackHistory, setFeedbackHistory] = useState({}); // Stores all feedback history per question: { questionId: [feedback1, feedback2, ...] }
  const [questionHistory, setQuestionHistory] = useState({}); // Stores all question versions: { questionId: [version1, version2, ...] }
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
      const newQuestions = response.data.questions.map((q, i) => ({ ...q, id: Date.now() + i }));
      setQuestions(newQuestions);
      
      // Initialize question history with the first version
      const newHistory = {};
      newQuestions.forEach(q => {
        newHistory[q.id] = [{ ...q, versionNumber: 1, timestamp: new Date().toISOString() }];
      });
      setQuestionHistory(newHistory);
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
    // Clean up feedback history for discarded question
    setFeedbackHistory(prev => {
      const newHistory = { ...prev };
      delete newHistory[questionId];
      return newHistory;
    });
    // Clean up question history for discarded question
    setQuestionHistory(prev => {
      const newHistory = { ...prev };
      delete newHistory[questionId];
      return newHistory;
    });
    // Clean up current feedback input
    setFeedback(prev => {
      const newFeedback = { ...prev };
      delete newFeedback[questionId];
      return newFeedback;
    });
  };

  const handleRegenerate = async (questionId) => {
    const question = questions.find(q => q.id === questionId);
    if (!question) return;

    setRegenerating(questionId);
    try {
      const materialsText = Object.values(materials).join('\n\n');
      const currentFeedback = feedback[questionId] || '';
      
      // Get all previous feedback for this question
      const previousFeedback = feedbackHistory[questionId] || [];
      
      // Combine all feedback: previous feedback + current feedback
      const allFeedback = [...previousFeedback];
      if (currentFeedback.trim()) {
        allFeedback.push(currentFeedback);
      }
      
      // Send all feedback history to backend
      const feedbackText = allFeedback.length > 0 
        ? allFeedback.join('\n\n--- Previous Feedback ---\n\n')
        : '';
      
      // Save current question to history before regenerating (if it's different from the last version)
      const currentHistory = questionHistory[questionId] || [];
      const lastVersion = currentHistory.length > 0 ? currentHistory[currentHistory.length - 1] : null;
      const isCurrentDifferent = !lastVersion || lastVersion.question !== question.question;
      
      const response = await axios.post('/regenerate-question', {
        question_text: question.question,
        feedback: feedbackText,
        materials: materialsText
      });

      const newQuestion = { ...response.data.question, id: questionId };
      
      // Update question
      setQuestions(prev => prev.map(q => 
        q.id === questionId ? newQuestion : q
      ));
      
      // Add to history: current version (if different) + new version
      setQuestionHistory(prev => {
        const history = prev[questionId] || [];
        const newHistory = [...history];
        
        // Add current version if it's different from the last one
        if (isCurrentDifferent) {
          const versionNumber = history.length + 1;
          newHistory.push({
            ...question,
            versionNumber: versionNumber,
            timestamp: new Date().toISOString()
          });
        }
        
        // Always add the new regenerated version
        const newVersionNumber = newHistory.length + 1;
        newHistory.push({
          ...newQuestion,
          versionNumber: newVersionNumber,
          timestamp: new Date().toISOString()
        });
        
        return {
          ...prev,
          [questionId]: newHistory
        };
      });
      
      // Add current feedback to history and clear current input
      if (currentFeedback.trim()) {
        setFeedbackHistory(prev => ({
          ...prev,
          [questionId]: [...(prev[questionId] || []), currentFeedback]
        }));
      }
      
      // Clear current feedback input (but keep history)
      setFeedback(prev => {
        const newFeedback = { ...prev };
        delete newFeedback[questionId];
        return newFeedback;
      });
    } catch (error) {
      alert('Error regenerating question: ' + error.message);
    } finally {
      setRegenerating(null);
    }
  };

  const handleRevert = (questionId, versionIndex) => {
    const history = questionHistory[questionId];
    if (!history || versionIndex < 0 || versionIndex >= history.length) return;
    
    const versionToRevert = history[versionIndex];
    // Remove versionNumber and timestamp before setting as current question
    const { versionNumber, timestamp, ...questionToRestore } = versionToRevert;
    
    setQuestions(prev => prev.map(q => 
      q.id === questionId ? { ...questionToRestore, id: questionId } : q
    ));
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
                      <div className="regenerate-label">
                        Improve this question:
                        {feedbackHistory[question.id] && feedbackHistory[question.id].length > 0 && (
                          <span className="feedback-history-indicator">
                            ({feedbackHistory[question.id].length} previous {feedbackHistory[question.id].length === 1 ? 'feedback' : 'feedbacks'})
                          </span>
                        )}
                      </div>
                      {feedbackHistory[question.id] && feedbackHistory[question.id].length > 0 && (
                        <div className="previous-feedback-summary">
                          <details>
                            <summary>View previous feedback history</summary>
                            <div className="feedback-history-list">
                              {feedbackHistory[question.id].map((fb, idx) => (
                                <div key={idx} className="feedback-history-item">
                                  <span className="feedback-number">Feedback #{idx + 1}:</span>
                                  <span className="feedback-text">{fb}</span>
                                </div>
                              ))}
                            </div>
                          </details>
                        </div>
                      )}
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
                    
                    {questionHistory[question.id] && questionHistory[question.id].length > 1 && (
                      <div className="revert-section">
                        <div className="revert-label">
                          Previous Versions ({questionHistory[question.id].length - 1} {questionHistory[question.id].length - 1 === 1 ? 'version' : 'versions'} available):
                        </div>
                        <div className="version-list">
                          {questionHistory[question.id].slice(0, -1).reverse().map((version, idx) => {
                            const actualIndex = questionHistory[question.id].length - 2 - idx;
                            const versionDate = new Date(version.timestamp).toLocaleString();
                            return (
                              <div key={actualIndex} className="version-item">
                                <div className="version-header">
                                  <span className="version-number">Version {version.versionNumber}</span>
                                  <span className="version-date">{versionDate}</span>
                                </div>
                                <div className="version-preview">
                                  <div className="version-question-preview">
                                    {version.question.substring(0, 100)}{version.question.length > 100 ? '...' : ''}
                                  </div>
                                </div>
                                <button
                                  onClick={() => handleRevert(question.id, actualIndex)}
                                  className="revert-btn"
                                >
                                  <span className="btn-icon">↩</span>
                                  Revert to this version
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
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
