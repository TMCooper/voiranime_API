from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from src.core.scraper import VoirAnimeScraper

app = FastAPI(
    title="VoirAnime API",
    description="API complète pour résoudre, lister et récupérer les liens vidéo depuis VoirAnime.",
    version="1.0.0"
)

scraper = VoirAnimeScraper(data_dir="data")

class CatalogUpdateResponse(BaseModel):
    message: str
    status: str

class AnimeResponse(BaseModel):
    name: str
    url: str

@app.get("/", tags=["General"])
def read_root():
    return {
        "message": "Bienvenue sur l'API VoirAnime",
        "docs": "/docs",
        "documentation": "Lisez le README.md pour le détail des routes."
    }

@app.get("/catalog", tags=["Catalog"])
def get_catalog():
    """
    Retourne le catalogue complet stocké localement.
    """
    catalog = scraper.load_catalog()
    return {"total": len(catalog), "catalog": catalog}

@app.get("/catalog/status", tags=["Catalog"])
def get_catalog_status():
    """
    Permet de suivre l'état de la mise à jour du catalogue en arrière-plan.
    Retourne la page actuelle, le nombre total d'animes et si la tâche est en cours.
    """
    return scraper.update_status

@app.get("/catalog/update", response_model=CatalogUpdateResponse, tags=["Catalog"])
@app.post("/catalog/update", response_model=CatalogUpdateResponse, tags=["Catalog"])
def trigger_catalog_update(background_tasks: BackgroundTasks, max_pages: int = 1000):
    """
    Lance une mise à jour complète du catalogue en tâche de fond via SeleniumBase.
    Parcourt toutes les pages disponibles.
    """
    background_tasks.add_task(scraper.update_catalog, max_pages)
    return {
        "message": f"Mise à jour démarrée en arrière-plan (max_pages={max_pages}).",
        "status": "processing"
    }

@app.get("/anime/search", tags=["Anime Resolver"])
def search_anime(query: str = Query(..., description="Nom partiel ou complet de l'anime (ex: 'Frieren')")):
    """
    Recherche un anime dans le catalogue local.
    Retourne TOUS les animes qui correspondent à la recherche (ex: Saisons, VF, VOSTFR).
    """
    results = scraper.resolve_anime(query)
    if not results:
        raise HTTPException(
            status_code=404, 
            detail="Aucun anime trouvé. Vérifiez l'orthographe ou mettez à jour le catalogue via /catalog/update."
        )
    return {"total_results": len(results), "results": results}

@app.get("/episodes", tags=["Episodes & Video Links"])
def get_episodes(anime_url: str = Query(..., description="L'URL complète de l'anime (obtenue via le resolver)")):
    """
    Récupère la liste de tous les épisodes associés à une URL d'anime.
    Ne résout pas les liens vidéo finaux (iframes).
    """
    episodes = scraper.fetch_episodes(anime_url)
    if not episodes:
        raise HTTPException(status_code=404, detail="Aucun épisode trouvé ou URL invalide.")
    return {"total_episodes": len(episodes), "episodes": episodes}

@app.get("/download/all", tags=["Episodes & Video Links"])
def get_all_download_links(
    anime_name: str = Query(..., description="Nom de l'anime (ex: 07-ghost)")
):
    """
    Récupère tous les épisodes d'un anime ET extrait la source de la vidéo (iframe)
    pour chacun d'eux, de manière asynchrone.
    """
    results = scraper.resolve_anime(anime_name)
    if not results:
        raise HTTPException(status_code=404, detail="Anime non trouvé dans la base de données.")
        
    # On prend le premier résultat correspondant exactement (ou le premier de la liste)
    # L'utilisateur est encouragé à utiliser le nom exact trouvé via /anime/search
    exact_match = next((a for a in results if a["name"].lower() == anime_name.lower()), results[0])
        
    episodes_with_links = scraper.fetch_all_episodes_with_links(exact_match["url"])
    if not episodes_with_links:
        raise HTTPException(status_code=404, detail="Aucun épisode ou lien vidéo trouvé.")
        
    return {
        "anime": exact_match["name"],
        "total_episodes": len(episodes_with_links),
        "episodes": episodes_with_links
    }

@app.get("/download/single", tags=["Episodes & Video Links"])
def get_single_download_link(
    anime_name: str = Query(..., description="Nom de l'anime"),
    episode_num: str = Query(..., description="Numéro ou identifiant de l'épisode (ex: 01)")
):
    """
    Récupère le lien vidéo d'un épisode spécifique.
    """
    results = scraper.resolve_anime(anime_name)
    if not results:
        raise HTTPException(status_code=404, detail="Anime non trouvé.")
        
    exact_match = next((a for a in results if a["name"].lower() == anime_name.lower()), results[0])
        
    episodes = scraper.fetch_episodes(exact_match["url"])
    if not episodes:
        raise HTTPException(status_code=404, detail="Aucun épisode trouvé.")
        
    target_url = None
    for ep in episodes:
        if episode_num in ep["title"]:
            target_url = ep["url"]
            break
            
    if not target_url:
        raise HTTPException(status_code=404, detail=f"Épisode '{episode_num}' introuvable.")
        
    video_link = scraper.fetch_download_link(target_url)
    if not video_link:
        raise HTTPException(status_code=404, detail="Aucun lecteur vidéo trouvé pour cet épisode.")
        
    return {
        "anime": exact_match["name"],
        "episode_title": ep["title"],
        "video_url": video_link
    }
