# from seleniumbase import Driver
import time
import sys

def scrape_voiranime(url, output_file="output_voiranime.html"):
    """
    Extrait l'HTML d'une page VoirAnime en contournant Cloudflare Turnstile.
    Utilise SeleniumBase en mode UC (Undetected Chromedriver).
    """
    print(f"Extraction de : {url}")
    
    # Configuration du driver en mode indétectable et headless
    # headless2=True est le mode headless 'moderne' plus discret
    driver = Driver(browser="chrome", uc=True, headless2=True)
    
    try:
        driver.get(url)
        print("Page chargée, attente du contournement Cloudflare (vitesse variable)...")
        
        # On attend que la page soit réellement chargée (le titre change après le challenge)
        # On boucle pour vérifier le titre
        success = False
        for i in range(5): # 5 tentatives de 5 secondes
            title = driver.title
            print(f"Vérification [{i+1}/5] - Titre : {title}")
            
            if title and "Just a moment" not in title and "Cloudflare" not in title and "しばらくお待ちください" not in title:
                print("Challenge Cloudflare contourné avec succès !")
                success = True
                break
            
            # Si on est bloqué, UC mode tente souvent de gérer ça tout seul, on attend juste
            time.sleep(5)
            
        if not success:
            print("Le challenge semble toujours présent. Tentative de récupération forcée...")

        # Récupération de l'HTML rendu
        html = driver.page_source
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)
            
        print(f"HTML sauvegardé dans : {output_file}")
        print(f"Taille du fichier : {len(html)} caractères.")
        
        return True
    except Exception as e:
        print(f"Erreur lors de l'extraction : {e}")
        return False
    finally:
        driver.quit()

if __name__ == "__main__":
    target_url = "https://voiranime.tv/anime/sousou-no-frieren/sousou-no-frieren-02-vostfr/"
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
        
    scrape_voiranime(target_url)
