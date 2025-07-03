# 🩺 Medical RAG Chatbot

A developer-first implementation of a **Retrieval-Augmented Generation (RAG)** chatbot for querying medical knowledge (Anatomy & Forensics) from local PDFs using **LangChain**, **FAISS**, and **Hugging Face Inference Endpoints**. Includes a modular backend pipeline and an interactive **Streamlit frontend**.

---

## ⚙️ Features

- ⚡ Local PDF ingestion and chunking
- 🔍 Semantic search via FAISS + HuggingFace embeddings (`bge-small`, etc.)
- 🤖 Context-aware answers with LLMs (e.g., DeepSeek, LLaMA via HF Inference API)
- 🧾 Source attribution for traceable answers
- 💬 Streamlit-based chat UI with message history
- 🔐 Environment-based configuration via `.env`

---

## 🧱 Architecture

PDF Loader (PyPDFLoader)
│
Text Splitter (LangChain)
│
HuggingFace Embeddings (Sentence-BERT/BGE)
│
FAISS Vector Store (local)
│
Retriever → LLM via HF Endpoint
│
Streamlit Chat UI

yaml
Copy
Edit

---

## 📂 Directory Structure

```bash
.
├── data/                   # Input PDFs
├── vectorstore/            # FAISS DB
├── embed_documents.py      # PDF → FAISS pipeline
├── rag_chain.py            # RAG chain logic
├── app.py                  # Streamlit UI
├── .env                    # API keys and config
├── requirements.txt        # Python deps
└── README.md
🔧 Setup
1. Clone & Install
bash
Copy
Edit
git clone https://github.com/yourusername/medical-rag-chatbot.git
cd medical-rag-chatbot
pip install -r requirements.txt
2. Environment Configuration
Create a .env file:

env
Copy
Edit
HF_TOKEN=your_hf_token
MODEL=BAAI/bge-small-en-v1.5
REPO_ID=deepseek-ai/deepseek-llm-7b-instruct
3. Prepare PDF Data
Place your medical PDF files inside the data/ directory.

4. Generate Embeddings
bash
Copy
Edit
python embed_documents.py
This:

Loads PDFs

Chunks text

Embeds with HuggingFace

Stores vectors in vectorstore/db_faiss

🧠 Run the Chatbot (Streamlit UI)
bash
Copy
Edit
streamlit run app.py
Navigate to http://localhost:8501 in your browser.

💬 Prompt Behavior
RAG Chain uses RetrievalQA with k=10 context docs

Custom system prompt template:

vbnet
Copy
Edit
Use the context to answer factually. 
Say "I don't know" if uncertain. Avoid small talk.
Output includes both:

response["result"]

response["source_documents"]

🧪 Testing a Sample Query
text
Copy
Edit
Query: List the bones forming the human pelvis.
Output:
  Answer: The pelvis is formed by the ilium, ischium, and pubis.
  Sources:
    - Anatomy_Notes.pdf page 5
🛠️ Dev Notes
All chunking uses RecursiveCharacterTextSplitter (768 chars, 50 overlap)

Embedding model and LLM repo are configurable via .env

Uses allow_dangerous_deserialization=True for FAISS load (safe in dev/local)

📌 Roadmap
 Web PDF uploader

 OCR support for scanned/image-based PDFs

 Docker containerization

 CI/CD pipeline for deployments

 Query logging and analytics

🛡 License
MIT License — free to use, modify, and distribute.

🤝 Contributions
PRs and issues welcome. Please open discussions for major design suggestions.

📎 References
LangChain Docs

FAISS

Hugging Face Hub

Streamlit

yaml
Copy
Edit

---

Let me know if you'd like this generated as an actual `README.md` file or packaged into a ZIP of the project!








Ask ChatGPT
