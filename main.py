import os
import pathlib
from fastapi import FastAPI, UploadFile, File
from google.adk.sessions import InMemorySessionService
from google.adk.cli.fast_api import get_fast_api_app
from google.genai import types
from google import genai


#TODO: use another method for fastAPI as agents are directly instantiated in main.py
app: FastAPI = get_fast_api_app(
    agents_dir="./agents/",
    web=True # Abilita anche la Web UI di debug
)
session_service = InMemorySessionService()


import os

def save_text_to_file(text: str, folder_path: str, filename: str) -> str:
    """
    Salva un testo in un file all'interno di una cartella. 
    Se la cartella non esiste, viene creata automaticamente.

    Args:
        text (str): Contenuto da scrivere nel file.
        folder_path (str): Percorso della cartella in cui salvare il file.
        filename (str): Nome del file (es: "output.txt").

    Returns:
        str: Percorso completo del file salvato.
    """

    # Crea la cartella se non esiste
    os.makedirs(folder_path, exist_ok=True)

    # Costruisci percorso completo
    file_path = os.path.join(folder_path, filename)

    # Scrivi il contenuto
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)

    return file_path




@app.post("/run_agent_pentests")
async def process_files(
    pdf: UploadFile = File(...),
    mapping_csv: UploadFile = File(...)
):
    """FastAPI Endpoint to process data with parameters.

    Args:
        pdf (UploadFile, optional): pdf file. Defaults to File(...).
        mapping_csv (UploadFile, optional): csv mapping file. Defaults to File(...).

    Returns:
        FileResponse: the enriched file as output. 
    """
   
    client = genai.Client()  # usa GOOGLE_API_KEY da env

    pdf_path = pathlib.Path("data/input/" + pdf.filename)
    csv_path = pathlib.Path("data/input/" + mapping_csv.filename)
    prompt = """
    Hai due file:
    1) Un PDF che contiene una tabella di vulnerabilità (asset, vulnerability, description, severity).
    2) Un SCSV che mappa gli asset al team.

    Task:
    - Estrai la tabella vulnerabilità dal PDF.
    - Fai join per colonna asset con il CSV.
    - Restituisci SOLO un SCSV con colonne:
    asset;vulnerability;description;severity;squad; Azure Team ID;Product Owner
    
    Regole:
    - Fornisci solo il testo del CSV
    - una riga per vulnerabilità
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(
                data=pdf_path.read_bytes(),
                mime_type="application/pdf",
            ),
            types.Part.from_bytes(
                data=csv_path.read_bytes(),
                mime_type="text/csv",
            ),
            prompt,
        ],
    )
    #TODO: parametrize the file output to avoid overwrite
    save_text_to_file(response.text, "./data/output/", "result2.csv")
