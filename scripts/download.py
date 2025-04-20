# scripts/download.py
import sqlite3
import json
import pandas as pd
import os # Added import

from img2dataset import download

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Construct paths relative to the script directory
db_path = os.path.join(script_dir, "../data/collections.db")
csv_path = os.path.join(script_dir, "../data/image_urls.csv")
output_dir = os.path.join(script_dir, "../data/images")

# db_path = "../data/collections.db" # Old path definition
conn = sqlite3.connect(db_path) # Use constructed path
cursor = conn.cursor()

def is_valid_image_url(url):
    if not url:
        return False
    url = url.strip().lower()
    return url.startswith(('http://', 'https://')) and url.endswith(('.jpg', '.jpeg', '.png', '.gif'))

# Move all the execution code into a main function
def main():
    image_data = [] # Changed from image_id_pairs
    
    # Handle Louvre data
    print("Processing Louvre data...")
    cursor.execute("SELECT id, data FROM artworks WHERE museum = 'louvre'")
    for row in cursor.fetchall():
        artwork_id = row[0]
        try:
            data = json.loads(row[1])
        except json.JSONDecodeError:
            print(f"Louvre: Error decoding JSON for artwork ID {artwork_id}")
            continue
            
        if 'image' in data and isinstance(data['image'], list):
            for img_data in data['image']:
                if isinstance(img_data, dict) and 'urlImage' in img_data and img_data['urlImage']:
                    url = img_data['urlImage']
                    thumbnail_url = img_data.get('UrlThumbnail') # Get thumbnail if available
                    if is_valid_image_url(url):
                        image_data.append({
                            "URL": url,
                            "ID": artwork_id,
                            "thumbnail_url": thumbnail_url if is_valid_image_url(thumbnail_url) else None
                        })

    # Handle Met data  
    print("Processing Met data...")
    cursor.execute("SELECT id, data FROM artworks WHERE museum = 'met'")
    for row in cursor.fetchall():
        artwork_id = row[0]
        try:
            data = json.loads(row[1])
        except json.JSONDecodeError:
            print(f"Met: Error decoding JSON for artwork ID {artwork_id}")
            continue
        
        primary_thumbnail = data.get('primaryImageSmall')
        primary_thumbnail = primary_thumbnail if is_valid_image_url(primary_thumbnail) else None

        # Add primary image if exists
        if 'primaryImage' in data and data['primaryImage']:
            url = data['primaryImage']
            if is_valid_image_url(url):
                image_data.append({
                    "URL": url,
                    "ID": artwork_id,
                    "thumbnail_url": primary_thumbnail
                })
        
        # Add additional images
        if 'additionalImages' in data and isinstance(data['additionalImages'], list):
            for url in data['additionalImages']:
                if is_valid_image_url(url):
                    image_data.append({
                        "URL": url,
                        "ID": artwork_id,
                        "thumbnail_url": None # No specific thumbnail for additional images
                    })

    conn.close()

    print(f"Total image entries found before filtering: {len(image_data)}")

    # Filter image_data to keep only entries with a valid thumbnail_url
    filtered_image_data = [item for item in image_data if item.get('thumbnail_url')]
    print(f"Total image entries after filtering for thumbnails: {len(filtered_image_data)}")

    if not filtered_image_data:
        print("No image data with thumbnails found to process.")
        return

    # Define column names
    url_col = "URL"
    id_col = "ID"
    thumb_col = "thumbnail_url"

    df = pd.DataFrame(filtered_image_data) # Use filtered data
    print(f"DataFrame shape before drop_duplicates: {df.shape}")
    df = df.drop_duplicates(subset=[url_col], keep='first')
    print(f"DataFrame shape after drop_duplicates: {df.shape}")

    # Ensure thumbnail_url column exists even if all values are None
    if thumb_col not in df.columns:
        df[thumb_col] = None

    # Specify column order for CSV: URL, ID, then extra columns
    csv_columns = [url_col, id_col, thumb_col]
    df.to_csv(csv_path, index=False, columns=csv_columns)
    print(f"Saved image URLs and thumbnail URLs to {csv_path}")

    print("Starting image download with img2dataset...")
    download(
        processes_count=8,
        thread_count=32,
        url_list=csv_path,
        image_size=512,
        output_folder=output_dir,
        output_format="webdataset",
        input_format="csv",
        url_col=url_col,
        caption_col=id_col, # Use the ID column as caption
        save_additional_columns=[thumb_col] # Use save_additional_columns
        # extra_columns=[thumb_col] # Remove extra_columns parameter
    )
    print("Image download finished.")

if __name__ == '__main__':
    main()
