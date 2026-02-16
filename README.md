# [Artalike](https://artalike.org/) - Image Similarity Search

Artalike is a web application that allows users to find visually similar images within a collection. It uses FAISS for efficient similarity search based on image embeddings.

## Features

*   Fetches images and their metadata (using `crawl.py` and `download.py`).
*   Generates image embeddings using a pre-trained model (`embed.py`).
*   Builds a FAISS index for fast similarity searches (`index.py`).
*   Provides a web interface (`index.html`, `app.js`, `style.css`) to:
    *   Display a gallery of images.
    *   Implement infinite scrolling with lazy loading and prefetching.
    *   Allow users to click an image to find visually similar ones.
*   Backend API built with FastAPI (`server.py`) to handle search and random image requests.

## Technology Stack

*   **Backend:** Python, FastAPI, FAISS, SQLite
*   **Frontend:** Vanilla JavaScript, HTML, CSS
*   **Data Pipeline:** `img2dataset` (implicitly used by scripts)

## Project Structure

```
artalike/
├── data/                 # (Created by scripts) Contains database and FAISS index
│   ├── collections.db
│   └── index.faiss
├── downloaded_data/      # (Created by download.py) Stores downloaded image shards (.tar files)
├── scripts/              # Python scripts for data processing and indexing
│   ├── crawl.py          # (Optional) Example script for crawling image URLs
│   ├── download.py       # Downloads images specified in a metadata file
│   ├── embed.py          # Generates embeddings and stores metadata in the database
│   └── index.py          # Builds the FAISS index from embeddings
├── static/               # Frontend web files
│   ├── app.js            # Main JavaScript logic for the frontend
│   ├── index.html        # Main HTML structure
│   └── style.css         # CSS for styling the gallery
├── server.py             # FastAPI backend server
└── README.md             # This file
```

## Setup

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <repository_url>
    cd artalike
    ```

2.  **Create a Python virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    You'll need Python packages for the backend and scripts. Create a `requirements.txt` file with the following content:
    ```txt
    fastapi
    uvicorn[standard]
    faiss-cpu # or faiss-gpu if you have CUDA configured
    numpy
    Pillow
    img2dataset
    webdataset
    sqlite-utils # Helpful for inspecting the DB
    ```
    Then install them:
    ```bash
    pip install -r requirements.txt
    ```

## Data Pipeline (Running the Scripts)

**Important:** Run these scripts from the root `artalike` directory.

1.  **Prepare Metadata:** You need a metadata source for `download.py`. This could be a `.parquet` file or similar structure compatible with `img2dataset`, containing at least `url` and `thumbnail_url` columns. The `crawl.py` script is an *example* of how you *might* generate such data, but you'll likely need to adapt it or use your own data source. Let's assume you have `metadata.parquet`.

2.  **Download Images:**
    ```bash
    python scripts/download.py --url_list metadata.parquet --output_folder downloaded_data --image_size 512 --thread_count $(nproc) --compute_md5 True --save_additional_columns '["thumbnail_url"]'
    ```
    *   Adjust `--url_list` to your metadata file.
    *   `--output_folder` specifies where the `.tar` shards will be saved.
    *   `--save_additional_columns` ensures the `thumbnail_url` is kept.

3.  **Generate Embeddings:**
    ```bash
    python scripts/embed.py
    ```
    *   This script reads the `.tar` files from `downloaded_data`, generates embeddings, and saves them along with metadata (including `url`, `width`, `height`, `thumbnail_url`) into `data/collections.db`.

4.  **Build FAISS Index:**
    ```bash
    python scripts/index.py
    ```
    *   This reads the embeddings from `data/collections.db` and builds the `data/index.faiss` file.

## Running the Application

1.  **Start the backend server:**
    Make sure you are in the root `artalike` directory.
    ```bash
    uvicorn server:app --reload
    ```
    *   `--reload` automatically restarts the server when code changes are detected (useful for development).

2.  **Access the frontend:**
    Open your web browser and navigate to `http://localhost:8000`.

## How it Works

1.  **Data Preparation:** The scripts download images, extract features (embeddings), and store them along with metadata in a database. A FAISS index is built for fast nearest-neighbor search on these embeddings.
2.  **Backend Server:** The FastAPI server loads the FAISS index and connects to the database. It exposes API endpoints (`/api/random`, `/api/search`).
3.  **Frontend:**
    *   The browser loads `index.html`, which includes `app.js` and `style.css`.
    *   `app.js` calls the `/api/random` endpoint initially to get a batch of images.
    *   Images are displayed using thumbnails (`thumbnail_url`) initially. Full images (`url`) are lazy-loaded as the user scrolls.
    *   Infinite scrolling fetches more images from `/api/random` or `/api/search` using offsets as the user scrolls down. Prefetching attempts to load the next batch before the user hits the bottom.
    *   Clicking an image triggers a call to `/api/search` with the clicked image's URL, replacing the grid content with similar images found by the backend using FAISS. 
