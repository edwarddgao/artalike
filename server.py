# server.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import faiss
import sqlite3
import numpy as np
from contextlib import contextmanager
import threading
import os

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Construct paths relative to the script directory
data_dir = os.path.join(script_dir, "data")
db_path = os.path.join(data_dir, "collections.db")
index_path = os.path.join(data_dir, "index.faiss")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # Adjust if your frontend runs elsewhere
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize FAISS index
print(f"Loading FAISS index from {index_path}...")
if not os.path.exists(index_path):
    raise FileNotFoundError(f"FAISS index file not found at {index_path}. Please run scripts/index.py first.")
index = faiss.read_index(index_path)
print("FAISS index loaded.")

# Initialize a global SQLite connection with thread safety
print(f"Connecting to database at {db_path}...")
if not os.path.exists(db_path):
    raise FileNotFoundError(f"Database file not found at {db_path}. Please run the data pipeline scripts first.")
db_lock = threading.Lock()
conn = sqlite3.connect(db_path, check_same_thread=False)
cursor = conn.cursor()
print("Database connection established.")

@contextmanager
def get_db():
    with db_lock:
        try:
            yield cursor
            # No commit/rollback here as we are only reading
        except Exception as e:
            print(f"Database error: {e}") # Simple error logging
            raise e

@app.get("/api/search")
def search(url: str, offset: int = 0, limit: int = 20):
    with get_db() as cursor:
        # Get the query embedding
        cursor.execute("SELECT embedding FROM embeddings WHERE url = ?", (url,))
        result = cursor.fetchone()
        if not result:
            return {"results": []}
        embedding = np.frombuffer(result[0], dtype=np.float32)

        # Calculate k for FAISS search
        k = offset + limit
        D, I = index.search(embedding.reshape(1, -1), k=k)

        # Adjust IDs (FAISS is 0-indexed, SQLite is 1-indexed)
        neighbor_ids = (I[0][offset:] + 1).tolist()
        placeholder = ','.join(['?'] * len(neighbor_ids))

        # Fetch image data including thumbnail_url
        cursor.execute(f"""
            SELECT url, width, height, thumbnail_url
            FROM embeddings 
            WHERE id IN ({placeholder})
        """, neighbor_ids)

        # Map results including thumbnail_url
        results = [
            {
                "url": row[0],
                "width": row[1],
                "height": row[2],
                "thumbnail_url": row[3] # Added
            }
            for row in cursor.fetchall()
        ]
    return {"results": results}

@app.get("/api/random")
def random_images(offset: int = 0, limit: int = 20):
    with get_db() as cursor:
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        total = cursor.fetchone()[0]

        if total == 0:
            return {"results": []}

        # Fetch random images including thumbnail_url
        cursor.execute("""
            SELECT url, width, height, thumbnail_url
            FROM embeddings 
            ORDER BY RANDOM()
            LIMIT ? OFFSET ?
        """, (limit, offset))

        # Map results including thumbnail_url
        results = [
            {
                "url": row[0],
                "width": row[1],
                "height": row[2],
                "thumbnail_url": row[3] # Added
            }
            for row in cursor.fetchall()
        ]
    return {"results": results}

# Serve static files (HTML, CSS, JS)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

print("Server setup complete. Ready for requests.")
