import sqlite3
import faiss
import numpy as np
from tqdm import tqdm

# Connect to database
conn = sqlite3.connect("data/collections.db")
cursor = conn.cursor()

# Get all embeddings ordered by ID
cursor.execute("SELECT id, embedding FROM embeddings ORDER BY id")
rows = cursor.fetchall()
num_vectors = len(rows)
dimension = 1152  # Your embedding dimension
print(f"Number of rows in embeddings table: {num_vectors}")

# Create IVFFlat index
nlist = int(np.sqrt(num_vectors))  # Rule of thumb: sqrt of dataset size
print(f"Creating IVFFlat index with {nlist} clusters")

# Create quantizer
quantizer = faiss.IndexFlatIP(dimension)  # Use IP (Inner Product) similarity
# Create IVF index
index = faiss.IndexIVFFlat(quantizer, dimension, nlist, faiss.METRIC_INNER_PRODUCT)

# Convert embeddings to numpy array for training
print("Preparing training data...")
training_vectors = np.zeros((num_vectors, dimension), dtype=np.float32)
for i, (_, embedding_blob) in enumerate(rows):
    training_vectors[i] = np.frombuffer(embedding_blob, dtype=np.float32)

# Train the index
print("Training index...")
index.train(training_vectors)

# Add embeddings to index in order
print("Adding vectors to index...")
for faiss_ix, (db_ix, embedding_blob) in tqdm(enumerate(rows)):
    assert faiss_ix == db_ix - 1
    embedding = np.frombuffer(embedding_blob, dtype=np.float32)
    index.add(embedding.reshape(1, -1))

# Set default nprobe value (can be adjusted at search time)
index.nprobe = 16  # Adjust based on your accuracy/speed requirements

# Save the index
print("Saving index...")
faiss.write_index(index, "data/index.faiss")
conn.close()

print("Done!")