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
import random

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Construct paths relative to the script directory
data_dir = os.path.join(script_dir, "data")
db_path = os.path.join(data_dir, "collections.db")
index_path = os.path.join(data_dir, "index.faiss")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # Allow all origins for simplicity, restrict in production if needed
    allow_origins=["*"], 
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
print(f"FAISS index loaded. Index size: {index.ntotal}") # Log index size

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

        # Handle cases where k > index.ntotal
        if not neighbor_ids:
            return {"results": []}

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
    # Use the total count from the FAISS index
    total_vectors = index.ntotal
    if total_vectors == 0:
        print("Error: FAISS index is empty.")
        return {"results": []}

    # Ensure limit doesn't exceed total vectors
    actual_limit = min(limit, total_vectors)

    # Generate unique random FAISS indices (0-based)
    try:
        random_indices_0_based = random.sample(range(total_vectors), actual_limit)
    except ValueError as e:
        # Handle case where limit > total_vectors (should be caught by min, but safety check)
        print(f"Warning generating random indices: {e}. Using population size.")
        random_indices_0_based = list(range(total_vectors))
        random.shuffle(random_indices_0_based)

    # Convert to 1-based database IDs
    random_db_ids = [idx + 1 for idx in random_indices_0_based]

    if not random_db_ids:
        return {"results": []}

    placeholder = ','.join(['?'] * len(random_db_ids))

    with get_db() as cursor:
        # Fetch data for the randomly selected IDs
        # No need for LIMIT or OFFSET here as we fetch specific IDs
        cursor.execute(f"""
            SELECT url, width, height, thumbnail_url
            FROM embeddings
            WHERE id IN ({placeholder})
        """, random_db_ids)

        # Map results including thumbnail_url
        fetched_rows = cursor.fetchall()
        # Create a dictionary for quick lookup by ID (Corrected syntax)
        results_map = {
            row[0]: { # Assuming URL is unique and suitable as a key
                "url": row[0],
                "width": row[1],
                "height": row[2],
                "thumbnail_url": row[3]
            }
            for row in fetched_rows
        }
        # Reorder results based on the original random ID list to maintain some randomness in order?
        # This might not be strictly necessary if frontend doesn't care about order
        # For now, return in the order the DB gave them
        results = list(results_map.values())

        # If DB returned fewer rows than requested IDs (shouldn't happen if index/DB sync), log warning
        if len(results) != len(random_db_ids):
            print(f"Warning: Requested {len(random_db_ids)} random IDs but DB returned {len(results)}")

    return {"results": results}

# Serve static files (HTML, CSS, JS)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

print("Server setup complete. Ready for requests.")
