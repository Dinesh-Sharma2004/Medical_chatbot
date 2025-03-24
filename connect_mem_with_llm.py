import os
from langchain_huggingface import HuggingFaceEndpoint
from langchain_core.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS

load_dotenv()
MODEL=os.environ.get("MODEL")

#1------------------------------Setup LLM(DeepSeek with HuggingFace)-----------------------------------------

HF_TOKEN=os.environ.get("HF_TOKEN")
repo_id=os.environ.get("REPO_ID")


def load_llm(repo_id):
    llm=HuggingFaceEndpoint(
        repo_id=repo_id,
        temperature=0.4,
        model_kwargs={"token":HF_TOKEN,
                      "max_length":"512"}
    )
    return llm


#2---------------------------------Connect LLM with FAISS and create chain-----------------------------------
DB_FAISS_PATH="vectorstore/db_faiss"
CUSTOM_PROMPT_TEMPLATE="""
Use the pieves of information provided in the context to answer user's question.
If you don't know the answer, just say that you don't knwo, don't try to make up an answer.
Don't provide anything out of the given control

Context:{context}
Question:{question}

Start the answer direactly.No small talk please.
"""

def set_custom_prompt(custom_prompt_template):
    prompt=PromptTemplate(template=custom_prompt_template,input_variable=["context","question"])
    return prompt


#------------------------------------------------load database-------------------------------------------------
DB_FAISS_PATH="vectorstore/db_faiss"
embedding_model=HuggingFaceEmbeddings(model_name=MODEL)
db=FAISS.load_local(DB_FAISS_PATH, embedding_model, allow_dangerous_deserialization=True)


#----------------------------------------------Create QA chain-------------------------------------------
qa_chain=RetrievalQA.from_chain_type(
    llm=load_llm(repo_id),
    chain_type="stuff",
    retriever=db.as_retriever(search_kwargs={'k':10}),
    return_source_documents=True,
    chain_type_kwargs={'prompt':set_custom_prompt(CUSTOM_PROMPT_TEMPLATE)}
)


#------------------------------------now invoke with a single query----------------------------------------
user_query=input("Write Query Here: ")
response=qa_chain.invoke({'query':user_query})
print(response)
print("RESULT: ",response["result"])
print("SOURCE DOCUMENTS: ",response["source_documents"])