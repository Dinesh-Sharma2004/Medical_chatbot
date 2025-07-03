# 🩺 Medical_chatbot

A **developer-first Retrieval-Augmented Generation (RAG)** chatbot for answering **medical queries** (e.g., Anatomy, Forensics) directly from your own PDF documents. Built with **LangChain**, **FAISS**, **Hugging Face Inference Endpoints**, and a clean **Streamlit frontend**.

---

##  Features

-  Ingest local PDFs and extract text
-  Chunk documents with overlap using LangChain splitters
-  Embed content using HuggingFace Sentence Transformers (e.g., `bge-small`)
-  Store embeddings locally using **FAISS** for fast retrieval
-  Connect to LLMs like **DeepSeek** or **LLaMA** via Hugging Face endpoints
-  Return answers along with the actual **source documents**
-  Medical-focused chat UI via **Streamlit**

---

##  Architecture

```text
PDF Loader ──> Text Splitter ──> Embeddings ──> FAISS Vector DB
                                             │
                                             ▼
         Streamlit UI  <── RAG Chain (Retriever + LLM via HF Endpoint)
📁 Project Structure
bash
Copy
Edit
Medical_chatbot/
├── data/                   # Input PDFs
├── vectorstore/            # FAISS database
├── embed_documents.py      # Script to index PDFs into FAISS
├── rag_chain.py            # Core RAG logic
├── app.py                  # Streamlit chatbot UI
├── .env                    # Environment config
├── requirements.txt        # Dependencies
└── README.md               # You're here
Quickstart
1. Clone the Repo
bash
Copy
Edit
git clone https://github.com/yourusername/Medical_chatbot.git
cd Medical_chatbot
2. Install Dependencies
bash
Copy
Edit
pip install -r requirements.txt
3. Configure .env
Create a .env file with:

env
Copy
Edit
HF_TOKEN=your_huggingface_api_token
MODEL=BAAI/bge-small-en-v1.5
REPO_ID=deepseek-ai/deepseek-llm-7b-instruct
4. Add PDFs
Drop your medical PDFs inside the data/ folder.

5. Generate Vector Store
bash
Copy
Edit
python embed_documents.py
This will:

Load and split documents

Create embeddings

Save vectors in vectorstore/db_faiss

6. Launch the Chat UI
bash
Copy
Edit
streamlit run app.py
Open your browser to http://localhost:8501.

 Example Query
text
Copy
Edit
Q: What bones make up the human pelvis?

A: The pelvis is formed by the ilium, ischium, and pubis bones.

Sources:
- Anatomy_Lecture_2024.pdf, Page 4
⚙ Dev Notes
RecursiveCharacterTextSplitter: 768-char chunks with 50-char overlap

Uses HuggingFaceEndpoint for LLMs (via repo_id)

RetrievalQA chain includes source document return

FAISS allows dangerous_deserialization=True for dev-only loading

📌 Roadmap
 Dynamic PDF upload UI

 OCR support for scanned textbooks

 Docker support

 Hugging Face Spaces deployment

 Query analytics/logging

🛡 License
MIT License — free to use, fork, and build upon.

🤝 Contributing
Pull requests and feature suggestions are welcome!

📚 References
LangChain

FAISS

Hugging Face Models

Streamlit

yaml
Copy
Edit

---

Would you like me to generate this as an actual `README.md` file for download or
