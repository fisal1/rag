from typing import List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct,VectorParams

import httpx
import uuid
from fastapi.middleware.cors import CORSMiddleware
import math



# Initialize FastAPI
app = FastAPI()
# Configure CORS middleware to allow all origins, methods, and headers
origins = ["*"]  # Allows all origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # Set to True if your API uses credentials (cookies, authorization headers)
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

from fastapi import UploadFile, File
import fitz  # PyMuPDF


# === CONFIG ===
import os
from dotenv import load_dotenv


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "doc")
CHUNK_SIZE = 5000

# Qdrant client
qdrant = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

# === Request Schema ===
class DocumentInput(BaseModel):
    content: str

# === Helper: Get Embedding from Gemini ===
async def get_gemini_embedding(text: str):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    json_data = {
        "model": "models/gemini-embedding-001",
        "content": {
            "parts": [{"text": text}]
        }
    }

  

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=json_data)
            response.raise_for_status()
            embedding = response.json()["embedding"]["values"]
            return embedding
        except Exception as e:
            print(str(e))


# === Endpoint: Add Document ===

@app.post("/add_document")
async def add_document(doc: DocumentInput):
    try:
        # Step 1: Generate embedding using Gemini
        embedding = await get_gemini_embedding(doc.content)
        point_id = str(uuid.uuid4())

        # Step 2: Check if collection exists
        existing_collections = qdrant.get_collections().collections
        collection_names = [c.name for c in existing_collections]

        if COLLECTION_NAME not in collection_names:
            print(f"Collection '{COLLECTION_NAME}' not found. Creating...")
            qdrant.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=3072,
                    distance="Cosine"
                )
            )
            print(f"Collection '{COLLECTION_NAME}' created successfully.")

        # Step 3: Create and insert point
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={"content": doc.content},
        )
        

        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=[point]
        )


        return {"status": "success", "id": point_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding document: {str(e)}")


# === Endpoint: Search Document ===
@app.get("/search_document")
async def search_document(
    query: str = Query(..., description="Query string to search"),
    limit: int = Query(5, gt=0, le=50, description="Number of top results to return (1-50)")
):
    try:
        embedding = await get_gemini_embedding(query)
        search_result = qdrant.search(
            collection_name=COLLECTION_NAME,
            query_vector=embedding,
            limit=limit,
        )
        results = [
            {
                "id": hit.id,
                "score": hit.score,
                "content": hit.payload.get("content", "")
            }
            for hit in search_result
        ]
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


def split_text_into_chunks(text, chunk_size=CHUNK_SIZE):
    text_length = len(text)
    num_chunks = math.ceil(text_length / chunk_size)

    # Recalculate a slightly larger chunk size so the text is evenly divided
    adjusted_chunk_size = math.ceil(text_length / num_chunks)

    chunks = [text[i:i + adjusted_chunk_size] for i in range(0, text_length, adjusted_chunk_size)]
    return chunks


@app.post("/upload_pdfs")
async def upload_pdfs(files: List[UploadFile] = File(...)):
    responses = []
    for file in files:
        try:
            if not file.filename.lower().endswith(".pdf"):
                responses.append({"filename": file.filename, "error": "Only PDF files are supported."})
                continue

            pdf_bytes = await file.read()
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            full_text = ""
            for page in pdf_doc:
                full_text += page.get_text()
            pdf_doc.close()

            if not full_text.strip():
                responses.append({"filename": file.filename, "error": "No readable text found in PDF."})
                continue

            # Chunk and upload each separately
            chunks = split_text_into_chunks(full_text)
            chunk_results = []

            for idx, chunk in enumerate(chunks):
                doc = DocumentInput(content=chunk)
                result = await add_document(doc)
                chunk_results.append({
                    "chunk_index": idx,
                    "chunk_id": result["id"]
                })

            responses.append({
                "filename": file.filename,
                "status": "success",
                "chunks_uploaded": len(chunk_results),
                "chunks": chunk_results
            })

        except Exception as e:
            responses.append({"filename": file.filename, "error": str(e)})

    return {"results": responses}

# === Helper: Search Top Documents ===
async def search_top_documents(query: str, limit: int = 10):
    try:
        search_response = await search_document(query=query, limit=limit)
        top_docs = [doc["content"] for doc in search_response["results"] if doc["content"]]
        return top_docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document search failed: {str(e)}")

# === Helper: Generate Answer using Gemini LLM ===

async def generate_answer_with_gemini(user_prompt: str) -> str:
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?key={GEMINI_API_KEY}"
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": user_prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "thinkingConfig": {
                    "thinkingBudget": -1
                }
            },
            "tools": [
                {
                    "googleSearch": {}
                }
            ]
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            data = response.json()

            # If streaming format has multiple chunks
            if isinstance(data, list):
                chunks = [chunk["candidates"][0]["content"]["parts"][0]["text"] for chunk in data if "candidates" in chunk]
                return "".join(chunks)
            else:
                # Non-stream fallback
                return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini API call failed: {str(e)}")

# === Controller: Ask Question ===
class UserQuery(BaseModel):
    question: str

@app.post("/ask_question")
async def ask_question(query: UserQuery):
    try:
        top_docs = await search_top_documents(query.question, limit=10)

        if not top_docs:
            raise HTTPException(status_code=404, detail="No relevant documents found.")

        # Truncate context to keep it safe (max ~4000 characters)
        context_text = "\n\n".join(top_docs)

        print("context_text")
        print(context_text[:100])

        # Generate answer from LLM
        prompt = f"""You are a helpful assistant. Use the following context to answer the question:

            Context:
            {context_text}

            Question:
            {query.question}
           
            Guardrails:
            Answer should be less than 100 words.
        """
        answer = await generate_answer_with_gemini(prompt)

        return {
            "question": query.question,
            "answer": answer,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Answering failed: {str(e)}")

