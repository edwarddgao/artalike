# server.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import faiss
import sqlite3
import numpy as np
from contextlib import contextmanager
import threading

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize FAISS index
index = faiss.read_index("data/index.faiss")

# Initialize a global SQLite connection with thread safety
db_lock = threading.Lock()
conn = sqlite3.connect("data/collections.db", check_same_thread=False)
cursor = conn.cursor()

@contextmanager
def get_db():
    with db_lock:
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

@app.get("/search")
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

        # Fetch image data
        cursor.execute(f"""
            SELECT url, width, height 
            FROM embeddings 
            WHERE id IN ({placeholder})
        """, neighbor_ids)

        results = [{"url": row[0], "width": row[1], "height": row[2]} for row in cursor.fetchall()]
    return {"results": results}

@app.get("/random")
def random_images(offset: int = 0, limit: int = 20):
    with get_db() as cursor:
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        total = cursor.fetchone()[0]

        if total == 0:
            return {"results": []}

        # Fetch random images using OFFSET and LIMIT
        cursor.execute("""
            SELECT url, width, height 
            FROM embeddings 
            ORDER BY RANDOM()
            LIMIT ? OFFSET ?
        """, (limit, offset))

        results = [{"url": row[0], "width": row[1], "height": row[2]} for row in cursor.fetchall()]
    return {"results": results}
