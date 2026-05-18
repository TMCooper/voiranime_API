# VoirAnime API

Une API légère et rapide pour extraire le catalogue, chercher des animes, et récupérer les liens vidéo (iframes) directement depuis VoirAnime. 

L'architecture sépare les tâches lourdes de contournement Cloudflare (réservées à la mise à jour du catalogue via SeleniumBase) de la navigation utilisateur (gérée via des requêtes asynchrones et ultra-rapides).

## Structure du Projet

```text
voiranime_API/
├── data/
│   └── catalog.json         # Base de données locale de tous les animes
├── src/
│   ├── main.py              # Application FastAPI (les routes)
│   └── core/
│       └── scraper.py       # Logique métier (Classe VoirAnimeScraper)
├── tests/                   # Zone contenant les scripts de test
├── venv/                    # Environnement virtuel Python
└── run_api.bat              # Script de lancement
```

## Lancement

Pour démarrer le serveur API, exécutez le script suivant à la racine du projet :
```bash
run_api.bat
```
L'API sera disponible sur : `http://127.0.0.1:8000`

> **Astuce** : Accédez à `http://127.0.0.1:8000/docs` pour une interface graphique interactive (Swagger UI) permettant de tester toutes les routes sans coder. aussi lors de la première recuperation des different animer prennez en compte que celle ci peut être un peut longue laissez donc le temps au code de faire son travaille

---

## Documentation des Routes

### 1. Gestion du Catalogue

#### `GET /catalog`
- **Description** : Renvoie le contenu entier du fichier `catalog.json` contenant la liste des animes et leurs URLs de base. Rapide et sans délai.
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

#### `POST /catalog/update`
- **Description** : Lance un script SeleniumBase en arrière-plan pour scanner la totalité des pages de VoirAnime (environ 330+ pages) et mettre à jour `catalog.json`.
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

### 3. Les Surcouches Vidéo

Ces routes sont conçues pour être exploitées par des interfaces graphiques tierces. Elles résolvent directement les lecteurs vidéo.

#### `GET /download/all` (Recommandé)
- **Description** : C'est la route la plus puissante. Vous lui passez le nom exact (ou partiel) d'un anime, et elle va chercher tous les épisodes, puis, **de manière asynchrone (en parallèle)**, va aller chercher le lecteur vidéo (iframe) pour chaque épisode en même temps. 
- **Paramètre** : `anime_name` (ex: `Frieren`)
- **Exemple de lien complet** : `http://127.0.0.1:8000/download/all?anime_name=Frieren`
- **Retour** :
  ```json
  {
    "anime": "Frieren",
    "total_episodes": 25,
    "episodes": [
      {
        "title": "Frieren - 01 VOSTFR - 01",
        "url": "https://voir-anime.to/anime/frieren-beyond-journey-end/frieren-01-vostfr-01/",
        "video_url": "https://vidmoly.biz/embed-0v50iamolxhq.html"
      },
      "...": "..."
    ]
  }
  ```

#### `GET /download/single`
- **Description** : Variante pour ne récupérer que le lien vidéo d'un épisode spécifique si vous ne voulez pas tout charger.
- **Paramètres** : 
  - `anime_name` (ex: `Frieren`)
  - `episode_num` (ex: `01`)
- **Retour** :
  ```json
  {
    "anime": "Frieren",
    "episode_title": "Frieren - 01 VOSTFR - 01",
    "video_url": "https://vidmoly.biz/embed-0v50iamolxhq.html"
  }
  ```
