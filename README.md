to run use this cmd
--------
for backenf:
--------
cd backend

pip install -r requirements.txt

uvicorn main:app --reload --port 8000

add .env file in your backend with this variable:
-------------
GEMINI_API_KEY=

QDRANT_API_KEY=

QDRANT_URL=

COLLECTION_NAME=documents

for frontenf:
---------
cd frontend

npm install

npm start

