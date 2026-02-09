import tempfile
import os
import pathlib
from fastapi import FastAPI, UploadFile, File
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.cli.fast_api import get_fast_api_app
from google.genai import types
from agents.agent import pentest_agent
from google import genai



app: FastAPI = get_fast_api_app(
    agents_dir="./agents/agents", # Cartella contenente i tuoi agenti
    web=True # Abilita anche la Web UI di debug
)
session_service = InMemorySessionService()


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
    2) Un CSV che mappa gli asset al team.

    Task:
    - Estrai la tabella vulnerabilità dal PDF.
    - Fai join per colonna asset con il CSV.
    - Restituisci SOLO un CSV con colonne:
    asset,vulnerability,description,severity,team
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

    print(response.text)
