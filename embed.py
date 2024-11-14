# embed.py
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
    wds.WebDataset("data/images/{00000..00110}.tar", shardshuffle=False)
    .decode("pil")
    .to_tuple("jpg", "json")
    .map(lambda x: {
        "image": transform(x[0]),
        "artwork_id": x[1]["caption"],
        "url": x[1]["url"],
        "width": x[1]["original_width"],
        "height": x[1]["original_height"]
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
        width INTEGER,
        height INTEGER,
        FOREIGN KEY(artwork_id) REFERENCES artworks(id)
    )
''')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_embeddings_url ON embeddings(url)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_embeddings_artwork_id ON embeddings(artwork_id)')

with torch.inference_mode():
    for batch_idx, batch in enumerate(dataloader):
        try:
            # Extract batch data
            urls = batch["url"]
            artwork_ids = batch["artwork_id"].tolist()
            widths = batch["width"].tolist()
            heights = batch["height"].tolist()
            images = batch["image"].to(device)

            # Check which URLs already exist in the database to avoid duplicates
            # Fetch existing URLs in bulk for the current batch
            cursor.execute(f"SELECT url FROM embeddings WHERE url IN ({','.join(['?'] * len(urls))})", urls)
            existing_urls = set(row[0] for row in cursor.fetchall())
            
            # Filter batch to only process new URLs
            mask = [url not in existing_urls for url in urls]

            if not any(mask):
                print(f"Batch {batch_idx}: All artworks already processed")
                continue
                
            # Filter out existing artworks
            new_images = images[mask]
            new_urls = [url for i, url in enumerate(urls) if mask[i]]
            new_artwork_ids = [artwork_id for i, artwork_id in enumerate(artwork_ids) if mask[i]]
            new_widths = [width for i, width in enumerate(widths) if mask[i]]
            new_heights = [height for i, height in enumerate(heights) if mask[i]]
            
            # Get embeddings for new images
            batch_embeddings = model.get_image_features(new_images)
            batch_embeddings /= torch.norm(batch_embeddings, dim=1, keepdim=True)
            batch_embeddings = batch_embeddings.cpu().numpy()

            # Insert data into database
            cursor.executemany(
                "INSERT INTO embeddings (url, artwork_id, embedding, width, height) VALUES (?, ?, ?, ?, ?)",
                list(zip(new_urls, new_artwork_ids, batch_embeddings, new_widths, new_heights))
            )
            conn.commit()
            print(f"Processed batch {batch_idx}: {len(new_urls)} artworks")

        except Exception as e:
            print(f"Error processing batch {batch_idx}: {e}")

conn.close()
