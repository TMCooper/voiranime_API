import json
import os
import re
import asyncio
import httpx
import unicodedata
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from rapidfuzz import process, fuzz
from src.core.resolver import StreamResolver

class VoirAnimeScraper:
    BASE_URL = "https://voir-anime.to"

    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.catalog_file = os.path.join(self.data_dir, "catalog.json")
        self.covers_file = os.path.join(self.data_dir, "covers.json")
        self.aliases_file = os.path.join(self.data_dir, "aliases.json")
        self.synopses_file = os.path.join(self.data_dir, "synopses.json")
        self.cookies_file = os.path.join(self.data_dir, "cookies.json")
        self.episodes_cache_file = os.path.join(self.data_dir, "episodes_cache.json")
        self.streams_cache_file = os.path.join(self.data_dir, "streams_cache.json")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://voir-anime.to/"
        }
        self.ROMAN_TO_INT = {
            'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5,
            'vi': 6, 'vii': 7, 'viii': 8, 'ix': 9, 'x': 10
        }
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        self.update_status = {
            "is_updating": False,
            "current_page": 0,
            "total_animes": 0
        }
        self.catalog = self.load_catalog()
        self.covers = self.load_covers()
        self.aliases = self.load_aliases()
        self.synopses = self.load_synopses()
        self.cookies = self.load_cookies()
        self.episodes_cache = self.load_episodes_cache()
        self.streams_cache = self.load_streams_cache()
        if self.cookies:
            self.headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        self.client = None
        self.resolver = StreamResolver(headers=self.headers)

    def init_client(self):
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                headers=self.headers,
                cookies=self.cookies or None,
                timeout=12.0,
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
            cookies=self.cookies or None,
            timeout=12.0,
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

    def load_covers(self):
        if os.path.exists(self.covers_file):
            try:
                with open(self.covers_file, "r", encoding="utf-8") as f:
                    self.covers = json.load(f)
                    return self.covers
            except Exception:
                pass
        self.covers = {}
        return {}

    def save_covers(self):
        try:
            with open(self.covers_file, "w", encoding="utf-8") as f:
                json.dump(self.covers, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_aliases(self):
        if os.path.exists(self.aliases_file):
            try:
                with open(self.aliases_file, "r", encoding="utf-8") as f:
                    self.aliases = json.load(f)
                    return self.aliases
            except Exception:
                pass
        self.aliases = {}
        return {}

    def save_aliases(self):
        try:
            with open(self.aliases_file, "w", encoding="utf-8") as f:
                json.dump(self.aliases, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_synopses(self):
        if os.path.exists(self.synopses_file):
            try:
                with open(self.synopses_file, "r", encoding="utf-8") as f:
                    self.synopses = json.load(f)
                    return self.synopses
            except Exception:
                pass
        self.synopses = {}
        return {}

    def save_synopses(self):
        try:
            with open(self.synopses_file, "w", encoding="utf-8") as f:
                json.dump(self.synopses, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_cookies(self):
        if os.path.exists(self.cookies_file):
            try:
                with open(self.cookies_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    elif isinstance(data, str):
                        c_dict = {}
                        for part in data.split(";"):
                            if "=" in part:
                                k, v = part.strip().split("=", 1)
                                c_dict[k.strip()] = v.strip()
                        return c_dict
            except Exception:
                pass
        return {}

    def save_cookies(self, cookies=None):
        if cookies is not None:
            self.cookies = cookies
        try:
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump(self.cookies, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def set_cookies(self, cookie_data):
        if isinstance(cookie_data, str):
            c_dict = {}
            for part in cookie_data.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    c_dict[k.strip()] = v.strip()
            self.cookies = c_dict
        elif isinstance(cookie_data, dict):
            self.cookies = cookie_data
        if self.cookies:
            self.headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        self.save_cookies()

    def load_episodes_cache(self):
        if os.path.exists(self.episodes_cache_file):
            try:
                with open(self.episodes_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_episodes_cache(self):
        try:
            with open(self.episodes_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.episodes_cache, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_streams_cache(self):
        if os.path.exists(self.streams_cache_file):
            try:
                with open(self.streams_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_streams_cache(self):
        try:
            with open(self.streams_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.streams_cache, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def search_site_fallback(self, search: str) -> list:
        try:
            query_param = search.replace(" ", "+")
            r = httpx.get(
                f"{self.BASE_URL}/?s={query_param}",
                headers=self.headers,
                timeout=8.0,
                follow_redirects=True
            )
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'lxml')
                found = []
                for h3 in soup.find_all('h3'):
                    a_tag = h3.find('a')
                    if a_tag:
                        name = a_tag.get_text(strip=True)
                        link = a_tag.get('href')
                        if name and link and "/anime/" in link:
                            found.append({"title": name, "lien": link, "link": link})
                return found
        except Exception as e:
            print(f"Error in search_site_fallback for '{search}': {e}")
        return []

    @staticmethod
    def normalize_title(title: str) -> str:
        if not title:
            return ""
        title = unicodedata.normalize("NFKD", title)
        title = "".join([c for c in title if not unicodedata.combining(c)])
        title = title.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")
        title = re.sub(r'[\/\\\:\*\?\"\<\>\|]', " ", title)
        title = re.sub(r"[^a-zA-Z0-9\-\_\&\.\'\#\s]", " ", title)
        return re.sub(r"\s+", " ", title).strip()

    @staticmethod
    def clean_string(text: str) -> str:
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    def load_base_anime_data(self) -> list:
        if not self.catalog:
            self.load_catalog()
        
        data = []
        for name, link in self.catalog.items():
            cover = self.covers.get(name, "")
            data.append({
                "title": self.normalize_title(name),
                "link": link,
                "cover": cover
            })
        return data

    def serch_anime(self, search: str, limit: int = 5) -> list:
        """
        Recherche fuzzy d'anime calquée sur le comportement de Cardinal.serchAnime dans AnimeSamaApi,
        avec fallback automatique sur le moteur de recherche VoirAnime en cas de titre alternatif/anglais.
        """
        if not self.catalog:
            self.load_catalog()

        cleaned_search = self.clean_string(search)
        if not cleaned_search:
            return []

        # Vérifier si un alias existe déjà dans le cache
        effective_search = search
        if cleaned_search in self.aliases:
            effective_search = self.aliases[cleaned_search]

        cleaned_effective = self.clean_string(effective_search)

        cleaned_to_orig = {}
        cleaned_to_link = {}
        cleaned_to_cover = {}

        for orig_name, link in self.catalog.items():
            cleaned = self.clean_string(orig_name)
            if cleaned and cleaned not in cleaned_to_orig:
                cleaned_to_orig[cleaned] = orig_name
                cleaned_to_link[cleaned] = link
                cleaned_to_cover[cleaned] = self.covers.get(orig_name, "")

        cleaned_titles = list(cleaned_to_orig.keys())
        q_tokens = set(cleaned_effective.split())
        wants_vf = "vf" in q_tokens or "(vf)" in search.lower()
        matches = process.extract(cleaned_effective, cleaned_titles, scorer=fuzz.token_set_ratio, limit=100)

        temp_results = []
        for cleaned_title, score, _ in matches:
            if score < 60:
                continue

            t_tokens = set(cleaned_title.split())
            common_tokens = q_tokens & t_tokens
            query_coverage = (len(common_tokens) / len(q_tokens)) if q_tokens else 0.0
            title_precision = (len(common_tokens) / len(t_tokens)) if t_tokens else 0.0

            length_ratio = len(cleaned_title) / len(cleaned_effective) if len(cleaned_effective) > 0 else 0
            specificity_bonus = 0.0
            if 0.9 <= length_ratio <= 1.1 and query_coverage >= 0.95:
                specificity_bonus = 10.0
            elif length_ratio < 0.5:
                specificity_bonus = -15.0

            coverage_adjustment = (query_coverage - 1.0) * 20.0 + (title_precision * 3.0)

            orig_title = cleaned_to_orig.get(cleaned_title)
            anime_link = cleaned_to_link.get(cleaned_title)
            cover = cleaned_to_cover.get(cleaned_title, "")

            vf_penalty = 0.0
            if orig_title and not wants_vf and ("(vf)" in orig_title.lower() or (anime_link and "-vf" in anime_link.lower())):
                vf_penalty = -1.0

            final_score = round(score + specificity_bonus + coverage_adjustment + vf_penalty, 2)

            if orig_title and anime_link:
                temp_results.append({
                    "title": orig_title,
                    "lien": anime_link,
                    "link": anime_link,
                    "cover": cover,
                    "final_score": final_score
                })

        temp_results.sort(key=lambda x: x["final_score"], reverse=True)

        # Si aucun résultat ou score faible (< 75), interroger le moteur de recherche de VoirAnime
        if not temp_results or (temp_results and temp_results[0]["final_score"] < 75):
            site_items = self.search_site_fallback(search)
            if site_items:
                for item in site_items:
                    orig_title = item["title"]
                    item_link = item["lien"]
                    cover = self.covers.get(orig_title, "")
                    temp_results.append({
                        "title": orig_title,
                        "lien": item_link,
                        "link": item_link,
                        "cover": cover,
                        "final_score": 100.0
                    })
                    if orig_title not in self.catalog:
                        self.catalog[orig_title] = item_link
                self.save_catalog()

                top_match = site_items[0]
                top_root, _ = self._resolve_franchise_root(top_match["title"], top_match["lien"])
                self.aliases[cleaned_search] = top_root
                self.save_aliases()

        temp_results.sort(key=lambda x: x["final_score"], reverse=True)

        final_results = []
        seen_links = set()
        for res in temp_results:
            if len(final_results) >= limit:
                break
            if res["lien"] not in seen_links:
                res["score"] = res.pop("final_score")
                final_results.append(res)
                seen_links.add(res["lien"])

        return final_results

    _SEASON_START_KW = re.compile(
        r'^(?:\d+|ii|iii|iv|v|vi|vii|viii|ix|x|s\d+|season|saison|ova|oav|special|specials|movie|film|'
        r'the\s+movie|the\s+final|the\s+last|remake|kai|part|stage|extra|plus|ex|new|born|hero|darkness|'
        r'shippuuden|shippuden|alternative|progressive|final|second|third|fourth|fifth|3d|hd|tv|ona|mini|'
        r'picture\s+drama|episode|arc|sp|gekijouban|kanketsu|gekitouhen|taidouhen|z|gt|super|daima|'
        r'stampede|stargaze|next|try|revolution|great|return|gorgeous|premium|excellent|kei|rou|shunmuki|'
        r'x\s+ut|prologue|omake|lite|wan|churutto|zoku|kan)\b',
        re.IGNORECASE
    )

    @staticmethod
    def _franchise_tokens(text: str) -> list:
        if not text:
            return []
        t = re.sub(r'\(VF\)', '', text, flags=re.IGNORECASE)
        t = (
            t.replace('½', ' 1 2 ')
            .replace('1/2', ' 1 2 ')
            .replace('²', ' 2 ')
            .replace('³', ' 3 ')
            .replace('+', ' plus ')
            .replace('×', ' x ')
            .replace('√', ' root ')
            .replace('∞', ' infinity ')
        )
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if not unicodedata.combining(c)).lower()
        t = re.sub(r'[^a-z0-9\s]', ' ', t)
        return t.split()

    def _is_franchise_child(self, child_name: str, root_name: str) -> bool:
        r_no_vf = re.sub(r'\(VF\)', '', root_name, flags=re.IGNORECASE).strip()
        c_no_vf = re.sub(r'\(VF\)', '', child_name, flags=re.IGNORECASE).strip()
        if not r_no_vf or not c_no_vf:
            return False
        if r_no_vf.startswith('_') and not c_no_vf.startswith('_'):
            return False

        rt = self._franchise_tokens(r_no_vf)
        ct = self._franchise_tokens(c_no_vf)
        if not rt or not ct or len(ct) < len(rt):
            return False
        if ct == rt:
            return True

        # 1. Préfixe direct par tokens entiers
        if ct[:len(rt)] == rt:
            rem = ct[len(rt):]
            rem_str = " ".join(rem)
            has_sep = bool(re.match(r'^' + re.escape(r_no_vf) + r'\s*[:\-–—\(!\?\.\/☆△]', c_no_vf, re.IGNORECASE))
            if len(rt) >= 3:
                return True
            if len(rt) == 2:
                if rt == ['high', 'score'] and rem[0] == 'girl':
                    return False
                if not has_sep and rem[0] in {'of', 'in', 'to', 'for', 'with', 'on', 'at', 'from', 'by', 'no', 'wa', 'ga', 'wo', 'ni'}:
                    return False
                return True
            # len(rt) == 1 : exiger un séparateur explicite ou un mot-clé de saison/suite/OAV/film
            if has_sep or self._SEASON_START_KW.match(rem_str):
                return True
            return False

        # 2. Spin-offs / suites avec préfixe connu devant la racine (ex: Motto To Love-Ru, Zoku ..., Boruto: Naruto ...)
        if len(rt) >= 2 or rt == ['naruto']:
            for idx in range(1, len(ct) - len(rt) + 1):
                if ct[idx:idx + len(rt)] == rt:
                    pref = " ".join(ct[:idx])
                    if pref in {'motto', 'zoku', 'zan', 'shin', 'new', 'super', 'the first', 'gekijouban', 'eiga', 'demon slayer', 'boruto', 'the last'}:
                        return True
                    pos = c_no_vf.lower().find(r_no_vf.lower())
                    if len(rt) >= 3 and pos > 0 and ':' in c_no_vf[:pos]:
                        return True

        return False

    def _resolve_franchise_root(self, title: str, url: str = "") -> tuple[str, str]:
        cand = re.sub(r'\(VF\)', '', title or '', flags=re.IGNORECASE).strip()
        if not cand:
            return title, url

        regex_root = self._extract_franchise_root(cand)
        parents = []

        for cat_name, cat_url in self.catalog.items():
            is_vf = bool(re.search(r'\(VF\)', cat_name, re.IGNORECASE) or "-vf" in cat_url.lower())
            if is_vf:
                continue
            if self._is_franchise_child(cand, cat_name) or (regex_root and self._is_franchise_child(regex_root, cat_name)):
                parents.append((len(self._franchise_tokens(cat_name)), len(cat_name), cat_name, cat_url))

        if parents:
            parents.sort(key=lambda x: (x[0], x[1]))
            return parents[0][2], parents[0][3]

        # Fallback si seules des entrées VF ou secondaires existent dans le catalogue
        if regex_root and regex_root != cand:
            for cat_name, cat_url in self.catalog.items():
                if cat_name != title and self._is_franchise_child(cat_name, regex_root):
                    return regex_root, url

        return cand, url

    @staticmethod
    def _strip_root_prefix(clean_name_no_vf: str, root_name: str) -> str:
        if not root_name:
            return clean_name_no_vf
        r_esc = re.escape(root_name.strip())
        r_pat = (
            r_esc.replace(r'\ ', r'[\s:\-–—\.\!☆△\/]*')
            .replace('½', '(?:½|1/2)')
            .replace(r'1\/2', '(?:½|1/2)')
        )
        m = re.match(r'^' + r_pat + r'[\s:\-–—\.\!☆△]*', clean_name_no_vf, flags=re.IGNORECASE)
        if m and m.end() < len(clean_name_no_vf):
            sub = clean_name_no_vf[m.end():].strip(" -:–—")
            if sub:
                return sub
        return clean_name_no_vf

    def _extract_franchise_root(self, title: str) -> str:
        # Nettoie les suffixes de saison, de langue ou de type pour identifier la franchise
        t = re.sub(r'\(VF\)', '', title, flags=re.IGNORECASE)
        t = re.sub(r'\(\d{4}\)', '', t) # enlever les années comme (2024)
        t = re.sub(r'\b(?:S\d+|Season\s*\d+|Saison\s*\d+|\d+(?:nd|rd|th|st)\s*Season)\b.*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'\b(?:The\s+Movie|Movie|Film|OVA|OAV|Special|Specials|Remake)\b.*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'\b(X|IX|VIII|VII|VI|V|IV|III|II|I)\b\s*$', '', t, flags=re.IGNORECASE)
        t = re.sub(r'\s+\d+$', '', t) # trailing number like "Frieren 2"
        return t.strip(" -_:")

    def _parse_season_label(self, clean_name_no_vf: str, root_name: str = "") -> str:
        sub = self._strip_root_prefix(clean_name_no_vf, root_name) if root_name else clean_name_no_vf
        sub_clean = sub.strip(" -:–—")
        if not sub_clean or (root_name and self._franchise_tokens(clean_name_no_vf) == self._franchise_tokens(root_name)):
            return "Saison 1"

        # 1. Année ou Remake (ex: "(2024)", "(2024) S2", "Remake 2024")
        m_rem_s = re.fullmatch(r'(?:remake\s*)?\(?(\d{4})\)?\s*(?:S|Saison|Season)\s*(\d+)', sub_clean, re.IGNORECASE)
        if m_rem_s:
            return f"Remake {m_rem_s.group(1)} Saison {m_rem_s.group(2)}"

        m_rem = re.fullmatch(r'(?:remake\s*)?\(?(\d{4})\)?(?:\s*remake)?', sub_clean, re.IGNORECASE)
        if m_rem:
            return f"Remake {m_rem.group(1)}"

        if re.fullmatch(r'remake', sub_clean, re.IGNORECASE):
            return "Remake"

        # 2. Numéro de saison pur (ex: "2", "S2", "Season 2", "Saison 2", "2nd Season", "II", "III")
        m_s_pure = re.fullmatch(
            r'(?:(?:S|Saison|Season)\s*(\d{1,2})|(\d{1,2})\s*(?:nd|rd|th|st)\s*Season|(\d{1,2}))',
            sub_clean,
            re.IGNORECASE
        )
        if m_s_pure:
            num = m_s_pure.group(1) or m_s_pure.group(2) or m_s_pure.group(3)
            return f"Saison {int(num)}"

        m_rom_pure = re.fullmatch(r'(?:(?:S|Saison|Season)\s*)?(X|IX|VIII|VII|VI|V|IV|III|II)', sub_clean, re.IGNORECASE)
        if m_rom_pure:
            rom = m_rom_pure.group(1).lower()
            if rom in self.ROMAN_TO_INT and self.ROMAN_TO_INT[rom] > 1:
                return f"Saison {self.ROMAN_TO_INT[rom]}"

        # 3. OAV / OVA / Special pur (ex: "OVA", "OAV", "OVA 2", "Special", "Specials")
        m_ova_pure = re.fullmatch(r'\(?(?:OVA|OAV)\)?(?:\s*0*(\d+))?', sub_clean, re.IGNORECASE)
        if m_ova_pure:
            return f"OAV {int(m_ova_pure.group(1))}" if m_ova_pure.group(1) else "OAV"

        m_spec_pure = re.fullmatch(r'\(?(?:Special|Specials)\)?(?:\s*0*(\d+))?', sub_clean, re.IGNORECASE)
        if m_spec_pure:
            return f"OAV {int(m_spec_pure.group(1))}" if m_spec_pure.group(1) else "OAV"

        # 4. Film / Movie pur ou préfixé (ex: "Movie", "Movie 1", "Movie: Ordinal Scale", "THE MOVIE: Futari no Hero")
        m_film_pure = re.fullmatch(r'\(?(?:The\s+)?(?:Movie|Film)\)?(?:\s*0*(\d+))?', sub_clean, re.IGNORECASE)
        if m_film_pure:
            return f"Film {int(m_film_pure.group(1))}" if m_film_pure.group(1) else "Film"

        m_film_sub = re.match(r'^\(?(?:The\s+)?(?:Movie|Film)\)?(?:\s*0*(\d+))?\s*[:\-–—]+\s*(.+)$', sub_clean, re.IGNORECASE)
        if m_film_sub:
            f_num = f" {int(m_film_sub.group(1))}" if m_film_sub.group(1) else ""
            f_sub = m_film_sub.group(2).strip(" -:–—")
            return f"Film{f_num}: {f_sub}" if f_sub else f"Film{f_num}"

        # 5. Suites connues exactes (Shippuuden = Saison 2, Sennen Kessen-hen = Saison 2, Kai = Kai)
        lower_sub = sub_clean.lower()
        if lower_sub in ("shippuuden", "shippuden", "sennen kessen-hen"):
            return "Saison 2"
        if lower_sub == "kai":
            return "Kai"

        # 6. Conserver le sous-titre / nom de saison exact (ex: "New", "BorN", "New OVA Oppai, Tsutsumimasu!")
        return sub_clean

    def _extract_synopsis_from_soup(self, soup: BeautifulSoup) -> str:
        desc_node = (
            soup.select_one('.description-summary .summary__content')
            or soup.select_one('.summary__content')
            or soup.select_one('.description-summary')
        )
        if not desc_node:
            og_desc = soup.find('meta', property='og:description')
            if og_desc and og_desc.get('content'):
                return og_desc['content'].strip()
            return ""

        p_tags = desc_node.find_all('p')
        if p_tags:
            paragraphs = [p.get_text(strip=True).replace('\xa0', ' ') for p in p_tags if p.get_text(strip=True)]
            if paragraphs:
                return "\n\n".join(paragraphs).strip()

        text = desc_node.get_text(separator="\n\n", strip=True).replace('\xa0', ' ')
        if text:
            return text

        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            return og_desc['content'].strip()
        return ""

    async def _fetch_metadata_if_missing(self, anime_name: str, anime_url: str, client=None) -> tuple[str, str]:
        cover = self.covers.get(anime_name, "")
        synopsis = self.synopses.get(anime_url, "")
        if not synopsis and anime_name:
            synopsis = self.synopses.get(anime_name, "")

        if cover and synopsis:
            return cover, synopsis

        http_client, should_close = self._get_active_client(client)
        try:
            r = await http_client.get(anime_url)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'lxml')
                if not synopsis:
                    synopsis = self._extract_synopsis_from_soup(soup)
                    if synopsis:
                        self.synopses[anime_url] = synopsis
                        if anime_name:
                            self.synopses[anime_name] = synopsis
                        self.save_synopses()

                if not cover:
                    og = soup.find('meta', property='og:image')
                    if og and og.get('content'):
                        cover = og['content']
                        self.covers[anime_name] = cover
                        self.save_covers()
                    else:
                        img = soup.select_one('.summary_image img')
                        if img and img.get('src'):
                            cover = img['src']
                            self.covers[anime_name] = cover
                            self.save_covers()
        except Exception as e:
            print(f"Error fetching metadata for '{anime_url}': {e}")
        finally:
            if should_close:
                await http_client.aclose()
        return cover, synopsis

    async def _fetch_cover_if_missing(self, anime_name: str, anime_url: str, client=None) -> str:
        cover, _ = await self._fetch_metadata_if_missing(anime_name, anime_url, client=client)
        return cover

    async def _fetch_synopsis(self, anime_url: str, anime_name: str = "", client=None) -> str:
        _, synopsis = await self._fetch_metadata_if_missing(anime_name, anime_url, client=client)
        return synopsis

    async def get_info_anime(self, query: str) -> list:
        """
        Retourne la liste des saisons disponibles pour un anime sous le format exact
        attendu par YoitsuWrap et Cardinal.getInfoAnime:
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
        if not query:
            return []

        search_results = self.serch_anime(query, limit=5)
        if not search_results:
            return []

        best_match = search_results[0]
        matched_title = best_match["title"]
        matched_url = best_match["lien"]
        root_name, root_url = self._resolve_franchise_root(matched_title, matched_url)
        if not root_name:
            root_name = matched_title
        base_url = root_url or matched_url

        # Trouver tous les animes du catalogue appartenant à cette même franchise (sans faux positifs)
        root_tokens = self._franchise_tokens(root_name)
        franchise_entries = []

        for name, link in self.catalog.items():
            if self._is_franchise_child(name, root_name):
                franchise_entries.append((name, link))

        if not franchise_entries:
            franchise_entries = [(matched_title, matched_url)]

        # Trier pour traiter d'abord la racine, puis les VOSTFR avant les VF
        def _entry_order(item):
            n, l = item
            is_vf_flag = bool(re.search(r'\(VF\)', n, re.IGNORECASE) or "-vf" in l.lower())
            no_vf = re.sub(r'\(VF\)', '', n, flags=re.IGNORECASE).strip()
            is_root_flag = (self._franchise_tokens(no_vf) == root_tokens)
            return (0 if is_root_flag else 1, 1 if is_vf_flag else 0, len(no_vf), n.lower())

        franchise_entries.sort(key=_entry_order)

        cover, synopsis = await self._fetch_metadata_if_missing(root_name, base_url, client=self.client)

        # Classifier en saisons / films / OAVs / Remakes sans jamais écraser une entrée existante distincte
        seasons_map = {
            "Saison 1": {"vostfr": base_url, "vf": None, "url": base_url, "_title": root_name}
        }

        for name, link in franchise_entries:
            is_vf = bool(re.search(r'\(VF\)', name, re.IGNORECASE) or "-vf" in link.lower())
            clean_name_no_vf = re.sub(r'\(VF\)', '', name, flags=re.IGNORECASE).strip()
            cand_tokens = self._franchise_tokens(clean_name_no_vf)

            is_root = (cand_tokens == root_tokens or link.rstrip('/') == base_url.rstrip('/'))
            if is_root:
                season_label = "Saison 1"
            else:
                season_label = self._parse_season_label(clean_name_no_vf, root_name=root_name)
                # Ne jamais laisser un titre secondaire écraser Saison 1
                if season_label == "Saison 1":
                    sub = self._strip_root_prefix(clean_name_no_vf, root_name).strip(" -:–—")
                    season_label = sub if (sub and sub != clean_name_no_vf) else f"Autre ({clean_name_no_vf})"

            if is_vf and not is_root:
                # Associer la VF à son homologue VOSTFR exact s'il existe déjà dans seasons_map
                matched_existing_label = None
                for existing_lbl, existing_data in seasons_map.items():
                    if existing_data.get("_title") and self._franchise_tokens(existing_data["_title"]) == cand_tokens:
                        matched_existing_label = existing_lbl
                        break
                if matched_existing_label:
                    season_label = matched_existing_label
                elif season_label in seasons_map and seasons_map[season_label]["vf"] and seasons_map[season_label]["vf"].rstrip('/') != link.rstrip('/'):
                    raw_sub = self._strip_root_prefix(clean_name_no_vf, root_name).strip(" -:–—")
                    if raw_sub and raw_sub != season_label and (raw_sub not in seasons_map or not seasons_map[raw_sub]["vf"]):
                        season_label = raw_sub
                    else:
                        idx_dup = 2
                        while f"{season_label} ({idx_dup})" in seasons_map and seasons_map[f"{season_label} ({idx_dup})"]["vf"]:
                            idx_dup += 1
                        season_label = f"{season_label} ({idx_dup})"
            elif not is_vf and not is_root:
                # Empêcher deux entrées VOSTFR distinctes (ex: OVA et Specials, ou New OVA) de s'écraser
                if season_label in seasons_map and seasons_map[season_label]["vostfr"] and seasons_map[season_label]["vostfr"].rstrip('/') != link.rstrip('/'):
                    raw_sub = self._strip_root_prefix(clean_name_no_vf, root_name).strip(" -:–—")
                    if raw_sub and raw_sub != season_label and (raw_sub not in seasons_map or not seasons_map[raw_sub]["vostfr"]):
                        season_label = raw_sub
                    else:
                        idx_dup = 2
                        while f"{season_label} ({idx_dup})" in seasons_map and seasons_map[f"{season_label} ({idx_dup})"]["vostfr"]:
                            idx_dup += 1
                        season_label = f"{season_label} ({idx_dup})"

            if season_label not in seasons_map:
                seasons_map[season_label] = {"vostfr": None, "vf": None, "url": link, "_title": clean_name_no_vf}

            if is_vf:
                seasons_map[season_label]["vf"] = link
                if not seasons_map[season_label]["url"]:
                    seasons_map[season_label]["url"] = link
            else:
                seasons_map[season_label]["vostfr"] = link
                seasons_map[season_label]["url"] = link
                seasons_map[season_label]["_title"] = clean_name_no_vf

        # Construire la liste finale
        result = []
        for s_label, urls in seasons_map.items():
            primary_url = urls["vostfr"] or urls["vf"] or urls["url"]
            result.append({
                "base_url": base_url,
                "title": root_name,
                "cover": cover,
                "synopsis": synopsis,
                "Saison": s_label,
                "url": primary_url,
                "_vostfr_url": urls["vostfr"],
                "_vf_url": urls["vf"]
            })

        # Trier Saison 1, Saison 2, Remake ..., Film, OAV, puis sous-titres
        def sort_key(item):
            s = item["Saison"]
            m = re.search(r'\d+', s)
            if s.startswith("Saison") and m:
                return (0, int(m.group()), s)
            if "Remake" in s:
                return (0, 99, s)
            if s.startswith("Film"):
                return (1, int(m.group()) if m else 0, s)
            if s.startswith("OAV") or s.lower() == "specials":
                return (2, int(m.group()) if m else 0, s)
            return (3, 0, s)

        result.sort(key=sort_key)
        return result

    async def get_specific_anime(self, query: str, saison: str = "saison1", version: str = "vostfr") -> dict:
        """
        Retourne les détails spécifiques d'une saison et version donnée.
        Supporte les notations variées de YoitsuWrap et AnimeSama (ex: Remake 2024, remake2024, 2024, saison3...).
        """
        seasons = await self.get_info_anime(query)
        if not seasons:
            return {}

        saison_str = (saison or "saison1").strip().lower().replace(" ", "")
        version_str = (version or "vostfr").strip().lower()

        # Extraire le numéro de saison ciblé
        num_target = re.search(r'\d+', saison_str)
        target_s_num = num_target.group() if num_target else None

        selected = None

        # 0. Si la requête cible directement un OAV/saison/film spécifique et que 'saison' est laissé par défaut ('saison1')
        if saison_str in ("saison1", "s1", ""):
            direct_matches = self.serch_anime(query, limit=1)
            if direct_matches:
                dm_title = direct_matches[0]["title"]
                dm_url = direct_matches[0]["lien"].rstrip("/")
                dm_tokens = self._franchise_tokens(dm_title)
                root_tokens = self._franchise_tokens(seasons[0]["title"])
                if dm_tokens != root_tokens:
                    for item in seasons:
                        candidates_urls = [
                            (item.get("url") or "").rstrip("/"),
                            (item.get("_vostfr_url") or "").rstrip("/"),
                            (item.get("_vf_url") or "").rstrip("/"),
                        ]
                        if dm_url in candidates_urls:
                            selected = item
                            break

        # 1. Match exact prioritaire (insensible à la casse, aux espaces et à la ponctuation)
        if not selected:
            saison_tokens = self._franchise_tokens(saison or "saison1")
            for item in seasons:
                s_item = item["Saison"].lower().replace(" ", "")
                if saison_str == s_item or (saison_tokens and saison_tokens == self._franchise_tokens(item["Saison"])):
                    selected = item
                    break

        # 2. Match si "remake" ou année demandée (ex: "remake2024", "2024")
        if not selected and ("remake" in saison_str or (target_s_num and len(target_s_num) == 4)):
            for item in seasons:
                s_item = item["Saison"].lower().replace(" ", "")
                if "remake" in s_item or (target_s_num and target_s_num in s_item):
                    selected = item
                    break

        # 3. Match par numéro de saison (ex: "saison2" ou "s2" dans "Saison 2")
        if not selected and target_s_num and ("saison" in saison_str or re.fullmatch(r's\d+', saison_str)):
            for item in seasons:
                s_item = item["Saison"].lower().replace(" ", "")
                if s_item == f"saison{target_s_num}" or s_item == f"s{target_s_num}":
                    selected = item
                    break

        # 4. Match partiel intelligent (en privilégiant la correspondance la plus spécifique/longue)
        if not selected:
            norm_target = saison_str.replace("ova", "oav").replace("movie", "film")
            best_partial = None
            best_partial_len = -1
            for item in seasons:
                s_item = item["Saison"].lower().replace(" ", "")
                norm_item = s_item.replace("ova", "oav").replace("movie", "film")
                if norm_target in norm_item:
                    # Privilégier l'item dont la longueur est la plus proche de la cible
                    score_len = 1000 - abs(len(norm_item) - len(norm_target))
                    if score_len > best_partial_len:
                        best_partial_len = score_len
                        best_partial = item
                elif norm_item in norm_target and len(norm_item) > best_partial_len:
                    best_partial_len = len(norm_item)
                    best_partial = item
            if best_partial:
                selected = best_partial

        # 4. Fallback par index ordinal (ex: saison3 alors que la 3ème saison s'appelle Remake 2024)
        if not selected and target_s_num and target_s_num.isdigit():
            idx = int(target_s_num) - 1
            if 0 <= idx < len(seasons):
                selected = seasons[idx]

        if not selected:
            selected = seasons[0]

        target_url = selected["url"]
        if version_str == "vf" and selected.get("_vf_url"):
            target_url = selected["_vf_url"]
        elif version_str == "vostfr" and selected.get("_vostfr_url"):
            target_url = selected["_vostfr_url"]

        # Récupération du synopsis : priorité au synopsis déjà extrait, sinon fetch
        synopsis = selected.get("synopsis") or ""
        if not synopsis:
            synopsis = await self._fetch_synopsis(target_url, anime_name=selected.get("title", ""), client=self.client)
            if not synopsis and selected.get("base_url") and selected["base_url"] != target_url:
                synopsis = await self._fetch_synopsis(selected["base_url"], anime_name=selected.get("title", ""), client=self.client)

        return {
            "base_url": selected["base_url"],
            "title": selected["title"],
            "cover": selected["cover"],
            "synopsis": synopsis,
            "Saison": selected["Saison"],
            "url": target_url
        }

    async def get_anime_link(self, nom: str, saison: str = "saison1", version: str = "vostfr") -> list:
        """
        Récupère les épisodes de la saison/version demandée et résout les liens vidéo directs (.m3u8/.mp4/embed)
        au format [ {"episode": 1, "url": "..."}, ... ] pour compatibilité totale avec YoitsuWrap et yt-dlp.
        """
        spec = await self.get_specific_anime(nom, saison, version)
        if not spec or "url" not in spec or not spec["url"]:
            return []

        anime_url = spec["url"]
        episodes = await self.fetch_episodes(anime_url)
        if not episodes:
            return []

        # Trier les épisodes par numéro croissant (1, 2, 3...)
        def get_episode_num(ep, fallback_idx):
            nums = re.findall(r'\b\d+\b', ep["title"])
            if nums:
                return int(nums[-1])
            return fallback_idx + 1

        episodes_with_num = []
        for idx, ep in enumerate(episodes):
            ep_num = get_episode_num(ep, idx)
            episodes_with_num.append((ep_num, ep))

        episodes_with_num.sort(key=lambda x: x[0])

        http_client, should_close = self._get_active_client()
        sem = asyncio.Semaphore(10)
        cf_blocked = False
        cache_dirty = False

        async def resolve_one(ep_num, ep_data):
            nonlocal cf_blocked, cache_dirty
            # 1. Vérifier si le flux direct ou le lecteur est déjà en cache (et le rafraîchir si expiré / autre IP-ASN)
            if ep_data["url"] in self.streams_cache and self.streams_cache[ep_data["url"]]:
                c = self.streams_cache[ep_data["url"]]
                old_stream = c.get("stream_url") if isinstance(c, dict) else c
                if self.resolver.is_stream_expired_or_invalid(old_stream):
                    async with sem:
                        c = await self._ensure_fresh_stream(
                            ep_data["url"], c, client=http_client, save_cache=False
                        )
                        cache_dirty = True
                stream = c.get("stream_url") or c.get("iframe_url") if isinstance(c, dict) else c
                if stream:
                    return {"episode": ep_num, "url": stream}

            # 2. Si pas bloqué par Cloudflare, tenter la résolution dynamique
            if not cf_blocked:
                async with sem:
                    try:
                        resolved = await self.fetch_download_link(ep_data["url"], client=http_client, resolve_stream=True)
                        if resolved == "CLOUDFLARE_BLOCKED":
                            cf_blocked = True
                        elif isinstance(resolved, dict):
                            final_url = resolved.get("stream_url") or resolved.get("iframe_url")
                            if final_url:
                                return {"episode": ep_num, "url": final_url}
                        elif resolved:
                            return {"episode": ep_num, "url": resolved}
                    except Exception:
                        pass

            # 3. Ne jamais renvoyer l'URL de la page web VoirAnime comme flux vidéo (incompatible yt-dlp)
            return None

        tasks = [resolve_one(num, ep) for num, ep in episodes_with_num]
        results = await asyncio.gather(*tasks)

        if cache_dirty:
            self.save_streams_cache()

        if should_close:
            await http_client.aclose()

        valid_links = [r for r in results if r is not None]
        valid_links.sort(key=lambda x: x["episode"])
        return valid_links

    def get_scan_hashmap(self, nom: str) -> dict:
        """
        VoirAnime est dédié aux vidéos/animes et ne dispose pas de scans intégrés.
        Renvoie une structure vide propre pour ne pas crasher YoitsuWrap.
        """
        return {"title": nom, "max_chapter": 0}

    def get_scan_link(self, nom: str, chap: str = "all") -> dict:
        """
        Renvoie un dict vide propre pour ne pas crasher YoitsuWrap.
        """
        return {}

    def resolve_anime(self, anime_name: str) -> list:
        # Méthode legacy avec support fuzzy amélioré
        fuzzy = self.serch_anime(anime_name, limit=10)
        return [{"name": f["title"], "url": f["lien"]} for f in fuzzy]

    async def _fetch_catalog_page(self, client, page):
        url = f"{self.BASE_URL}/liste-danimes/page/{page}/" if page > 1 else f"{self.BASE_URL}/liste-danimes/"
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

    async def fetch_episodes(self, anime_url: str, client=None) -> list:
        clean_url = anime_url.rstrip("/") + "/"
        if clean_url in self.episodes_cache and self.episodes_cache[clean_url]:
            return self.episodes_cache[clean_url]
        if anime_url in self.episodes_cache and self.episodes_cache[anime_url]:
            return self.episodes_cache[anime_url]

        http_client, should_close = self._get_active_client(client)
        try:
            resp = await http_client.get(anime_url)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, 'lxml')
            episodes = []
            
            # 1. Liens via les chapitres standard de la page
            chapter_list = soup.find_all("li", class_="wp-manga-chapter")
            if chapter_list:
                for li in chapter_list:
                    a_tag = li.find("a")
                    if a_tag:
                        ep_name = a_tag.text.strip()
                        ep_link = a_tag.get("href")
                        if ep_link:
                            episodes.append({
                                "title": ep_name,
                                "url": ep_link
                            })

            # 2. Si pas trouvé via li, chercher dans le sélecteur <select class="single-chapter-select">
            if not episodes:
                options = soup.select("select.single-chapter-select option")
                for opt in options:
                    ep_link = opt.get("data-redirect")
                    ep_num = opt.text.strip()
                    if ep_link:
                        episodes.append({
                            "title": f"Episode {ep_num}",
                            "url": ep_link
                        })

            if episodes:
                self.episodes_cache[clean_url] = episodes
                self.save_episodes_cache()

            return episodes
        except Exception as e:
            print(f"Error fetching episodes from {anime_url}: {e}")
            return []
        finally:
            if should_close:
                await http_client.aclose()

    async def _ensure_fresh_stream(self, episode_url: str, cached_entry, client=None, save_cache=True):
        """
        Vérifie si une entrée de self.streams_cache est toujours valide pour l'IP/ASN courant
        et non expirée. Si elle est expirée, liée à un autre ASN, sur vmbox.space,
        ou encore sous forme d'embed (ex: ansembed/voembed), la résout à la volée.
        """
        if isinstance(cached_entry, dict):
            stream_url = cached_entry.get("stream_url")
            iframe_url = cached_entry.get("iframe_url") or stream_url
            host = cached_entry.get("host") or "voembed"
            stream_type = cached_entry.get("stream_type") or "hls"
        else:
            stream_url = str(cached_entry)
            iframe_url = stream_url
            host = "voembed"
            stream_type = "hls"

        if not self.resolver.is_stream_expired_or_invalid(stream_url):
            return cached_entry if isinstance(cached_entry, dict) else {
                "iframe_url": iframe_url,
                "stream_url": stream_url,
                "stream_type": stream_type,
                "host": host,
            }

        http_client, should_close = self._get_active_client(client)
        try:
            target_to_resolve = (
                iframe_url if (iframe_url and "embed-" in iframe_url) else (stream_url or iframe_url)
            )
            resolved = await self.resolver.resolve(target_to_resolve, client=http_client)
            if resolved.get("status") == "success" and resolved.get("stream_url"):
                vid_id = self.resolver.extract_vm_video_id(target_to_resolve)
                clean_iframe = (
                    iframe_url
                    if (iframe_url and "embed-" in iframe_url)
                    else (f"https://voembed.net/embed-{vid_id}.html" if vid_id else resolved.get("embed_url", iframe_url))
                )
                updated = {
                    "iframe_url": clean_iframe,
                    "stream_url": resolved["stream_url"],
                    "stream_type": resolved.get("type", "hls"),
                    "host": resolved.get("host") or host,
                }
                self.streams_cache[episode_url] = updated
                if save_cache:
                    self.save_streams_cache()
                return updated
        except Exception:
            pass
        finally:
            if should_close:
                await http_client.aclose()

        return cached_entry if isinstance(cached_entry, dict) else {
            "iframe_url": iframe_url,
            "stream_url": stream_url,
            "stream_type": stream_type,
            "host": host,
        }

    async def fetch_download_link(self, episode_url: str, client=None, resolve_stream=True):
        if episode_url in self.streams_cache and self.streams_cache[episode_url]:
            if not resolve_stream:
                c = self.streams_cache[episode_url]
                return c.get("iframe_url") or c.get("stream_url") if isinstance(c, dict) else c
            return await self._ensure_fresh_stream(
                episode_url, self.streams_cache[episode_url], client=client, save_cache=True
            )

        http_client, should_close = self._get_active_client(client)
        try:
            resp = await http_client.get(episode_url)
            if resp.status_code in (403, 503) or "challenge" in resp.text.lower():
                return "CLOUDFLARE_BLOCKED"
            if resp.status_code != 200:
                return None

            html = resp.text
            iframe_url = None

            # 1. Analyser thisChapterSources pour accéder à tous les lecteurs
            candidates = []
            sources_match = re.search(r'var\s+thisChapterSources\s*=\s*(\{.*?\});', html)
            if sources_match:
                try:
                    sources_dict = json.loads(sources_match.group(1))
                    # Priorité des lecteurs (prioriser les flux directement extractibles en .m3u8 / .mp4 pour yt-dlp)
                    def source_priority(key):
                        k = key.lower()
                        if "sibnet" in k: return 999
                        if "mytv" in k or "voembed" in k or "ansembed" in k: return 0
                        if "vidmoly" in k: return 1
                        if "sendvid" in k: return 2
                        if "vidoza" in k: return 3
                        if any(h in k for h in ["smoothpre", "vidhide", "streamwish"]): return 4
                        if "voe" in k: return 5
                        if "stape" in k or "streamtape" in k: return 6
                        if "fhd" in k or "mail" in k: return 7
                        if "sb" in k: return 8
                        if "moon" in k: return 9
                        return 20

                    sorted_keys = sorted(sources_dict.keys(), key=source_priority)
                    for k in sorted_keys:
                        if "sibnet" in k.lower():
                            continue
                        iframe_html = sources_dict[k]
                        src_match = re.search(r'src=["\']([^"\']+)["\']', iframe_html)
                        if src_match:
                            c_url = src_match.group(1).replace(r"\/", "/")
                            if "voiranime" not in c_url and "sibnet" not in c_url.lower():
                                candidates.append((k, c_url))
                except Exception:
                    pass

            # 2. Si aucun candidat dans thisChapterSources, inspecter les tags iframe directs
            if not candidates:
                soup = BeautifulSoup(html, 'lxml')
                iframes = soup.find_all("iframe")
                for iframe in iframes:
                    src = iframe.get("src")
                    if src and "voiranime" not in src and "sibnet" not in src.lower():
                        candidates.append(("iframe", src))

            if not candidates:
                return None

            if not resolve_stream:
                return candidates[0][1]

            # 3. Résoudre les candidats par ordre de priorité jusqu'à trouver un flux direct exploitable par yt-dlp
            first_fallback = None
            for player_name, c_url in candidates:
                try:
                    resolved = await self.resolver.resolve(c_url, client=http_client)
                    if resolved.get("status") == "success" and resolved.get("stream_url"):
                        res = {
                            "iframe_url": c_url,
                            "stream_url": resolved.get("stream_url"),
                            "stream_type": resolved.get("type"),
                            "host": resolved.get("host") or player_name
                        }
                        self.streams_cache[episode_url] = res
                        self.save_streams_cache()
                        return res
                    elif not first_fallback and resolved.get("stream_url"):
                        first_fallback = {
                            "iframe_url": c_url,
                            "stream_url": resolved.get("stream_url"),
                            "stream_type": resolved.get("type"),
                            "host": resolved.get("host") or player_name
                        }
                except Exception:
                    continue

            # Si aucun flux direct (.m3u8/.mp4) n'a pu être extrait avec succès, utiliser le premier candidat valide
            if first_fallback:
                self.streams_cache[episode_url] = first_fallback
                self.save_streams_cache()
                return first_fallback

            default_candidate = candidates[0][1]
            res = {
                "iframe_url": default_candidate,
                "stream_url": default_candidate,
                "stream_type": "embed",
                "host": candidates[0][0]
            }
            self.streams_cache[episode_url] = res
            self.save_streams_cache()
            return res
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
