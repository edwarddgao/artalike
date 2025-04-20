# scripts/crawl.py
import asyncio
import aiohttp
import sqlite3
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import os

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Construct paths relative to the script directory
db_default_path = os.path.join(script_dir, "../data/collections.db")
cookie_default_path = os.path.join(script_dir, "../cookie.txt")

class Crawler:
    def __init__(self, db_path=db_default_path, cookie_path=cookie_default_path):
        # Rate limit
        self.rate_limit = 80 # requests per second
        # Read cookie from the correct path
        try:
            with open(cookie_path, "r") as f:
                self.met_cookies = f.read().strip()
        except FileNotFoundError:
            print(f"Error: Cookie file not found at {cookie_path}")
            self.met_cookies = "" # Or handle error appropriately

        # Initialize database
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS artworks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                museum TEXT,
                accession_ref TEXT,
                data TEXT,
                updated DATETIME,
                UNIQUE(museum, accession_ref)
            )
        ''')
        # Add index if it doesn't exist (improves lookup speed)
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_artworks_museum_ref ON artworks (museum, accession_ref)')
        
    async def get_existing_refs(self, museum):
        """Fetch existing accession_refs for a given museum from the database."""
        self.cursor.execute("SELECT accession_ref FROM artworks WHERE museum = ?", (museum,))
        return {row[0] for row in self.cursor.fetchall()}
        
    async def crawl(self):
        headers = {"Cookie": self.met_cookies}
        async with aiohttp.ClientSession(headers=headers) as session:
            # Create tasks for both museums
            tasks = [
                self.crawl_met(session),
                self.crawl_louvre(session)
            ]
            await asyncio.gather(*tasks)

        # Close the synchronous connection without await
        print("Closing database connection...")
        self.conn.close()

    async def crawl_met(self, session):
        print("Starting Met crawl...")
        # Get accession refs
        refs = [] # Initialize refs
        try:
            async with session.get("https://collectionapi.metmuseum.org/public/collection/v1/objects") as response:
                response.raise_for_status() # Raise exception for bad status codes
                refs = (await response.json())["objectIDs"]
                print(f"Met: Found {len(refs)} object IDs.") # Added print
        except Exception as e:
            print(f"Met: Error fetching object IDs: {e}")
            return # Stop if we can't get IDs

        if not refs:
            print("Met: No object IDs found.")
            return

        # Check existing refs in DB
        print("Met: Checking database for existing artworks...")
        existing_refs_set = await self.get_existing_refs("met")
        api_refs_set = {str(ref) for ref in refs} # Ensure refs are strings for comparison
        missing_refs = list(api_refs_set - existing_refs_set)
        print(f"Met: Found {len(missing_refs)} new or missing artworks to process.")

        if not missing_refs:
            print("Met: No new artworks to crawl.")
            return

        # Process artworks with concurrency limit
        sem = asyncio.Semaphore(50)
        processed_count = 0 # Counter
        total_refs = len(missing_refs) # Total count based on missing refs

        async def process_artwork(ref):
            nonlocal processed_count
            async with sem:
                # print(f"Met: Starting processing artwork {ref}...") # Optional: Can be very verbose
                await asyncio.sleep(1 / self.rate_limit)
                url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{ref}"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.save_artwork("met", ref, data)
                            processed_count += 1
                            if processed_count % 100 == 0: # Print progress every 100 items
                                print(f"Met: Processed {processed_count}/{total_refs} artworks...")
                            # print(f"Met: Finished processing artwork {ref}.") # Optional: Can be very verbose
                        # else: # Optional: Log non-200 responses if needed
                            # print(f"Met: Received status {response.status} for artwork {ref}")
                except Exception as e:
                    print(f"Error processing Met artwork {ref}: {e}")

        await asyncio.gather(*[process_artwork(ref) for ref in missing_refs]) # Process only missing refs
        print(f"Met: Committing {processed_count} new artworks to database...")
        self.conn.commit() # Commit after processing all missing refs for this museum
        print(f"Met: Finished crawling {processed_count} artworks.")

    async def crawl_louvre(self, session):
        print("Starting Louvre crawl...")
        # Get accession refs from sitemap
        refs = []
        try:
            async with session.get("https://collections.louvre.fr/sitemap.xml") as response:
                response.raise_for_status()
                root = ET.fromstring(await response.text())
                
            namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            sitemap_urls = [sitemap.text for sitemap in root.findall('.//ns:loc', namespace)]
            print(f"Louvre: Found {len(sitemap_urls)} sitemaps in index.") # Added print

            for sitemap_url in sitemap_urls:
                print(f"Louvre: Processing sitemap {sitemap_url}...") # Added print
                async with session.get(sitemap_url) as response:
                    response.raise_for_status()
                    sitemap_root = ET.fromstring(await response.text())
                    count_before = len(refs) # Count before adding from this sitemap
                    for url in sitemap_root.findall('.//ns:loc', namespace):
                        if '/ark:/53355/' in url.text:
                            ref = url.text.split('/ark:/53355/')[-1].replace('.json', '')
                            if ref: # Ensure ref is not empty
                                refs.append(ref)
                    count_after = len(refs)
                    print(f"Louvre: Added {count_after - count_before} refs from {sitemap_url}.") # Added print

            print(f"Louvre: Found {len(refs)} total object refs.") # Added print
        except Exception as e:
            print(f"Louvre: Error fetching or parsing sitemaps: {e}")
            return # Stop if we can't get refs

        if not refs:
            print("Louvre: No object refs found.")
            return

        # Check existing refs in DB
        print("Louvre: Checking database for existing artworks...")
        existing_refs_set = await self.get_existing_refs("louvre")
        api_refs_set = set(refs) # Refs are already strings here
        missing_refs = list(api_refs_set - existing_refs_set)
        print(f"Louvre: Found {len(missing_refs)} new or missing artworks to process.")

        if not missing_refs:
            print("Louvre: No new artworks to crawl.")
            return

        # Process artworks with concurrency limit
        sem = asyncio.Semaphore(50)
        processed_count = 0 # Counter
        total_refs = len(missing_refs) # Total count based on missing refs

        async def process_artwork(ref):
            nonlocal processed_count
            async with sem:
                # print(f"Louvre: Starting processing artwork {ref}...") # Optional: Can be very verbose
                await asyncio.sleep(1 / self.rate_limit)
                url = f"https://collections.louvre.fr/ark:/53355/{ref}.json"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.save_artwork("louvre", ref, data)
                            processed_count += 1
                            if processed_count % 100 == 0: # Print progress every 100 items
                                print(f"Louvre: Processed {processed_count}/{total_refs} artworks...")
                            # print(f"Louvre: Finished processing artwork {ref}.") # Optional: Can be very verbose
                        # else: # Optional: Log non-200 responses if needed
                            # print(f"Louvre: Received status {response.status} for artwork {ref}")
                except Exception as e:
                    print(f"Error processing Louvre artwork {ref}: {e}")

        await asyncio.gather(*[process_artwork(ref) for ref in missing_refs]) # Process only missing refs
        print(f"Louvre: Committing {processed_count} new artworks to database...")
        self.conn.commit() # Commit after processing all missing refs for this museum
        print(f"Louvre: Finished crawling {processed_count} artworks.")

    def save_artwork(self, museum, ref, data):
        # Use INSERT OR IGNORE to skip duplicates silently
        # No commit here, will be done in batches
        self.cursor.execute(
            'INSERT OR IGNORE INTO artworks (museum, accession_ref, data, updated) VALUES (?, ?, ?, ?)',
            (museum, str(ref), json.dumps(data), datetime.now().isoformat())) # Added museum back
        # self.conn.commit() # Removed commit from here

async def main():
    crawler = Crawler()
    await crawler.crawl()

if __name__ == "__main__":
    asyncio.run(main())