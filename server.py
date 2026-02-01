# server.py
import os
import uuid
import shutil
import logging
from typing import List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# ADK: Runner config e tuo agent
from google.adk.agents import RunConfig
from agents.pdf_parameter_agent.agent import processor_agent

from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.genai import types
# -----------------------------------------------------------------------------
# (Opzionale) Carica le variabili da .env (GOOGLE_API_KEY, GOOGLE_CLOUD_PROJECT)
# -----------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# -----------------------------------------------------------------------------
# App & Logging
# -----------------------------------------------------------------------------
app = FastAPI(title="ADK Web Project – PDF Agent")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Paths (statici e I/O)
# -----------------------------------------------------------------------------
WEB_DIR = "web"
DATA_INPUT_DIR = "data/input"
DATA_OUTPUT_DIR = "data/output"
os.makedirs(DATA_INPUT_DIR, exist_ok=True)
os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)

# Statici sotto /static (non montare su "/")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# -----------------------------------------------------------------------------
# Routes base
# -----------------------------------------------------------------------------
@app.get("/")
async def root():
    """Serve la home page (index.html) dalla cartella web/."""
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

# CORS (sviluppo: accetta tutto; in produzione limita i domini)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("🟢 Server FastAPI avviato e pronto!")
    logger.info("🌍 Endpoint: http://localhost:8000/run-agent")
    logger.info(f"📁 Input directory:  {os.path.abspath(DATA_INPUT_DIR)}")
    logger.info(f"📁 Output directory: {os.path.abspath(DATA_OUTPUT_DIR)}")

@app.get("/ping")
async def ping():
    return {"status": "ok"}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _event_to_dict(ev) -> Dict[str, Any]:
    """
    Serializza i campi utili degli Event ADK:
    - testo (se presente)
    - tool calls / tool responses
    - flag di 'final response'
    """
    try:
        data: Dict[str, Any] = {
            "id": getattr(ev, "id", None),
            "author": getattr(ev, "author", None),
            "is_final_response": False,
            "function_calls": [],
            "function_responses": [],
            "content": None,
            "text": None,
        }
        if hasattr(ev, "get_function_calls"):
            data["function_calls"] = ev.get_function_calls() or []
        if hasattr(ev, "get_function_responses"):
            data["function_responses"] = ev.get_function_responses() or []
        if hasattr(ev, "is_final_response"):
            data["is_final_response"] = bool(ev.is_final_response())

        content = getattr(ev, "content", None)
        # Se l'oggetto content ha .dict(), lo serializzo; altrimenti salvo raw
        data["content"] = getattr(content, "dict", lambda: content)() if content else None

        # Estraggo eventuale testo dal primo part
        try:
            parts = getattr(content, "parts", None)
            if parts and len(parts) and hasattr(parts[0], "text"):
                data["text"] = parts[0].text
        except Exception:
            pass

        return data
    except Exception:
        return {"raw": str(ev)}

# -----------------------------------------------------------------------------
# Endpoint principale: esegue l'agente ADK
# -----------------------------------------------------------------------------
@app.post("/run-agent")
async def run_agent(
        params_file: UploadFile = File(...),
        pdf_file: UploadFile = File(...),
        key: str = Form(default="")
):
    logger.info("▶️ run-agent: richiesta ricevuta")

    # --- 1) Validazioni -------------------------------------------------------
    # Accetta .csv o .json per i parametri (SE vuoi solo CSV:
    #   cambia la condizione in: if params_ext != ".csv": ... )
    params_ext = os.path.splitext(params_file.filename)[1].lower()
    if params_ext not in (".csv", ".json"):
        raise HTTPException(
            status_code=400,
            detail="Il file dei parametri deve essere .csv o .json"
        )
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Il documento deve essere un PDF (.pdf)")

    # --- 2) Salvataggio su disco con job_id ----------------------------------
    job_id = uuid.uuid4().hex[:8]
    job_input_dir = os.path.join(DATA_INPUT_DIR, job_id)
    job_output_dir = os.path.join(DATA_OUTPUT_DIR, job_id)
    os.makedirs(job_input_dir, exist_ok=True)
    os.makedirs(job_output_dir, exist_ok=True)

    params_path = os.path.join(job_input_dir, params_file.filename)
    pdf_path = os.path.join(job_input_dir, pdf_file.filename)

    try:
        with open(params_path, "wb") as f:
            shutil.copyfileobj(params_file.file, f)
        with open(pdf_path, "wb") as f:
            shutil.copyfileobj(pdf_file.file, f)
    finally:
        # chiude gli stream UploadFile per evitare file descriptor leak
        await params_file.close()
        await pdf_file.close()

    params_path_n = params_path.replace("\\", "/")
    pdf_path_n = pdf_path.replace("\\", "/")
    job_output_dir_n = job_output_dir.replace("\\", "/")

    logger.info(f"💾 Salvati: {params_path_n} | {pdf_path_n}")
    logger.info(f"📂 Output previsto: {job_output_dir_n}")

    # --- 3) Prompt di tasking per l'agente -----------------------------------
    message = (
        "Fondi la tabella parametri con le due tabelle del PDF e salva un CSV.\n"
        f"- load_parameter_table(params_path_n='{params_path_n}')\n"
        f"- extract_pdf_tables(pdf_path_n='{pdf_path_n}')\n"
        f"- combine_and_match(...)\n"
        f"- save_csv_output(output_dir='{job_output_dir_n}')\n"
        f"Chiave opzionale: '{key}'."
    )
    logger.info(f" message: {message}")

    # Runner “in-memory” per orchestrare l’esecuzione
    runner = InMemoryRunner(
        agent=processor_agent,
        session_service=InMemorySessionService(),
        artifact_service=InMemoryArtifactService(),
    )


    # --- 4) Esecuzione agente ADK (senza RunConfig) -----------------------------

    events: List[Dict[str, Any]] = []
    try:
        async for ev in runner.run_async(
                user_id="web",
                session_id=job_id,  # così colleghi input/output a questa invocazione
                message=message,    # <--- passa il messaggio qui
        ):
            events.append(_event_to_dict(ev))
    except Exception as e:
        logger.exception("❌ Errore durante l'esecuzione dell'agente ADK (Runner)")
        raise HTTPException(status_code=500, detail=f"Errore agente: {e}")

    # --- 5) Elenco dei file prodotti -----------------------------------------
    produced_files: List[str] = []
    for root, _, files in os.walk(job_output_dir_n):
        for name in files:
            produced_files.append(os.path.relpath(os.path.join(root, name), job_output_dir_n))

    # --- 6) Estrazione testo finale ------------------------------------------
    final_text = None
    for ev in reversed(events):
        if ev.get("is_final_response"):
            final_text = ev.get("text") or ev.get("content")
            break

    # --- 7) Risposta ----------------------------------------------------------
    payload: Dict[str, Any] = {
        "job_id": job_id,
        "input": {"params_path_n": params_path_n, "pdf_path_n": pdf_path_n},
        "output_dir": job_output_dir_n,
        "produced_files": produced_files,
        "final_text": final_text,
        "events": events[-50:],  # limito la risposta
    }
    return JSONResponse(content=payload, status_code=200)