import json
import os
import asyncio
import httpx
from bs4 import BeautifulSoup
from src.core.resolver import StreamResolver

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
        self.catalog = self.load_catalog()
        self.client = None
        self.resolver = StreamResolver(headers=self.headers)

    def init_client(self):
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                headers=self.headers,
                timeout=10.0,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=30, max_keepalive_connections=15)
            )

    async def close_client(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            self.client = None

    def _get_active_client(self, provided_client=None):
        if provided_client is not None:
            return provided_client, False
        if self.client is not None and not self.client.is_closed:
            return self.client, False
        return httpx.AsyncClient(
            headers=self.headers,
            timeout=10.0,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=15)
        ), True

    def load_catalog(self):
        if os.path.exists(self.catalog_file):
            try:
                with open(self.catalog_file, "r", encoding="utf-8") as f:
                    self.catalog = json.load(f)
                    return self.catalog
            except Exception as e:
                print(f"Error loading catalog file: {e}")
        self.catalog = {}
        return {}

    def save_catalog(self, catalog=None):
        if catalog is not None:
            self.catalog = catalog
        with open(self.catalog_file, "w", encoding="utf-8") as f:
            json.dump(self.catalog, f, indent=4, ensure_ascii=False)

    def resolve_anime(self, anime_name):
        if not self.catalog:
            self.load_catalog()
            
        search_words = anime_name.lower().strip().split()
        matches = []
        for name, link in self.catalog.items():
            name_lower = name.lower()
            if all(word in name_lower for word in search_words):
                matches.append({"name": name, "url": link})
        return matches

    async def _fetch_catalog_page(self, client, page):
        url = f"https://voir-anime.to/liste-danimes/page/{page}/" if page > 1 else "https://voir-anime.to/liste-danimes/"
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return page, {}
                
            soup = BeautifulSoup(resp.text, 'lxml')
            items = soup.find_all("div", class_="item-summary")
            if not items:
                items = soup.find_all("h3", class_="h4")
                
            page_animes = {}
            for item in items:
                a_tag = item.find("a")
                if a_tag:
                    name = a_tag.text.strip()
                    link = a_tag.get("href")
                    if name and link:
                        page_animes[name] = link
            return page, page_animes
        except Exception as e:
            print(f"Error scraping catalog page {page}: {e}")
            return page, {}

    async def update_catalog(self, max_pages=1000, client=None, batch_size=10):
        self.update_status["is_updating"] = True
        self.update_status["current_page"] = 0
        
        http_client, should_close = self._get_active_client(client)
        catalog = self.catalog.copy()
        self.update_status["total_animes"] = len(catalog)
        
        try:
            current_page = 1
            while current_page <= max_pages:
                pages_to_fetch = list(range(current_page, min(current_page + batch_size, max_pages + 1)))
                tasks = [self._fetch_catalog_page(http_client, p) for p in pages_to_fetch]
                results = await asyncio.gather(*tasks)
                
                stop_update = False
                for page_num, page_animes in sorted(results, key=lambda x: x[0]):
                    if not page_animes:
                        stop_update = True
                        break
                        
                    catalog.update(page_animes)
                    self.update_status["current_page"] = page_num
                    self.update_status["total_animes"] = len(catalog)
                    
                self.save_catalog(catalog)
                print(f"[Mise à jour] Lot terminé jusqu'à la page {self.update_status['current_page']}. Total animes: {len(catalog)}")
                
                if stop_update:
                    break
                    
                current_page += batch_size
                
        except Exception as e:
            print(f"Error updating catalog: {e}")
        finally:
            self.update_status["is_updating"] = False
            if should_close:
                await http_client.aclose()
                
        self.save_catalog(catalog)
        return catalog

    async def fetch_episodes(self, anime_url, client=None):
        http_client, should_close = self._get_active_client(client)
        try:
            resp = await http_client.get(anime_url)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, 'lxml')
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
        except Exception as e:
            print(f"Error fetching episodes from {anime_url}: {e}")
            return []
        finally:
            if should_close:
                await http_client.aclose()

    async def fetch_download_link(self, episode_url, client=None, resolve_stream=True):
        http_client, should_close = self._get_active_client(client)
        try:
            resp = await http_client.get(episode_url)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, 'lxml')
            iframes = soup.find_all("iframe")
            iframe_url = None
            for iframe in iframes:
                src = iframe.get("src")
                if src and "voiranime" not in src:
                    iframe_url = src
                    break
                    
            if not iframe_url:
                return None

            if resolve_stream:
                resolved = await self.resolver.resolve(iframe_url, client=http_client)
                return {
                    "iframe_url": iframe_url,
                    "stream_url": resolved.get("stream_url"),
                    "stream_type": resolved.get("type"),
                    "host": resolved.get("host")
                }
            return iframe_url
        except Exception as e:
            print(f"Error fetching download link from {episode_url}: {e}")
            return None
        finally:
            if should_close:
                await http_client.aclose()

    async def _fetch_single_iframe_async(self, http_client, episode):
        try:
            resolved_data = await self.fetch_download_link(episode["url"], client=http_client, resolve_stream=True)
            if isinstance(resolved_data, dict):
                return {
                    **episode,
                    "iframe_url": resolved_data.get("iframe_url"),
                    "video_url": resolved_data.get("stream_url") or resolved_data.get("iframe_url"),
                    "stream_url": resolved_data.get("stream_url"),
                    "stream_type": resolved_data.get("stream_type"),
                    "host": resolved_data.get("host")
                }
            return {
                **episode,
                "iframe_url": resolved_data,
                "video_url": resolved_data,
                "stream_url": None,
                "stream_type": None,
                "host": None
            }
        except Exception:
            return {
                **episode,
                "iframe_url": None,
                "video_url": None,
                "stream_url": None,
                "stream_type": None,
                "host": None
            }

    async def fetch_all_episodes_with_links(self, anime_url, client=None):
        http_client, should_close = self._get_active_client(client)
        try:
            episodes = await self.fetch_episodes(anime_url, client=http_client)
            if not episodes:
                return []
            
            tasks = [self._fetch_single_iframe_async(http_client, ep) for ep in episodes]
            results = await asyncio.gather(*tasks)
            return list(results)
        finally:
            if should_close:
                await http_client.aclose()


