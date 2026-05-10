import json
import os
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
from seleniumbase import Driver

class VoirAnimeScraper:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.catalog_file = os.path.join(self.data_dir, "catalog.json")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        self.update_status = {
            "is_updating": False,
            "current_page": 0,
            "total_animes": 0
        }

    def load_catalog(self):
        if os.path.exists(self.catalog_file):
            with open(self.catalog_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_catalog(self, catalog):
        with open(self.catalog_file, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=4, ensure_ascii=False)

    def resolve_anime(self, anime_name):
        catalog = self.load_catalog()
        search_words = anime_name.lower().strip().split()
        
        matches = []
        for name, link in catalog.items():
            name_lower = name.lower()
            # On vérifie que TOUS les mots de la recherche sont dans le nom de l'anime
            if all(word in name_lower for word in search_words):
                matches.append({"name": name, "url": link})
        return matches

    def update_catalog(self, max_pages=1000):
        self.update_status["is_updating"] = True
        self.update_status["current_page"] = 0
        
        driver = None
        catalog = self.load_catalog()
        self.update_status["total_animes"] = len(catalog)
        
        try:
            driver = Driver(browser="chrome", uc=True, headless2=True)
            page = 1
            while page <= max_pages:
                url = f"https://voir-anime.to/liste-danimes/page/{page}/" if page > 1 else "https://voir-anime.to/liste-danimes/"
                driver.get(url)
                
                # Attente pour s'assurer que Cloudflare est passé
                import time
                for _ in range(3):
                    title = driver.title
                    if title and "Just a moment" not in title and "Cloudflare" not in title:
                        break
                    time.sleep(3)
                    
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                
                items = soup.find_all("div", class_="item-summary")
                if not items:
                    items = soup.find_all("h3", class_="h4")
                    
                if not items:
                    break
                    
                added_on_page = 0
                for item in items:
                    a_tag = item.find("a")
                    if a_tag:
                        name = a_tag.text.strip()
                        link = a_tag.get("href")
                        if name and link:
                            catalog[name] = link
                            added_on_page += 1
                            
                if added_on_page == 0:
                    break
                
                page += 1
                
                # Sauvegarde incrémentale toutes les pages pour que l'utilisateur voie la progression
                self.save_catalog(catalog)
                self.update_status["current_page"] = page - 1
                self.update_status["total_animes"] = len(catalog)
                print(f"[Mise à jour] Page {page-1} scannée avec succès. Animes totaux: {len(catalog)}")
                
        except Exception as e:
            print(f"Error updating catalog: {e}")
        finally:
            self.update_status["is_updating"] = False
            if driver:
                driver.quit()
            
        self.save_catalog(catalog)
        return catalog

    def fetch_episodes(self, anime_url):
        try:
            resp = requests.get(anime_url, headers=self.headers, timeout=10)
            resp.raise_for_status()
        except requests.RequestException:
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        episodes = []
        
        chapter_list = soup.find_all("li", class_="wp-manga-chapter")
        for li in chapter_list:
            a_tag = li.find("a")
            if a_tag:
                ep_name = a_tag.text.strip()
                ep_link = a_tag.get("href")
                episodes.append({
                    "title": ep_name,
                    "url": ep_link
                })
                
        return episodes

    def fetch_download_link(self, episode_url):
        try:
            resp = requests.get(episode_url, headers=self.headers, timeout=10)
            resp.raise_for_status()
        except requests.RequestException:
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')
        iframes = soup.find_all("iframe")
        for iframe in iframes:
            src = iframe.get("src")
            if src and "voiranime" not in src:
                return src
        return None

    async def _fetch_single_iframe_async(self, session, episode):
        try:
            async with session.get(episode["url"], timeout=10) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                iframes = soup.find_all("iframe")
                for iframe in iframes:
                    src = iframe.get("src")
                    if src and "voiranime" not in src:
                        return {**episode, "video_url": src}
        except Exception:
            pass
        return {**episode, "video_url": None}

    async def _fetch_all_iframes_async(self, episodes):
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = [self._fetch_single_iframe_async(session, ep) for ep in episodes]
            return await asyncio.gather(*tasks)

    def fetch_all_episodes_with_links(self, anime_url):
        episodes = self.fetch_episodes(anime_url)
        if not episodes:
            return []
        
        return asyncio.run(self._fetch_all_iframes_async(episodes))
