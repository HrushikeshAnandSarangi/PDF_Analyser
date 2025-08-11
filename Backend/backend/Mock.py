from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import jwt
from datetime import datetime, timedelta
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

# Authentication settings
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class User(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class QuestionRequest(BaseModel):
    question: str
    chat_history: List[dict] = []

# User database (replace with actual database in production)
users_db = {
    "admin": {
        "username": "admin",
        "hashed_password": "hashed_admin_password",  # Use proper hashing in production
    }
}

# Authentication functions
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        if username not in users_db:
            raise HTTPException(status_code=401, detail="User not found")
        return users_db[username]
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

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
openai_api_key = ""
if not openai_api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set")

embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
vector_store = None
qa_chain = None

# API endpoints
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_db.get(form_data.username)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token({"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    global vector_store, qa_chain
    
    # Save uploaded file
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # Load and process document
        loader = get_loader_for_file(file_path)
        documents = loader.load()
        
        # Split text into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        texts = text_splitter.split_documents(documents)
        
        # Create vector store
        vector_store = FAISS.from_documents(texts, embeddings)
        
        # Initialize QA chain
        llm = ChatOpenAI(temperature=0, openai_api_key=openai_api_key)
        qa_chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=vector_store.as_retriever(),
            return_source_documents=True
        )
        
        return {"message": "File processed successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up uploaded file
        os.remove(file_path)

@app.post("/ask")
async def ask_question(
    request: QuestionRequest,
    current_user: User = Depends(get_current_user)
):
    if not vector_store or not qa_chain:
        raise HTTPException(status_code=400, detail="No document has been uploaded yet")
    
    try:
        # Process question
        result = qa_chain({
            "question": request.question,
            "chat_history": request.chat_history
        })
        
        # Extract relevant context
        context = [doc.page_content for doc in result["source_documents"]]
        
        return {
            "answer": result["answer"],
            "context": context
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
