import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [question, setQuestion] = useState('');
  const [chat, setChat] = useState([]);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [thinking, setThinking] = useState(false);

  const handleAsk = async () => {
    if (!question) return;

    setChat(prev => [...prev, { type: 'user', text: question }]);
    setThinking(true); // 🧠 Set thinking state

    try {
      const res = await axios.post('http://localhost:8000/ask_question', { question });

      setChat(prev => [
        ...prev,
        { type: 'bot', text: res.data.answer }
      ]);
      setQuestion('');
    } catch (err) {
      console.error(err);
      setChat(prev => [...prev, { type: 'bot', text: "❌ Failed to get an answer." }]);
    } finally {
      setThinking(false);
    }
  };

  const handleFileUpload = async () => {
    if (!file) {
      alert("Please select a PDF file.");
      return;
    }

    const formData = new FormData();
    formData.append('files', file);
    setUploading(true);

    try {
      await axios.post('http://localhost:8000/upload_pdfs', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      alert("✅ File uploaded successfully.");
      setFile(null);
    } catch (err) {
      console.error(err);
      alert("❌ Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="container">
      <header className="header">
        <h1>Bank Intel Assistant</h1>
      </header>

      <section className="overview">
        <h2>Overview</h2>
        <p>A GenAI-powered assistant for banking staff to get instant answers on operations, policies, SOPs, and financial terms.</p>
      </section>

      <section className="chat-box">
        {chat.map((entry, index) => (
          <div key={index} className={entry.type === 'user' ? 'chat-user' : 'chat-bot'}>
            <p>{entry.text}</p>
          </div>
        ))}
        {thinking && (
          <div className="chat-bot thinking">
            <p>💭 Thinking...</p>
          </div>
        )}
      </section>

      <section className="input-section">
        <input
          type="text"
          placeholder="Type your question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={thinking}
        />
        <button onClick={handleAsk} disabled={thinking}>Send</button>
      </section>

      <section className="upload-enhanced">
        <h3>Upload New PDF</h3>

        <div className="upload-row bordered">
          <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files[0])} />
          <span>{file ? file.name : "No file chosen"}</span>
        </div>

        <div className="upload-row horizontal">
          <button onClick={handleFileUpload} disabled={uploading}>
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </div>
      </section>
    </div>
  );
}

export default App;
