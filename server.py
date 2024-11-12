from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import faiss
import sqlite3
import numpy as np
from contextlib import contextmanager

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

index = faiss.read_index("data/index.faiss")

@contextmanager
def get_db():
    conn = sqlite3.connect("data/collections.db")
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()

@app.get("/search")
def search(url: str, k: int = 10):
    with get_db() as cursor:
        cursor.execute("SELECT embedding FROM embeddings WHERE url = ?", (url,))
        embedding = np.frombuffer(cursor.fetchone()[0], dtype=np.float32)
        D, I = index.search(embedding.reshape(1, -1), k=k)
        cursor.execute("SELECT url FROM embeddings WHERE id IN ({})".format(
            ','.join(['?'] * len(I[0]))), (I[0] + 1).tolist())
        urls = [row[0] for row in cursor.fetchall()]
    return {"results": urls}

@app.get("/random")
def random(k: int = 10):
    with get_db() as cursor:
        cursor.execute("SELECT url FROM embeddings ORDER BY RANDOM() LIMIT ?", (k,))
        urls = [row[0] for row in cursor.fetchall()]
    return {"results": urls}