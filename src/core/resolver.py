import re
import httpx

class StreamResolver:
    def __init__(self, headers=None):
        self.headers = headers or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def resolve(self, embed_url: str, client: httpx.AsyncClient = None) -> dict:
        if not embed_url:
            return {"status": "error", "message": "URL d'embed invalide ou vide."}

        close_client = False
        if client is None or client.is_closed:
            client = httpx.AsyncClient(headers=self.headers, timeout=10.0, follow_redirects=True)
            close_client = True

        try:
            resp = await client.get(embed_url)
            if resp.status_code != 200:
                return {
                    "status": "error",
                    "message": f"Impossible d'accéder à l'embed (HTTP {resp.status_code})",
                    "embed_url": embed_url
                }

            html = resp.text

            # 1. Vidmoly
            if "vidmoly" in embed_url or "vmeas.cloud" in html or "vmnow.online" in html:
                m3u8_match = re.search(r'file\s*:\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html)
                if not m3u8_match:
                    m3u8_match = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
                if m3u8_match:
                    return {
                        "status": "success",
                        "host": "vidmoly",
                        "stream_url": m3u8_match.group(1),
                        "type": "hls",
                        "embed_url": embed_url
                    }

            # 2. Sibnet
            if "sibnet" in embed_url or "video.sibnet.ru" in html:
                mp4_match = re.search(r'["\'](/v/[^"\']+\.mp4)["\']', html)
                if mp4_match:
                    return {
                        "status": "success",
                        "host": "sibnet",
                        "stream_url": f"https://video.sibnet.ru{mp4_match.group(1)}",
                        "type": "mp4",
                        "headers": {"Referer": embed_url},
                        "embed_url": embed_url
                    }

            # 3. Sendvid
            if "sendvid" in embed_url:
                mp4_match = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
                if mp4_match:
                    return {
                        "status": "success",
                        "host": "sendvid",
                        "stream_url": mp4_match.group(1),
                        "type": "mp4",
                        "embed_url": embed_url
                    }

            # 4. Vidoza
            if "vidoza" in embed_url:
                mp4_match = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
                if mp4_match:
                    return {
                        "status": "success",
                        "host": "vidoza",
                        "stream_url": mp4_match.group(1),
                        "type": "mp4",
                        "embed_url": embed_url
                    }

            # Generic m3u8 fallback
            m3u8_generic = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
            if m3u8_generic:
                return {
                    "status": "success",
                    "host": "generic",
                    "stream_url": m3u8_generic.group(1),
                    "type": "hls",
                    "embed_url": embed_url
                }

            # Generic mp4 fallback
            mp4_generic = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
            if mp4_generic:
                return {
                    "status": "success",
                    "host": "generic",
                    "stream_url": mp4_generic.group(1),
                    "type": "mp4",
                    "embed_url": embed_url
                }

            return {
                "status": "error",
                "message": "Aucun flux direct (.m3u8/.mp4) trouvé dans la page d'embed.",
                "embed_url": embed_url
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "embed_url": embed_url}
        finally:
            if close_client:
                await client.aclose()
