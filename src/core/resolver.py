import re
import httpx
from urllib.parse import urlparse

def _to_base_n(num, base):
    if num == 0:
        return '0'
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    res = ''
    while num > 0:
        res = chars[num % base] + res
        num //= base
    return res

def _decode_pack(p, a, c, k_str):
    k_list = k_str.split('|')
    for i in range(c - 1, -1, -1):
        if i < len(k_list) and k_list[i]:
            alias = _to_base_n(i, a)
            p = re.sub(r'\b' + re.escape(alias) + r'\b', k_list[i], p)
    return p

class StreamResolver:
    def __init__(self, headers=None):
        self.headers = headers or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def resolve(self, embed_url: str, client: httpx.AsyncClient = None) -> dict:
        if not embed_url or "sibnet" in embed_url.lower():
            return {"status": "error", "message": "URL d'embed invalide ou lecteur Sibnet non pris en charge."}

        # If it's already a direct video stream
        if re.search(r'\.m3u8(\?|$)', embed_url, re.IGNORECASE):
            return {"status": "success", "host": "direct", "stream_url": embed_url, "type": "hls", "embed_url": embed_url}
        if re.search(r'\.mp4(\?|$)', embed_url, re.IGNORECASE):
            return {"status": "success", "host": "direct", "stream_url": embed_url, "type": "mp4", "embed_url": embed_url}

        close_client = False
        if client is None or client.is_closed:
            client = httpx.AsyncClient(headers=self.headers, timeout=5.0, follow_redirects=True)
            close_client = True

        try:
            # Custom domain tweaks if needed (e.g. vidmoly)
            fetch_url = embed_url
            if "vidmoly.to" in fetch_url:
                fetch_url = fetch_url.replace("vidmoly.to", "vidmoly.net")

            resp = await client.get(fetch_url, headers={**self.headers, "Referer": fetch_url})
            if resp.status_code != 200:
                return {
                    "status": "error",
                    "message": f"Impossible d'accéder à l'embed (HTTP {resp.status_code})",
                    "embed_url": embed_url
                }

            html = resp.text

            # 1. Voembed (myTV)
            if "voembed" in fetch_url.lower():
                hls_match = re.search(r"['\"](?:hls|file)['\"]\s*:\s*['\"](https?://[^'\"]+\.m3u8[^'\"]*)['\"]", html)
                if not hls_match:
                    hls_match = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
                if hls_match:
                    return {
                        "status": "success",
                        "host": "voembed",
                        "stream_url": hls_match.group(1),
                        "type": "hls",
                        "embed_url": embed_url
                    }

            # 2. Vidmoly
            if any(h in fetch_url.lower() for h in ["vidmoly", "vmeas.cloud", "vmnow.online"]):
                redirect_match = re.search(r"window\.location\.replace\('([^']+)'\)", html)
                if redirect_match:
                    r2 = await client.get(redirect_match.group(1), headers={**self.headers, "Referer": fetch_url})
                    if r2.status_code == 200:
                        html = r2.text

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

            # 3. VOE (voe.sx)
            if "voe.sx" in fetch_url.lower() or "voe" in fetch_url.lower():
                hls_match = re.search(r"['\"]hls['\"]\s*:\s*['\"](https?://[^'\"]+\.m3u8[^'\"]*)['\"]", html)
                if not hls_match:
                    hls_match = re.search(r"['\"]file['\"]\s*:\s*['\"](https?://[^'\"]+\.m3u8[^'\"]*)['\"]", html)
                if not hls_match:
                    hls_match = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
                if hls_match:
                    return {
                        "status": "success",
                        "host": "voe",
                        "stream_url": hls_match.group(1),
                        "type": "hls",
                        "embed_url": embed_url
                    }
                # Check for redirect in VOE
                redir = re.search(r'window\.location\.href\s*=\s*[\'"]([^\'"]+)[\'"]', html)
                if redir:
                    r_voe = await client.get(redir.group(1), headers={**self.headers, "Referer": fetch_url})
                    if r_voe.status_code == 200:
                        m3u8_sub = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', r_voe.text)
                        if m3u8_sub:
                            return {
                                "status": "success",
                                "host": "voe",
                                "stream_url": m3u8_sub.group(1),
                                "type": "hls",
                                "embed_url": embed_url
                            }

            # 3. Streamtape
            if "streamtape" in fetch_url.lower():
                token_match = re.search(r"document\.getElementById\(['\"](?:robotlink|videolink)['\"]\)\.innerHTML\s*=\s*['\"]([^'\"]+)['\"];", html)
                if token_match:
                    video_part = token_match.group(1)
                    parsed = urlparse(fetch_url)
                    stream_url = f"{parsed.scheme}://{parsed.netloc}{video_part}" if video_part.startswith("/") else f"https:{video_part}" if video_part.startswith("//") else video_part
                    return {
                        "status": "success",
                        "host": "streamtape",
                        "stream_url": stream_url,
                        "type": "mp4",
                        "embed_url": embed_url
                    }

            # 4. Sendvid
            if "sendvid" in fetch_url.lower():
                mp4_match = re.search(r'<source\s+src="([^"]+\.mp4[^"]*)"', html)
                if not mp4_match:
                    mp4_match = re.search(r'property="og:video"\s+content="([^"]+)"', html)
                if not mp4_match:
                    mp4_match = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
                if mp4_match:
                    v_url = mp4_match.group(1)
                    if v_url.startswith("//"):
                        v_url = "https:" + v_url
                    return {
                        "status": "success",
                        "host": "sendvid",
                        "stream_url": v_url,
                        "type": "mp4",
                        "embed_url": embed_url
                    }

            # 6. SmoothPre / VidHide / StreamWish (PACK decode)
            if any(h in fetch_url.lower() for h in ["smoothpre", "vidhide", "streamwish"]):
                eval_match = re.search(r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)\)\)", html, re.DOTALL)
                if eval_match:
                    decoded = _decode_pack(eval_match.group(1), int(eval_match.group(2)), int(eval_match.group(3)), eval_match.group(4))
                    for key in ['hls4', 'hls3', 'hls2', 'source']:
                        m = re.search(f'"{key}"\\s*:\\s*"(.*?)"', decoded)
                        if m:
                            parsed = urlparse(fetch_url)
                            target_url = m.group(1).replace('\\', '')
                            if target_url.startswith("/"):
                                target_url = f"{parsed.scheme}://{parsed.netloc}{target_url}"
                            return {
                                "status": "success",
                                "host": "smoothpre",
                                "stream_url": target_url,
                                "type": "hls",
                                "embed_url": embed_url
                            }

            # 7. Vidoza
            if "vidoza" in fetch_url.lower():
                mp4_match = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
                if mp4_match:
                    return {
                        "status": "success",
                        "host": "vidoza",
                        "stream_url": mp4_match.group(1),
                        "type": "mp4",
                        "embed_url": embed_url
                    }

            # 8. Voembed / general m3u8 fallback
            m3u8_generic = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
            if m3u8_generic:
                return {
                    "status": "success",
                    "host": "generic",
                    "stream_url": m3u8_generic.group(1),
                    "type": "hls",
                    "embed_url": embed_url
                }

            # 9. General mp4 fallback
            mp4_generic = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
            if mp4_generic:
                return {
                    "status": "success",
                    "host": "generic",
                    "stream_url": mp4_generic.group(1),
                    "type": "mp4",
                    "embed_url": embed_url
                }

            # If no stream found, return the embed itself so callers (like yt-dlp) can try to handle it directly
            return {
                "status": "fallback",
                "message": "Aucun flux direct (.m3u8/.mp4) extrait, utilisation de l'embed.",
                "host": "embed",
                "stream_url": embed_url,
                "type": "embed",
                "embed_url": embed_url
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "embed_url": embed_url}
        finally:
            if close_client:
                await client.aclose()
