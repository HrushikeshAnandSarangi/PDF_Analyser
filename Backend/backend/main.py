from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    CSVLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
import os
import shutil

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File processing functions
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_loader_for_file(file_path: str):
    file_extension = file_path.split(".")[-1].lower()
    if file_extension == "pdf":
        return PyPDFLoader(file_path)
    elif file_extension in ["docx", "doc"]:
        return Docx2txtLoader(file_path)
    elif file_extension == "txt":
        return TextLoader(file_path)
    elif file_extension == "csv":
        return CSVLoader(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_extension}")

# Vector store setup
# Replace this with your standard OpenAI API key (starting with sk-)
openai_api_key = "" # Use environment variable for the API key
if not openai_api_key:
    raise RuntimeError("Please set a valid OpenAI API key")

# Initialize with api_type and api_version for better compatibility
embeddings = OpenAIEmbeddings(
    openai_api_key=openai_api_key,
    model="text-embedding-ada-002"  # Explicitly specify the embeddings model
)
vector_store = None
qa_chain = None

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    global vector_store, qa_chain
    
    try:
        print(f"Uploading file: {file.filename}")
        
        # Save uploaded file
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        print(f"File saved at: {file_path}")
        
        # Load and process document
        loader = get_loader_for_file(file_path)
        documents = loader.load()
        print(f"Loaded {len(documents)} documents.")
        
        # Split text into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        texts = text_splitter.split_documents(documents)
        print(f"Number of text chunks: {len(texts)}")
        
        # Create vector store
        vector_store = FAISS.from_documents(texts, embeddings)
        print("FAISS vector store created successfully.")
        
        # Initialize QA chain
        llm = ChatOpenAI(
            temperature=0,
            openai_api_key=openai_api_key,
            model="gpt-3.5-turbo"  # Explicitly specify the chat model
        )
        qa_chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=vector_store.as_retriever(),
            return_source_documents=True
        )
        
        return {"message": "File processed successfully"}
    
    except ValueError as e:
        print(f"Error in file processing: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error during file processing: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error: " + str(e))
    finally:
        # Clean up uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted uploaded file: {file_path}")

@app.post("/ask")
async def ask_question(question: str = Body(..., embed=True)):
    global qa_chain
    if not vector_store or not qa_chain:
        raise HTTPException(status_code=400, detail="No document has been uploaded yet")

    if not question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    try:
        # Process question
        result = qa_chain({
            "question": question,
            "chat_history": []
        })
        
        # Extract relevant context
        context = [doc.page_content for doc in result["source_documents"]]
        
        return {
            "answer": result["answer"],
            "context": context
        }
    except Exception as e:
        print(f"Error during question processing: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error: " + str(e))
