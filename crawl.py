# crawl.py
import asyncio
import aiohttp
import sqlite3
import json
import xml.etree.ElementTree as ET
from datetime import datetime

class Crawler:
    def __init__(self, db_path="collections.db"):
        # Rate limit
        self.rate_limit = 80 # requests per second
        self.met_cookies = open("cookie.txt").read()

        # Initialize database
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS artworks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                museum TEXT,
                artwork_id TEXT,
                data TEXT,
                updated DATETIME,
                UNIQUE(museum, artwork_id)
            )
        ''')
        
    async def crawl(self):
        headers = {"Cookie": self.met_cookies}
        async with aiohttp.ClientSession(headers=headers) as session:
            # Create tasks for both museums
            tasks = [
                self.crawl_met(session),
                self.crawl_louvre(session)
            ]
            await asyncio.gather(*tasks)

        await self.conn.close()

    async def crawl_met(self, session):
        print("Starting Met crawl...")
        # Get artwork IDs
        async with session.get("https://collectionapi.metmuseum.org/public/collection/v1/objects") as response:
            ids = (await response.json())["objectIDs"]

        # Process artworks with concurrency limit
        sem = asyncio.Semaphore(50)
        async def process_artwork(id):
            async with sem:
                await asyncio.sleep(1 / self.rate_limit)
                url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.save_artwork("met", str(id), data)
                except Exception as e:
                    print(f"Error processing Met artwork {id}: {e}")

        await asyncio.gather(*[process_artwork(id) for id in ids])

    async def crawl_louvre(self, session):
        print("Starting Louvre crawl...")
        # Get artwork IDs from sitemap
        async with session.get("https://collections.louvre.fr/sitemap.xml") as response:
            root = ET.fromstring(await response.text())
            
        ids = []
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        for sitemap in root.findall('.//ns:loc', namespace):
            sitemap_url = sitemap.text
            async with session.get(sitemap_url) as response:
                sitemap_root = ET.fromstring(await response.text())
                for url in sitemap_root.findall('.//ns:loc', namespace):
                    if '/ark:/53355/' in url.text:
                        ids.append(url.text.split('/ark:/53355/')[-1].replace('.json', ''))

        # Process artworks with concurrency limit
        sem = asyncio.Semaphore(50)
        async def process_artwork(id):
            async with sem:
                await asyncio.sleep(1 / self.rate_limit)
                url = f"https://collections.louvre.fr/ark:/53355/{id}.json"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.save_artwork("louvre", id, data)
                except Exception as e:
                    print(f"Error processing Louvre artwork {id}: {e}")

        await asyncio.gather(*[process_artwork(id) for id in ids])

    def save_artwork(self, museum, artwork_id, data):
        self.cursor.execute(
            'INSERT INTO artworks (museum, artwork_id, data, updated) VALUES (?, ?, ?, ?)',
            (museum, artwork_id, json.dumps(data), datetime.now().isoformat())
        )
        self.conn.commit()

async def main():
    crawler = Crawler()
    await crawler.crawl()

if __name__ == "__main__":
    asyncio.run(main())