@echo off
echo Lancement de l'API VoirAnime...
call .\venv\Scripts\activate
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
