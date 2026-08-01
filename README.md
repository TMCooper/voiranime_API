# VoirAnime API

Une API ultra-rapide et 100% asynchrone pour extraire le catalogue, chercher des animes, et récupérer les liens vidéo (iframes) directement depuis VoirAnime. 

L'architecture est entièrement légère, s'appuyant sur des requêtes HTTP/2 asynchrones par lots (`httpx` / `curl_cffi`) et le parseur haute performance `lxml`, éliminant totalement le besoin de navigateurs lourds (SeleniumBase / Playwright).

## Structure du Projet

```text
voiranime_API/
├── data/
│   └── catalog.json         # Base de données locale de tous les animes
├── src/
│   ├── main.py              # Application FastAPI (les routes asynchrones)
│   └── core/
│       └── scraper.py       # Logique métier asynchrone (Classe VoirAnimeScraper)
├── venv/                    # Environnement virtuel Python
└── run_api.bat              # Script de lancement
```

## Lancement

Pour démarrer le serveur API, exécutez le script suivant à la racine du projet :
```bash
run_api.bat
```
L'API sera disponible sur : `http://127.0.0.1:8000`

> **Astuce** : Accédez à `http://127.0.0.1:8000/docs` pour une interface graphique interactive (Swagger UI) permettant de tester toutes les routes en direct. La mise à jour complète du catalogue prend désormais moins de 20 secondes pour plus de 330 pages !

---

## Documentation des Routes

### 1. Gestion du Catalogue

#### `GET /catalog`
- **Description** : Renvoie le contenu entier du fichier `catalog.json` stocké en mémoire RAM. Ultra-rapide et instantané.
- **Retour** : 
  ```json
  {
    "total": 42,
    "catalog": {
      "Frieren": "https://voir-anime.to/anime/frieren-beyond-journey-end/",
      "...": "..."
    }
  }
  ```

#### `POST /catalog/update` ou `GET /catalog/update`
- **Description** : Lance la mise à jour complète du catalogue en arrière-plan par lots asynchrones (10 pages simultanées). Scanne l'intégralité du site (~330+ pages, ~2000+ animes) en moins de 20 secondes sans aucun navigateur Chrome.
- **Paramètres** : `max_pages` (optionnel, défaut: 1000)
- **Retour** : Message de confirmation du lancement de la tâche.

---

### 2. Résolution & Épisodes

#### `GET /anime/search`
- **Description** : Recherche un anime dans votre catalogue local par son nom (supporte les recherches partielles). Utile pour différencier les différentes saisons (ex: Saison 2, VF, VOSTFR).
- **Paramètre** : `query` (ex: `Frieren`)
- **Exemple de lien complet** : `http://127.0.0.1:8000/anime/search?query=Frieren`
- **Retour** :
  ```json
  {
    "total_results": 2,
    "results": [
      {
        "name": "Frieren",
        "url": "https://voir-anime.to/anime/frieren-beyond-journey-end/"
      },
      {
        "name": "Frieren (VF)",
        "url": "https://voir-anime.to/anime/frieren-beyond-journey-end-vf/"
      }
    ]
  }
  ```

#### `GET /episodes`
- **Description** : À partir d'une URL d'anime exacte, récupère la liste de tous ses épisodes et leurs URL correspondantes.
- **Paramètre** : `anime_url` (ex: `https://voir-anime.to/anime/sousou-no-frieren/`)
- **Retour** :
  ```json
  {
    "total_episodes": 25,
    "episodes": [
      {
        "title": "Frieren - 01 VOSTFR - 01",
        "url": "https://voir-anime.to/anime/frieren-beyond-journey-end/frieren-01-vostfr-01/"
      }
    ]
  }
  ```

---

### 3. Les Surcouches Vidéo & Resolver de Flux

Ces routes sont conçues pour être exploitées par des lecteurs vidéo et interfaces graphiques. Elles extraient ET résolvent automatiquement les lecteurs (Vidmoly, Sibnet, Sendvid...) en liens vidéo directs prêts à l'emploi (`.m3u8` HLS / `.mp4`).

#### `GET /resolve` (Nouveau)
- **Description** : Prend une URL d'embed lecteur (ex: `https://vidmoly.biz/embed-ce2b8bs6lycx.html` ou Sibnet/Sendvid) et extrait le lien vidéo direct prêt à être lu dans un lecteur vidéo (VLC, HTML5 `<video>`, etc.).
- **Paramètre** : `embed_url`
- **Exemple** : `http://127.0.0.1:8000/resolve?embed_url=https://vidmoly.biz/embed-ce2b8bs6lycx.html`
- **Retour** :
  ```json
  {
    "status": "success",
    "host": "vidmoly",
    "stream_url": "https://box-1096-q.vmeas.cloud/hls/.../master.m3u8",
    "type": "hls",
    "embed_url": "https://vidmoly.biz/embed-ce2b8bs6lycx.html"
  }
  ```

---

#### `GET /download/all` (Recommandé)
- **Description** : Récupère tous les épisodes d'un anime et résout de manière 100% asynchrone tous les flux vidéo directs prêts à l'emploi.
- **Paramètre** : `anime_name` (ex: `Frieren`)
- **Exemple** : `http://127.0.0.1:8000/download/all?anime_name=Frieren`
- **Retour** :
  ```json
  {
    "anime": "Frieren",
    "total_episodes": 25,
    "episodes": [
      {
        "title": "Frieren - 01 VOSTFR - 01",
        "url": "https://voir-anime.to/anime/frieren-beyond-journey-end/frieren-01-vostfr-01/",
        "iframe_url": "https://vidmoly.biz/embed-0v50iamolxhq.html",
        "stream_url": "https://gate-2-an-p.vmnow.online/hls2/.../master.m3u8",
        "stream_type": "hls",
        "host": "vidmoly",
        "video_url": "https://gate-2-an-p.vmnow.online/hls2/.../master.m3u8"
      }
    ]
  }
  ```

---

#### `GET /download/single`
- **Description** : Récupère et résout le lien vidéo direct d'un épisode spécifique.
- **Paramètres** : 
  - `anime_name` (ex: `Frieren`)
  - `episode_num` (ex: `01`)
- **Retour** :
  ```json
  {
    "anime": "Frieren",
    "episode_title": "Frieren - 01 VOSTFR - 01",
    "iframe_url": "https://vidmoly.biz/embed-0v50iamolxhq.html",
    "stream_url": "https://gate-2-an-p.vmnow.online/hls2/.../master.m3u8",
    "stream_type": "hls",
    "host": "vidmoly",
    "video_url": "https://gate-2-an-p.vmnow.online/hls2/.../master.m3u8"
  }
  ```
