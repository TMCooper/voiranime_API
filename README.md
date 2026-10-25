# VoirAnime API

Une API ultra-rapide et 100% asynchrone pour extraire le catalogue, chercher des animes, et récupérer les liens vidéo directs depuis VoirAnime. 

Cette API est **100% compatible avec l'architecture de `AnimeSamaApi`** afin de permettre à des wrappers unifiés comme **`YoitsuWrap`** de fonctionner de manière interchangeable sur les deux plateformes sans modification de code.

## Structure du Projet

```text
voiranime_API/
├── data/
│   ├── catalog.json             # Base de données locale de tous les animes
│   └── covers.json              # Cache local des images de couverture
├── src/
│   ├── main.py                  # Application FastAPI (routes standardisées & legacy)
│   └── core/
│       ├── scraper.py           # Logique de scraping et de recherche floue (VoirAnimeScraper)
│       └── resolver.py          # Résolveur universel de lecteurs vidéo (StreamResolver)
├── tests/
│   └── test_animesama_compat.py # Suite de validation de compatibilité AnimeSama / YoitsuWrap
├── main.py                      # Point d'entrée pour lancer le serveur API
```

## Lancement

Pour démarrer le serveur API :
```bash
python main.py
```
L'API sera disponible sur : `http://127.0.0.1:8000`
La documentation interactive Swagger est accessible sur : `http://127.0.0.1:8000/docs`

---

## Routes Compatibles AnimeSamaApi & YoitsuWrap (`/api/...`)

Ces routes fournissent les mêmes formats, noms de paramètres et structures de données que l'API AnimeSama (`Cardinal` / `Yui`) :

| Méthode | Route | Description | Paramètres |
|---|---|---|---|
| `GET` | `/status` & `/api/status` | Statut en ligne de l'API | Aucun |
| `GET` | `/config` | Renvoie l'IP et le PORT de l'API | Aucun |
| `GET` | `/api/getAnimeSamaURL` / `getVoirAnimeURL` | Renvoie l'URL source de base | Aucun |
| `GET` | `/api/loadBaseAnimeData` | Charge la liste globale des animes (`title`, `link`, `cover`) | Aucun |
| `GET` | `/api/getAllAnime` | Charge la liste ou déclenche une màj si `r=True` | `r` (optionnel) |
| `GET` | `/api/getSerchAnime` | Recherche floue avec score (Fuzzy Matching RapidFuzz) | `q` (query), `l` (limit, défaut: 5) |
| `GET` | `/api/getInfoAnime` | Liste les saisons d'une œuvre pour initialiser `YoitsuWrap` | `q` (nom de l'anime) |
| `GET` | `/api/getSpecificAnime` | Récupère la saison et version linguistique voulue | `q` (nom), `s` (saison), `v` (vostfr/vf) |
| `GET` | `/api/getAnimeLink` | Retourne la liste des épisodes avec liens directs (`.m3u8`/`.mp4`) | `n` (nom), `s` (saison), `v` (vostfr/vf) |
| `GET` | `/api/getScanHashmap` | Sécurité pour YoitsuWrap (renvoie `{title, max_chapter: 0}`) | `n` (nom) |
| `GET` | `/api/getScanLink` | Sécurité pour YoitsuWrap (renvoie `{}`) | `n` (nom), `c` (chapitre) |

### Exemples d'utilisation

#### 1. Recherche : `/api/getSerchAnime?q=Frieren`
```json
[
  {
    "title": "Sousou no Frieren",
    "lien": "https://voir-anime.to/anime/sousou-no-frieren/",
    "cover": "https://voir-anime.to/wp-content/uploads/2023/09/thumb_650d6d2a0493b.jpg",
    "score": 100.0
  }
]
```

#### 2. Informations Saisons : `/api/getInfoAnime?q=Frieren`
```json
[
  {
    "base_url": "https://voir-anime.to/anime/sousou-no-frieren/",
    "title": "Sousou no Frieren",
    "cover": "https://voir-anime.to/wp-content/uploads/2023/09/thumb_650d6d2a0493b.jpg",
    "Saison": "Saison 1",
    "url": "https://voir-anime.to/anime/sousou-no-frieren/"
  },
  {
    "base_url": "https://voir-anime.to/anime/sousou-no-frieren/",
    "title": "Sousou no Frieren",
    "cover": "https://voir-anime.to/wp-content/uploads/2023/09/thumb_650d6d2a0493b.jpg",
    "Saison": "Saison 2",
    "url": "https://voir-anime.to/anime/sousou-no-frieren-2/"
  }
]
```

#### 3. Saison Spécifique & Synopsis : `/api/getSpecificAnime?q=Frieren&s=saison1&v=vostfr`
```json
{
  "base_url": "https://voir-anime.to/anime/sousou-no-frieren/",
  "title": "Sousou no Frieren",
  "cover": "https://voir-anime.to/wp-content/uploads/2023/09/thumb_650d6d2a0493b.jpg",
  "synopsis": "Que deviennent les héros une fois le mal vaincu ?\n\nLe jeune héros Himmel et ses compagnons...",
  "Saison": "Saison 1",
  "url": "https://voir-anime.to/anime/sousou-no-frieren/"
}
```

#### 4. Épisodes et Flux Vidéo : `/api/getAnimeLink?n=Frieren&s=saison1&v=vostfr`
```json
[
  {
    "episode": 1,
    "url": "https://delivery.voe.sx/hls/..."
  },
  {
    "episode": 2,
    "url": "https://delivery.voe.sx/hls/..."
  }
]
```

---

## Routes Historiques VoirAnime (Rétro-compatibilité)

Toutes les routes historiques ont été conservées :
- `GET /catalog` : Liste brute du catalogue `{ nom: url }`.
- `GET /catalog/status` : Statut en direct de la mise à jour asynchrone.
- `POST /catalog/update` : Déclenche la mise à jour asynchrone du catalogue.
- `GET /anime/search?query=...` : Recherche dans le catalogue.
- `GET /episodes?anime_url=...` : Liste des épisodes sans résolution vidéo.
- `GET /download/all?anime_name=...` : Récupère tous les épisodes avec les iframes.
- `GET /download/single?anime_name=...&episode_num=...` : Récupère un seul épisode résolu.
- `GET /resolve?embed_url=...` : Résout une URL d'embed (Vidmoly, VOE, Streamtape, Sendvid...).
