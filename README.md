# 🏥 Medical Chatbot – AI-Powered Health Assistance

An AI-driven medical chatbot built using **FastAPI (backend)** and **React (frontend)**.  
It provides users with symptom-based responses, medical information retrieval, and general health guidance.  
This project is designed for learning, experimentation, and demonstrating end-to-end AI application development.

---

## 🚀 Features

- 🤖 **AI Chatbot** for answering basic medical queries  
- 📚 **Knowledge Retrieval / RAG** support (optional)  
- ⚡ **FastAPI backend** with async endpoints  
- 🌐 **React frontend** for a clean chat UI  
- 🔐 **CORS enabled** for secure client–server communication  
- 📍 **Location-based services** (optional: geopy, Google Maps API)  
- 🧪 **ML model integration** (optional: sklearn, joblib, MLflow)

---

## 🛠 Tech Stack

### **Backend**
- Python 3.10+
- FastAPI
- Uvicorn
- Pydantic
- geopy (optional)
- httpx (for API calls)
- MLflow / joblib (optional for ML models)

### **Frontend**
- React + Vite (or CRA)
- TailwindCSS (optional)
- Axios for API communication

---

## 📁 Project Structure

Medical_chatbot/

├── backend/

│     ├── main.py

│     ├── requirements.txt

│     ├── app.py

│     ├── ingest.py

│     ├── rag_chain.py

│

├── frontend/

│     ├──dist/

│     ├── src/

│     ├── public/

│     └── package.json

│

└── README.md


---

## ⚙️ Installation & Setup

### 📌 **1. Clone the Repository**
```bash
git clone https://github.com/Dinesh-Sharma2004/Medical_chatbot.git
cd Medical_Chatbot
```

### 📌 2. Backend Setup (FastAPI)**
```bash
Copy code
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
Run the server:

```bash
Copy code
uvicorn main:app --host 0.0.0.0 --port 8000
```
### 📌 3. Frontend Setup (React)**
```bash
Copy code
cd frontend
npm install
npm run dev
```
🔧 Environment Variables
Create a .env file inside backend/:

ini

Copy code

RETRIEVER_K=8

RETRIEVER_FETCH_K=20

RETRIEVER_RERANK_TOP_K=5

USE_RERANKER=false

LLM_MAX_TOKENS=300

LLM_DEVICE=auto

LLM_QUANTIZE=false

LLM_TEMPERATURE=0.1

GROQ_API_KEYS="your-api-keys(I used 15 with comma separated values in one line)"

GROQ_MODEL=llama-3.1-8b-instant

EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

EMBED_BATCH_SIZE=32

DB_FAISS_BASE="vectorstore"

HF_HOME="/cache/huggingface"

HF_HUB_CACHE="/cache/huggingface"

### 📡 API Endpoints**

Method	Endpoint	Description
🚀 1. Health Check
GET /api/health

Returns the live status of the backend, including vector store & LLM readiness.

Response
```bash
{
  "status": "ok",
  "vector_ready": true,
  "llm_ready": true,
  "detail": {
    "vectorstore": true,
    "llm": true
  }
}
```
📄 2. PDF Upload & Ingestion
POST /api/upload

Uploads a PDF file, saves it, and triggers background ingestion → embeddings → FAISS vector store creation.

Form-Data
Field	Type	Description
file	file (.pdf)	PDF document to ingest
```
Response
{
  "ok": true,
  "job_id": "uuid",
  "filename": "uploaded.pdf"
}
```
GET /api/upload/status/{job_id}

Fetches the ongoing ingestion progress.

```Response Example

{
  "job_id": "1234",
  "filename": "report.pdf",
  "status": "processing",
  "progress": 60,
  "detail": "Chunking pages"
}
```

Status values:
```
processing

completed

error
```
📚 3. Full Document Text Retrieval
GET /api/source/{doc_id}

Returns the fulltext representation of a document chunk created during ingestion.

Response
```
{
  "doc_id": "page_3",
  "text": "Full page extracted text..."
}
```
💬 4. Non-Streaming Question Answering
POST /api/ask

Sends a user query and returns the final answer using RAG (Groq + FAISS).

Form Fields
Field	Type	Default	Description
question	string	required	User query
mode	string	"basic"	RAG chain mode

```
Response
{
  "answer": "The answer...",
  "sources": [
    {
      "filename": "file.pdf",
      "page": 12,
      "doc_id": "chunk_12"
    }
  ],
  "mode": "basic"
}
```

🔄 5. Streaming Question Answering (NDJSON)
POST /api/ask/stream

Returns the answer token-by-token (Groq streaming). Uses NDJSON format where every line is a JSON object.

```
Body (JSON)
{
  "question": "What is diabetes?",
  "mode": "basic"
}
```
Streaming Event Types
Type	Meaning
sources	First event → List of retrieved chunks
partial	Partial answer chunk
done	Completion signal
error	Error message
Example Stream
```
{"type":"sources","sources":[...]}
{"type":"partial","text":"Diabetes is..."}
{"type":"partial","text":"a metabolic disorder..."}
{"type":"done"}
```

🖥️ 6. Frontend Serving (Vite Build)

If the frontend build exists, it serves the SPA:

GET /
```
Serves index.html from Vite’s dist/ folder.
```
🧪 7. Frontend Info Endpoint
GET /_frontend_info

Returns the actual location of the frontend distribution folder.

```
Response
{
  "frontend_dist": "/path/to/dist",
  "exists": true
}
```


🧠 How It Works
The user sends a message via the React UI

The message is forwarded to FastAPI

Backend processes the query using:

LLM / RAG

ML model

Custom rule-based logic

Response is returned to frontend

User sees the AI-generated output

🧪 Running Tests
```bash
Copy code
pytest
🛤 Roadmap
 Add vector database (Chroma / FAISS)

 Deploy backend to Fly.io or Render

 Deploy frontend to Vercel

 Add user authentication

 Implement chat history storage
```
🤝 Contributing
Pull requests are welcome!
For major changes, please open an issue first to discuss your ideas.

📄 License
This project is licensed under the MIT License.

⭐ Support
If you find this project helpful, please star the repository ⭐
