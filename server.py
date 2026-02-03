"""This is FastAPI app: server.py
"""
import os
import uuid
import logging
import inspect
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from google.adk.agents import RunConfig
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from agents.pdf_parameter_agent.agent import processor_agent

# -----------------------------------------------------------------------------
# (Opzionale) Carica le variabili da .env (GOOGLE_API_KEY, GOOGLE_CLOUD_PROJECT)
# -----------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as ex:
    pass

# -----------------------------------------------------------------------------
# Web App FastAPI
# -----------------------------------------------------------------------------
# Crea l'app FastAPI preconfigurata da ADK
app: FastAPI = get_fast_api_app(
    agents_dir="./agents/pdf_parameter_agent", # Cartella contenente i tuoi agenti
    web=True # Abilita anche la Web UI di debug
)
# Crea un servizio per la gestione delle sessini (InMemory perchè in locale)
session_service = InMemorySessionService()

# Logging config
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

# Constants for Message Keys
SUPPORTED_MSG_KEYS = ("message", "input", "prompt", "text", "query", "content")


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
    """StartUp. logging some info.
    """
    logger.info("🟢 Server FastAPI avviato e pronto!")
    logger.info("🌍 Endpoint: http://localhost:8000/run-agent")
    logger.info("📁 Input directory: %s", os.path.abspath(DATA_INPUT_DIR))
    logger.info("📁 Output directory: %s", os.path.abspath(DATA_OUTPUT_DIR))

@app.get("/ping")
async def ping():
    """Ping API to verify webserver healthy state

    Returns:
        dict: status ok, whether the Webserver is up and runnning.
    """
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
    data: Dict[str, Any] = {
            "id": getattr(ev, "id", None),
            "author": getattr(ev, "author", None),
            "is_final_response": False,
            "function_calls": [],
            "function_responses": [],
            "content": None,
            "text": None,
        }
    try:
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
    except Exception:
        return {"raw": str(ev)}
    return data


async def iter_runner_events(runner, user_id: str, session_id: str, message: str):
    """Esegue runner.run_async in modo compatibile con diverse versioni di google-adk.
    Ordine dei tentativi:
      1) Passa il contenuto con uno tra: message/input/prompt/text/query/content, se supportato.
      2) Usa RunConfig tramite 'config' o 'run_config', se supportato.
      3) Pre-inietta (se runner espone metodi/servizi adatti), poi chiama run_async senza contenuto.
      4) Fallback: run_async(**kwargs base) o senza kwargs.
    """
    # 0) Firma di run_async
    try:
        sig = inspect.signature(runner.run_async)
        params = sig.parameters
        logger.info("runner.run_async signature: %s", sig)
    except Exception as ex:
        logger.warning("Impossibile ispezionare runner.run_async: %s", ex)
        params = {}

    # 1) user_id / session_id se supportati
    base_kwargs = {}
    if "user_id" in params:
        base_kwargs["user_id"] = user_id
    if "session_id" in params:
        base_kwargs["session_id"] = session_id

    # 2) Prova i nomi di parametro "messaggio"
    for key in SUPPORTED_MSG_KEYS:
        if key in params:
            try:
                logger.info("Invoco run_async con kwarg contenuto: %s", key)
                async for ev in runner.run_async(**base_kwargs, **{key: message}):
                    yield _event_to_dict(ev)
                return
            except TypeError as te:
                logger.warning("TypeError con '%s': %s. Provo altro nome...", key, te)
            except Exception as e:
                logger.exception("Errore run_async(%s=...): %s", key, e)
                raise

    # 3) Prova con RunConfig (config/run_config)
    #    Costruisco dinamicamente l'oggetto RunConfig con i campi supportati
    try:
        rc_sig = inspect.signature(RunConfig)
        rc_params = rc_sig.parameters
    except Exception:
        rc_params = {}
    config_kwargs = {}
    # user_id/session_id se previsti da RunConfig
    if "user_id" in rc_params:
        config_kwargs["user_id"] = user_id
    if "session_id" in rc_params:
        config_kwargs["session_id"] = session_id
    # campo di input messaggio in RunConfig (scegli il primo disponibile)
    for msg_key in SUPPORTED_MSG_KEYS:
        if msg_key in rc_params:
            config_kwargs[msg_key] = message
            break

    runconfig_obj = None
    if config_kwargs:
        try:
            runconfig_obj = RunConfig(**config_kwargs)
        except Exception as e:
            logger.warning("Creazione RunConfig(**%s) fallita: %s", config_kwargs, e)

    # 'config' o 'run_config' in run_async?
    for conf_name in ("config", "run_config"):
        if conf_name in params and runconfig_obj is not None:
            try:
                logger.info("Invoco run_async con %s=RunConfig(...)", conf_name)
                async for ev in runner.run_async(**base_kwargs, **{conf_name: runconfig_obj}):
                    yield _event_to_dict(ev)
                return
            except TypeError as te:
                logger.warning("TypeError con %s=RunConfig: %s. Provo fallback...", conf_name, te)
            except Exception as e:
                logger.exception("Errore run_async con %s: %s", conf_name, e)
                raise

    # 4) Pre-iniezione messaggio e run senza contenuto
    pre_injected = False
    try:
        if hasattr(runner, "add_user_message"):
            logger.info("Pre-inietto con runner.add_user_message(...)")
            await runner.add_user_message(user_id=user_id, session_id=session_id, message=message)
            pre_injected = True
        elif hasattr(runner, "add_user_event"):
            logger.info("Pre-inietto con runner.add_user_event(...)")
            await runner.add_user_event(user_id=user_id, session_id=session_id, message=message)
            pre_injected = True
        elif hasattr(runner, "message_service"):
            ms = runner.message_service
            if hasattr(ms, "create_user_message"):
                logger.info("Pre-inietto con message_service.create_user_message(...)")
                await ms.create_user_message(user_id=user_id,
                                             session_id=session_id,
                                             message=message)
                pre_injected = True
            elif hasattr(ms, "append"):
                logger.info("Pre-inietto con message_service.append(...)")
                await ms.append(user_id=user_id,
                                session_id=session_id,
                                role="user",
                                content=message)
                pre_injected = True
    except Exception as e:
        logger.warning("Pre-iniezione fallita (procedo comunque): %s", e)

    # 5) run_async senza contenuto
    try:
        if pre_injected:
            logger.info("Chiamo run_async senza contenuto (messaggio pre-iniettato).")
        else:
            logger.info("Chiamo run_async senza contenuto (nessun parametro messaggio supportato).")

        async for ev in runner.run_async(**base_kwargs):
            yield _event_to_dict(ev)
        return
    except TypeError as te:
        logger.warning("TypeError run_async(**base_kwargs): %s. Ritento senza kwargs.", te)
        async for ev in runner.run_async():
            yield _event_to_dict(ev)



# -----------------------------------------------------------------------------
# Endpoint principale: esegue l'agente ADK
# -----------------------------------------------------------------------------
@app.post("/run-agent")
async def run_agent(params_file: UploadFile = File(...),
                    pdf_file: UploadFile = File(...),
                    key: str = Form(default="")):
    """Run the Agent passing the right set of parameters

    Args:
        params_file (UploadFile, optional): _description_. Defaults to File(...).
        pdf_file (UploadFile, optional): _description_. Defaults to File(...).
        key (str, optional): _description_. Defaults to Form(default="").

    Raises:
        HTTPException: _description_
        HTTPException: _description_
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
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

    params_path_n = params_path.replace("\\", "/")
    pdf_path_n = pdf_path.replace("\\", "/")
    job_output_dir_n = job_output_dir.replace("\\", "/")

    try:
        csv_bytes = await params_file.read()
        pdf_bytes = await pdf_file.read()
        content_csv = csv_bytes.decode("utf-8")     # OK
        content_pdf = pdf_bytes                     # PDF → binario
        with open(params_path, "wb") as f:
            f.write(csv_bytes)
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
    finally:
        await params_file.close()
        await pdf_file.close()
    logger.info("💾 Salvati: %s | %s", params_path_n, pdf_path_n)
    logger.info("📂 Output previsto: %s", job_output_dir_n)

    # --- 3) Prompt di tasking per l'agente -----------------------------------
    message = (
        "Fondi la tabella parametri con le due tabelle del PDF e salva un CSV.\n"
        f"- load_parameter_table(params_path_n='{params_path_n}')\n"
        f"- extract_pdf_tables(pdf_path_n='{pdf_path_n}')\n"
        f"- combine_and_match(...)\n"
        f"- save_csv_output(output_dir='{job_output_dir_n}')\n"
        f"Chiave opzionale: '{key}'."
    )
    logger.info("Message: %s", message)
    try:
       # Avvia una sessione e passa i contenuti nello 'state'
        session = await session_service.create_session(
            app_name="FileApp",
            user_id="web",
            state={"file1_data": content_csv, "file2_data": content_pdf}
        )
        runner = Runner(agent=processor_agent, app_name="FileApp", session_service=session_service)
        content = types.Content(role='user', parts=[types.Part(text=message)])
        # Esegui l'agente
        response_text = ""
        events = runner.run_async(session_id=session.id, user_id="web", new_message=content)
        async for eve in events:
            if eve.is_final_response():
                #if eve.content and eve.content.parts:
                response_text = eve.content.parts[0].text

        return {"response": response_text}
    except Exception as e:
        logger.exception("❌ Errore durante l'esecuzione dell'agente ADK (Runner)")
        raise HTTPException(status_code=500, detail=f"Errore agente:{e}") from e



    # # --- 5) Elenco dei file prodotti -----------------------------------------
    # produced_files=[]
    # for root, _, files in os.walk(job_output_dir_n):
    #     for name in files:
    #         produced_files.append(os.path.relpath(os.path.join(root, name), job_output_dir_n))

    # # --- 6) Estrazione testo finale ------------------------------------------
    # final_text = None
    # for ev in reversed(events):
    #     if ev.get("is_final_response"):
    #         final_text = ev.get("text") or ev.get("content")
    #         break

    # # --- 7) Risposta ----------------------------------------------------------
    # payload: Dict[str, Any] = {
    #     "job_id": job_id,
    #     "input": {"params_path_n": params_path_n, "pdf_path_n": pdf_path_n},
    #     "output_dir": job_output_dir_n,
    #     "produced_files": produced_files,
    #     "final_text": final_text,
    #     "events": events[-50:]  # limito la risposta
    # }
    # return JSONResponse(content=payload, status_code=200)
    