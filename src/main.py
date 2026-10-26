from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from src.core.scraper import VoirAnimeScraper

scraper = VoirAnimeScraper(data_dir="data")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scraper.init_client()
    yield
    await scraper.close_client()

app = FastAPI(
    title="VoirAnime API",
    description="API ultra-rapide et standardisée pour rechercher, lister et résoudre les animes et épisodes depuis VoirAnime, compatible 1:1 avec AnimeSamaApi et YoitsuWrap.",
    version="2.0.0",
    lifespan=lifespan
)

class CatalogUpdateResponse(BaseModel):
    message: str
    status: str

# =====================================================================
#  ROUTES COMPATIBLES AVEC ANIMESAMAAPI & YOITSUWRAP (/api/...)
# =====================================================================

@app.get("/", tags=["General"])
async def root(q: Optional[str] = None):
    """
    Route racine : renvoie les infos API, ou si paramètre 'q' est présent,
    le format d'accueil attendu par les wrappers.
    """
    if q:
        return {
            "Bonjours": "Je suis une api...",
            "Valeur q ": q,
            "Cardinal value": "VoirAnime.Cardinal"
        }
    return {
        "message": "Bienvenue sur l'API VoirAnime",
        "docs": "/docs",
        "status": "Online",
        "documentation": "Compatible 1:1 avec AnimeSamaApi pour YoitsuWrap."
    }

@app.get("/config", tags=["General"])
async def get_config():
    """
    Retourne la configuration IP / PORT de l'API (identique à AnimeSamaApi).
    """
    return {
        "IP": "127.0.0.1",
        "PORT": 8000
    }

@app.get("/status", tags=["General"])
@app.get("/api/status", tags=["General"])
async def get_status():
    """
    Vérification de l'état en ligne de l'API (utilisé par YoitsuWrap Config.py).
    """
    return {"API Status": "Online"}

@app.get("/api/getAnimeSamaURL", tags=["AnimeSamaApi Compatible"])
@app.get("/api/getVoirAnimeURL", tags=["AnimeSamaApi Compatible"])
async def get_site_url():
    """
    Retourne l'URL de base du site source.
    """
    return {"url": scraper.BASE_URL}

@app.get("/api/getAllAnime", tags=["AnimeSamaApi Compatible"])
async def get_all_anime(background_tasks: BackgroundTasks, r: Optional[str] = None, reset: Optional[str] = None):
    """
    Retourne la liste complète du catalogue, ou déclenche une actualisation
    complète en arrière-plan si reset='True' ou r='True'.
    """
    is_reset = str(r or reset or "").strip().lower() in ["true", "1", "yes"]
    if is_reset:
        background_tasks.add_task(scraper.update_catalog, 1000)
        return "Recuperation en cours en arriere-plan"
    return scraper.load_base_anime_data()

@app.get("/api/loadBaseAnimeData", tags=["AnimeSamaApi Compatible"])
async def load_base_anime_data():
    """
    Charge les données brutes des animes enregistrés (titre, lien, cover).
    """
    return scraper.load_base_anime_data()

@app.get("/api/getSerchAnime", tags=["AnimeSamaApi Compatible"])
@app.get("/api/getSearchAnime", tags=["AnimeSamaApi Compatible"])
async def serch_anime(
    q: str = Query(..., description="Nom de l'anime recherché (ex: Frieren)"),
    l: int = Query(5, description="Limite du nombre de résultats")
):
    """
    Recherche floue (fuzzy search) avec scoring intelligent et anti-doublons.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Paramètre 'q' manquant")
    return scraper.serch_anime(q.strip(), limit=l)

@app.get("/api/getInfoAnime", tags=["AnimeSamaApi Compatible"])
async def get_info_anime(q: str = Query(..., description="Nom de l'anime (ex: Frieren)")):
    """
    Retourne la liste des saisons disponibles pour un anime sous le format exact
    attendu par YoitsuWrap et Cardinal :
    [
        {
            "base_url": "...",
            "title": "Sousou no Frieren",
            "cover": "...",
            "synopsis": "...",
            "Saison": "Saison 1",
            "url": "..."
        },
        ...
    ]
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Paramètre 'q' manquant")
    res = await scraper.get_info_anime(q.strip())
    if not res:
        raise HTTPException(status_code=404, detail="Aucun anime trouvé pour cette requête.")
    return res

@app.get("/api/getSpecificAnime", tags=["AnimeSamaApi Compatible"])
async def get_specific_anime(
    q: str = Query(..., description="Nom de l'anime (ex: Frieren)"),
    s: Optional[str] = Query("saison1", description="Saison souhaitée (ex: saison1, saison 2, film)"),
    v: Optional[str] = Query("vostfr", description="Version linguistique (vostfr ou vf)")
):
    """
    Retourne l'objet de saison ciblé avec l'URL adaptée à la version (VOSTFR / VF) et le synopsis :
    {
        "base_url": "...",
        "title": "Sousou no Frieren",
        "cover": "...",
        "synopsis": "...",
        "Saison": "Saison 1",
        "url": "..."
    }
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Paramètre 'q' manquant")
    res = await scraper.get_specific_anime(q.strip(), saison=s, version=v)
    if not res:
        raise HTTPException(status_code=404, detail="Saison ou anime introuvable.")
    return res

@app.get("/api/getAnimeLink", tags=["AnimeSamaApi Compatible"])
async def get_anime_link(
    n: str = Query(..., description="Nom de l'anime"),
    s: Optional[str] = Query("saison1", description="Saison ciblée (défaut: saison1)"),
    v: Optional[str] = Query("vostfr", description="Version (vostfr ou vf)")
):
    """
    Résout et retourne la liste ordonnée des épisodes prêts à être lus ou téléchargés par yt-dlp :
    [
        {"episode": 1, "url": "https://..."},
        {"episode": 2, "url": "https://..."}
    ]
    """
    if not n.strip():
        raise HTTPException(status_code=400, detail="Paramètre 'n' manquant")
    links = await scraper.get_anime_link(n.strip(), saison=s, version=v)
    return links

@app.get("/api/getScanHashmap", tags=["AnimeSamaApi Compatible"])
async def get_scan_hashmap(n: str = Query(..., description="Nom du manga")):
    """
    Renvoie une structure sécurisée pour les scans (non applicables à VoirAnime).
    """
    if not n.strip():
        raise HTTPException(status_code=400, detail="Paramètre 'n' manquant")
    return scraper.get_scan_hashmap(n.strip())

@app.get("/api/getScanLink", tags=["AnimeSamaApi Compatible"])
async def get_scan_link(
    n: str = Query(..., description="Nom du manga"),
    c: Optional[str] = Query("all", description="Numéro de chapitre ou 'all'")
):
    """
    Renvoie une structure sécurisée pour les scans (non applicables à VoirAnime).
    """
    if not n.strip():
        raise HTTPException(status_code=400, detail="Paramètre 'n' manquant")
    return scraper.get_scan_link(n.strip(), chap=c)


# =====================================================================
#  ROUTES HISTORIQUES VOIRANIME (POUR RÉTRO-COMPATIBILITÉ)
# =====================================================================

@app.get("/catalog", tags=["Catalog Legacy"])
async def get_catalog():
    """
    Retourne le catalogue complet (nom: url).
    """
    catalog = scraper.load_catalog()
    return {"total": len(catalog), "catalog": catalog}

@app.get("/catalog/status", tags=["Catalog Legacy"])
async def get_catalog_status():
    """
    Permet de suivre l'état de la mise à jour du catalogue en arrière-plan.
    """
    return scraper.update_status

@app.get("/catalog/update", response_model=CatalogUpdateResponse, tags=["Catalog Legacy"])
@app.post("/catalog/update", response_model=CatalogUpdateResponse, tags=["Catalog Legacy"])
async def trigger_catalog_update(background_tasks: BackgroundTasks, max_pages: int = 1000):
    """
    Lance une mise à jour complète du catalogue en tâche de fond.
    """
    background_tasks.add_task(scraper.update_catalog, max_pages)
    return {
        "message": f"Mise à jour démarrée en arrière-plan (max_pages={max_pages}).",
        "status": "processing"
    }

@app.get("/anime/search", tags=["Anime Resolver Legacy"])
async def search_anime(query: str = Query(..., description="Nom partiel ou complet de l'anime (ex: 'Frieren')")):
    """
    Recherche un anime dans le catalogue local.
    """
    results = scraper.serch_anime(query, limit=10)
    if not results:
        raise HTTPException(
            status_code=404, 
            detail="Aucun anime trouvé. Vérifiez l'orthographe ou mettez à jour le catalogue via /catalog/update."
        )
    legacy_results = [{"name": r["title"], "url": r["lien"], **r} for r in results]
    return {"total_results": len(legacy_results), "results": legacy_results}

@app.get("/episodes", tags=["Episodes & Video Links Legacy"])
async def get_episodes(anime_url: str = Query(..., description="L'URL complète de l'anime")):
    """
    Récupère la liste de tous les épisodes associés à une URL d'anime.
    """
    episodes = await scraper.fetch_episodes(anime_url)
    if not episodes:
        raise HTTPException(status_code=404, detail="Aucun épisode trouvé ou URL invalide.")
    return {"total_episodes": len(episodes), "episodes": episodes}

@app.get("/download/all", tags=["Episodes & Video Links Legacy"])
async def get_all_download_links(
    anime_name: str = Query(..., description="Nom de l'anime (ex: 07-ghost)")
):
    """
    Récupère tous les épisodes d'un anime et résout les flux vidéo directement.
    """
    results = scraper.serch_anime(anime_name, limit=5)
    if not results:
        raise HTTPException(status_code=404, detail="Anime non trouvé dans la base de données.")
        
    exact_match = results[0]
    episodes_with_links = await scraper.fetch_all_episodes_with_links(exact_match["lien"])
    if not episodes_with_links:
        raise HTTPException(status_code=404, detail="Aucun épisode ou lien vidéo trouvé.")
        
    return {
        "anime": exact_match["title"],
        "total_episodes": len(episodes_with_links),
        "episodes": episodes_with_links
    }

@app.get("/resolve", tags=["Episodes & Video Links Legacy"])
async def resolve_embed_link(
    embed_url: str = Query(..., description="L'URL de l'embed lecteur vidéo")
):
    """
    Résout une URL d'embed pour extraire directement le lien de flux vidéo réels (.m3u8 / .mp4).
    """
    result = await scraper.resolver.resolve(embed_url)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Échec de la résolution du lien."))
    return result

@app.get("/download/single", tags=["Episodes & Video Links Legacy"])
async def get_single_download_link(
    anime_name: str = Query(..., description="Nom de l'anime"),
    episode_num: str = Query(..., description="Numéro ou identifiant de l'épisode (ex: 01)")
):
    """
    Récupère le lien vidéo d'un épisode spécifique avec la résolution automatique du flux direct.
    """
    results = scraper.serch_anime(anime_name, limit=5)
    if not results:
        raise HTTPException(status_code=404, detail="Anime non trouvé.")
        
    exact_match = results[0]
    episodes = await scraper.fetch_episodes(exact_match["lien"])
    if not episodes:
        raise HTTPException(status_code=404, detail="Aucun épisode trouvé.")
        
    target_url = None
    target_ep_title = None
    for ep in episodes:
        if episode_num in ep["title"]:
            target_url = ep["url"]
            target_ep_title = ep["title"]
            break
            
    if not target_url:
        raise HTTPException(status_code=404, detail=f"Épisode '{episode_num}' introuvable.")
        
    resolved_info = await scraper.fetch_download_link(target_url, resolve_stream=True)
    if not resolved_info:
        raise HTTPException(status_code=404, detail="Aucun lecteur vidéo trouvé pour cet épisode.")
        
    return {
        "anime": exact_match["title"],
        "episode_title": target_ep_title,
        "iframe_url": resolved_info.get("iframe_url") if isinstance(resolved_info, dict) else resolved_info,
        "video_url": resolved_info.get("stream_url") or resolved_info.get("iframe_url"),
        "stream_url": resolved_info.get("stream_url") if isinstance(resolved_info, dict) else None,
        "stream_type": resolved_info.get("stream_type") if isinstance(resolved_info, dict) else None,
        "host": resolved_info.get("host") if isinstance(resolved_info, dict) else None
    }

@app.get("/api/setCookie", tags=["Cloudflare Bypass"])
@app.post("/api/setCookie", tags=["Cloudflare Bypass"])
async def set_cookie_endpoint(cookie: Optional[str] = Query(None, description="Valeur du cookie cf_clearance ou chaîne brute")):
    """
    Configure dynamiquement les cookies Cloudflare (notamment cf_clearance) pour contourner le challenge Turnstile.
    """
    if not cookie:
        raise HTTPException(status_code=400, detail="Paramètre 'cookie' manquant.")
    scraper.set_cookies(cookie)
    return {
        "status": "success",
        "message": "Cookies mis a jour avec succes.",
        "cookies": list(scraper.cookies.keys())
    }

@app.get("/api/getCookieStatus", tags=["Cloudflare Bypass"])
async def get_cookie_status():
    """
    Vérifie si un cookie Cloudflare (ex: cf_clearance) est configuré dans l'API.
    """
    return {
        "has_cf_clearance": "cf_clearance" in scraper.cookies,
        "configured_cookies": list(scraper.cookies.keys())
    }

