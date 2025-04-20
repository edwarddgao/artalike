# scripts/index.py
import sqlite3
import faiss
import numpy as np
from tqdm import tqdm
import os

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Construct paths relative to the script directory
data_dir = os.path.join(script_dir, "../data")
db_path = os.path.join(data_dir, "collections.db")
index_path = os.path.join(data_dir, "index.faiss")

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all embeddings ordered by ID
cursor.execute("SELECT id, embedding FROM embeddings ORDER BY id")
rows = cursor.fetchall()
num_vectors = len(rows)
dimension = 1152    # SigLip embedding dimension
print(f"Number of rows in embeddings table: {num_vectors}")

# Create PQ-IVF index parameters
nlist = int(np.sqrt(num_vectors))  # Number of centroids/clusters
M = 64  # Number of subquantizers (determines compression)
nbits = 8  # Bits per subquantizer (standard choice)
print(f"Creating IVF-PQ index with {nlist} clusters and {M} subquantizers")

base_index = faiss.IndexFlatIP(dimension)
index = faiss.IndexIVFPQ(base_index, dimension, nlist, M, nbits, faiss.METRIC_INNER_PRODUCT)

print("Preparing training data...")
training_vectors = np.zeros((num_vectors, dimension), dtype=np.float32)
for i, (_, embedding_blob) in enumerate(rows):
    training_vectors[i] = np.frombuffer(embedding_blob, dtype=np.float32)

print("Training index...")
index.train(training_vectors)

print("Adding vectors to index...")
for faiss_ix, (db_ix, embedding_blob) in tqdm(enumerate(rows)):
    assert faiss_ix == db_ix - 1
    embedding = np.frombuffer(embedding_blob, dtype=np.float32)
    index.add(embedding.reshape(1, -1))

# Set search parameters
index.nprobe = 16    # Number of clusters to visit during search

print("Saving index...")
faiss.write_index(index, index_path)
conn.close()

print("Done!")