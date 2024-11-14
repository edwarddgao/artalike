# scripts/download.py
import sqlite3
import json
import pandas as pd

from img2dataset import download

db_path = "../data/collections.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def is_valid_image_url(url):
    if not url:
        return False
    url = url.strip().lower()
    return url.startswith(('http://', 'https://')) and url.endswith(('.jpg', '.jpeg', '.png', '.gif'))

# Move all the execution code into a main function
def main():
    image_id_pairs = []
    
    # Handle Louvre data
    cursor.execute("SELECT id, data FROM artworks WHERE museum = 'louvre'")
    for row in cursor.fetchall():
        id = row[0]
        data = json.loads(row[1])
        
        if 'image' in data:
            for img in data['image']:
                if 'urlImage' in img and img['urlImage']:
                    url = img['urlImage']
                    if is_valid_image_url(url):
                        image_id_pairs.append((url, id))

    # Handle Met data  
    cursor.execute("SELECT id, data FROM artworks WHERE museum = 'met'")
    for row in cursor.fetchall():
        id = row[0]
        data = json.loads(row[1])
        
        # Add primary image if exists
        if 'primaryImage' in data and data['primaryImage']:
            image_id_pairs.append((data['primaryImage'], id))
        
        # Add additional images
        if 'additionalImages' in data and data['additionalImages']:
            for url in data['additionalImages']:
                if is_valid_image_url(url):
                    image_id_pairs.append((url, id))

    conn.close()

    print("Number of image-id pairs:", len(image_id_pairs))

    url_col = "URL"
    id_col = "ID"
    df = pd.DataFrame(image_id_pairs, columns=[url_col, id_col])
    df = df.drop_duplicates(subset=[url_col], keep='first')
    df.to_csv("data/image_urls.csv", index=False)

    download(
        processes_count=8,
        thread_count=32,
        url_list="data/image_urls.csv",
        image_size=512,
        output_folder="data/images",
        output_format="webdataset",
        input_format="csv",
        url_col=url_col,
        caption_col=id_col,
    )

if __name__ == '__main__':
    main()
