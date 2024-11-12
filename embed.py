import webdataset as wds
import torch
import torchvision.transforms as transforms
from transformers import AutoModel
import sqlite3


# Set up device and model
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = AutoModel.from_pretrained(
    "google/siglip-so400m-patch14-384",
    trust_remote_code=True
).to(device).eval()

# Set up dataset
transform = transforms.Compose([
    transforms.Resize((384, 384), interpolation=transforms.InterpolationMode.BICUBIC),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5])
])

# Set up dataset pipeline
dataset = (
    wds.WebDataset("data/images/{00000..00112}.tar", shardshuffle=False)
    .decode("pil")
    .to_tuple("jpg", "json")
    .map(lambda x: {
        "image": transform(x[0]),
        "id": int(x[1]["caption"]),
        "url": x[1]["url"]
    })
)

# Process batches
dataloader = torch.utils.data.DataLoader(
    dataset,
    batch_size=256,
    num_workers=8,
)

conn = sqlite3.connect("data/collections.db")
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        artwork_id INTEGER,
        embedding BLOB,
        FOREIGN KEY(artwork_id) REFERENCES artworks(id)
    )
''')

with torch.inference_mode():
    for batch_idx, batch in enumerate(dataloader):
        try:
            # Check which URLs don't exist in the database
            urls = batch["url"]
            cursor.execute('SELECT url FROM embeddings WHERE url IN ({})'.format(
                ','.join(['?'] * len(urls))), urls)
            existing_urls = set(row[0] for row in cursor.fetchall())
            
            # Filter batch to only process new URLs
            mask = [url not in existing_urls for url in urls]
            if not any(mask):
                print(f"Batch {batch_idx}: All artworks already processed")
                continue
                
            # Process only new images
            batch_images = batch["image"][mask].to(device)
            new_urls = [url for i, url in enumerate(urls) if mask[i]]
            new_ids = [id for i, id in enumerate(batch["id"]) if mask[i]]
            
            # Get embeddings for new images
            batch_embeddings = model.get_image_features(batch_images)
            batch_embeddings /= torch.norm(batch_embeddings, dim=1, keepdim=True)
            batch_embeddings = batch_embeddings.cpu().numpy()

            cursor.executemany(
                "INSERT INTO embeddings (url, artwork_id, embedding) VALUES (?, ?, ?)",
                [(url, int(art_id), embedding.tobytes()) 
                for url, embedding, art_id in zip(new_urls, batch_embeddings, new_ids)]
            )
            conn.commit()
            print(f"Processed batch {batch_idx}: {len(new_urls)} artworks")
        except Exception as e:
            print(f"Error processing batch {batch_idx}: {e}")

conn.close()