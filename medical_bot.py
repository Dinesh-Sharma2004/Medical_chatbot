import streamlit as st
import os
from langchain_huggingface import HuggingFaceEndpoint
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate

load_dotenv()

HF_TOKEN = os.environ.get("HF_TOKEN")
MODEL = os.environ.get("MODEL")
DB_FAISS_PATH = "vectorstore/db_faiss"

def get_vectorstore():
    embedding_model = HuggingFaceEmbeddings(model_name=MODEL)
    return FAISS.load_local(DB_FAISS_PATH, embedding_model, allow_dangerous_deserialization=True)
    
def set_custom_prompt(custom_prompt_template):
    return PromptTemplate(template=custom_prompt_template, input_variable=["context", "question"])
    
def load_llm(repo_id, HF_TOKEN):
    return HuggingFaceEndpoint(
        repo_id=repo_id,
        temperature=0.4,
        model_kwargs={"token": HF_TOKEN, "max_length": "512"}
    )

def main():
    st.title("Ask Me Anything About Anatomy and Forensics:")
    
    # Initialize session state for messages if not already set
    if 'messages' not in st.session_state:
        st.session_state["messages"] = []
    
    # Display previous messages
    for message in st.session_state["messages"]:
        st.chat_message(message['role']).markdown(message['content'])
    
    prompt = st.chat_input("Pass your prompt here:")
    
    if prompt:
        st.chat_message('user').markdown(prompt)
        st.session_state["messages"].append({'role': 'user', 'content': prompt})
        
        CUSTOM_PROMPT_TEMPLATE = """
            Use the pieces of information provided in the context to answer user's question.
            If you don't know the answer, just say that you don't know, don't try to make up an answer.

            Context:{context}
            Question:{question}

            Start the answer directly. No small talk, please.
        """
                    
        REPO_ID = os.environ.get("REPO_ID")
        
        try:
            vectorstore = get_vectorstore()
            if vectorstore is None:
                st.error("Failed to load the vector store")
                return
            
            qa_chain = RetrievalQA.from_chain_type(
                llm=load_llm(repo_id=REPO_ID, HF_TOKEN=HF_TOKEN),
                chain_type="stuff",
                retriever=vectorstore.as_retriever(search_kwargs={'k':10}),
                return_source_documents=True,
                chain_type_kwargs={'prompt': set_custom_prompt(CUSTOM_PROMPT_TEMPLATE)}
            )   
            
            response = qa_chain.invoke({'query': prompt})
            result = response["result"]
            source_documents = response["source_documents"]
            source_texts = "\n".join([f"- {doc.page_content}" for doc in source_documents])
            result_to_show = f"**Answer:** {result}\n\n**Source Documents:**\n{source_texts}"
            st.chat_message("assistant").markdown(result_to_show)
            st.session_state["messages"].append({"role": "assistant", "content": result_to_show})
        except Exception as e:
            st.error(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
