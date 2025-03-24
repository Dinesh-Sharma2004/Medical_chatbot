from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
MODEL = os.getenv("MODEL")
DATA_PATH = "data/"

if not HF_TOKEN or not MODEL:
    raise ValueError("Missing HF_TOKEN or MODEL in environment variables!")

# Set cache directories for Hugging Face
os.environ["HF_HOME"] = os.getenv("HF_HOME", "./hf_home")
os.environ["HF_HUB_CACHE"] = os.getenv("HF_HUB_CACHE", "./hf_cache")

# Function to load PDFs from a directory using PyPDFLoader
def load_pdf_files(data_path):
    loader = DirectoryLoader(data_path, glob="*.pdf", loader_cls=PyPDFLoader)
    return loader.load()

documents = load_pdf_files(DATA_PATH)

# Function to split text from documents into manageable chunks
def create_chunks(extracted_data):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=768, chunk_overlap=50)
    return text_splitter.split_documents(extracted_data)

text_chunks = create_chunks(documents)

# Initialize the embedding model using Hugging Face
def get_embedding_model():
    return HuggingFaceEmbeddings(model_name=MODEL)

embedding_model = get_embedding_model()

# Prepare local storage for FAISS database
DB_FAISS_PATH = "vectorstore/db_faiss"
os.makedirs(DB_FAISS_PATH, exist_ok=True)

# Extract text content and metadata from each chunk
texts = [chunk.page_content for chunk in text_chunks]
metadatas = [chunk.metadata for chunk in text_chunks]

# Generate the FAISS vector store from texts
db = FAISS.from_texts(texts=texts, embedding=embedding_model, metadatas=metadatas)
db.save_local(DB_FAISS_PATH)

print(f"FAISS vector store saved at {DB_FAISS_PATH}")
