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

│
├── backend/
│ ├── main.py

│ ├── requirements.txt

│ ├── app.py

│ ├── ingest.py

│ ├── rag_chain.py

│

├── frontend/

│ ├── src/

│ ├── public/

│ └── package.json

│

└── README.md


---

## ⚙️ Installation & Setup

### 📌 **1. Clone the Repository**
```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
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
GOOGLE_MAPS_API_KEY=your-api-key
OPENAI_API_KEY=your-api-key
MODEL_PATH=./models/model.pkl

### 📡 API Endpoints**
Method	Endpoint	Description
POST	/chat	Send a user message to chatbot
GET	/health	Health check for backend
POST	/predict	(Optional) ML model prediction

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
