import uvicorn

def launch_api(host: str = "127.0.0.1", port: int = 8000, reload: bool = True):
    
    # Lancement via uvicorn. 
    # reload=True nécessite de passer l'application sous forme de chaîne "module:app"
    uvicorn.run("src.main:app", host=host, port=port, reload=reload)

if __name__ == "__main__":
    # Exécution directe du fichier (équivalent au run_api.bat)
    launch_api()
