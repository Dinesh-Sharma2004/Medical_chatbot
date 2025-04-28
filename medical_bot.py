import streamlit as st
import os
from langchain_huggingface import HuggingFaceEndpoint
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate

# Load environment variables safely
load_dotenv()

# Environment variables
HF_TOKEN = os.getenv("HF_TOKEN")
MODEL = os.getenv("MODEL")
REPO_ID = os.getenv("REPO_ID")
DB_FAISS_PATH = "vectorstore/db_faiss"

def get_vectorstore():
    embedding_model = HuggingFaceEmbeddings(model_name=MODEL)
    return FAISS.load_local(DB_FAISS_PATH, embedding_model, allow_dangerous_deserialization=True)
    
def set_custom_prompt(custom_prompt_template):
    return PromptTemplate(template=custom_prompt_template, input_variables=["context", "question"])
    
def load_llm(repo_id, token):
    return HuggingFaceEndpoint(
        repo_id=repo_id,
        temperature=0.4,
        model_kwargs={"token": token, "max_length": 512}
    )

def main():
    st.set_page_config(page_title="Medical Chatbot", layout="wide")
    st.title("🩺 Medical Chatbot — Ask About Anatomy & Forensics")

    if 'messages' not in st.session_state:
        st.session_state['messages'] = []

    for message in st.session_state['messages']:
        st.chat_message(message['role']).markdown(message['content'])

    prompt = st.chat_input("Ask a medical question...")

    if prompt:
        st.chat_message('user').markdown(prompt)
        st.session_state['messages'].append({'role': 'user', 'content': prompt})

        CUSTOM_PROMPT_TEMPLATE = """
        Use the provided context to answer the user's question factually.
        If you don't know the answer, say "I don't know" — do not guess.

        Context: {context}
        Question: {question}

        Answer directly without greetings or apologies.
        """

        try:
            vectorstore = get_vectorstore()
            if not vectorstore:
                st.error("Error loading the vector database.")
                return

            qa_chain = RetrievalQA.from_chain_type(
                llm=load_llm(REPO_ID, HF_TOKEN),
                chain_type="stuff",
                retriever=vectorstore.as_retriever(search_kwargs={'k': 10}),
                return_source_documents=True,
                chain_type_kwargs={'prompt': set_custom_prompt(CUSTOM_PROMPT_TEMPLATE)}
            )

            response = qa_chain.invoke({'query': prompt})
            result = response.get("result", "No result found.")
            source_documents = response.get("source_documents", [])
            sources_text = "\n".join(f"- {doc.page_content}" for doc in source_documents)

            result_to_display = f"**Answer:** {result}\n\n**Sources:**\n{sources_text}"
            st.chat_message('assistant').markdown(result_to_display)
            st.session_state['messages'].append({'role': 'assistant', 'content': result_to_display})

        except Exception as e:
            st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
