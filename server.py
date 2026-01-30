from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from agents.pdf_parameter_agent.agent import processor_agent

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI
app = FastAPI(title="ADK Web Project – PDF Agent")

# CORS: serve per usare il frontend aperto come file://
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Input/output directories
DATA_INPUT_DIR = "data/input"
DATA_OUTPUT_DIR = "data/output"
os.makedirs(DATA_INPUT_DIR, exist_ok=True)
os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)

@app.post("/run-agent")
async def run_agent(
        params_file: UploadFile = File(...),
        pdf_file: UploadFile = File(...),
        key: str = Form(default="")
):
    logger.info(f"Ricevuti file: {params_file.filename}, {pdf_file.filename}, key={key}")

    params_path = os.path.join(DATA_INPUT_DIR, params_file.filename)
    pdf_path = os.path.join(DATA_INPUT_DIR, pdf_file.filename)

    # Save uploaded files
    with open(params_path, "wb") as f:
        f.write(await params_file.read())

    with open(pdf_path, "wb") as f:
        f.write(await pdf_file.read())

    # Build agent prompt
    query = f"""
    Load parameter table from: {params_path}
    Load PDF from: {pdf_path}
    Extract exactly two tables.
    Combine & match data (key="{key}" if provided).
    Save output CSV to: {DATA_OUTPUT_DIR}/result.csv
    """

    # Run the agent
    result = processor_agent.run(query)
    logger.info(f"Risultato agente: {result}")

    return JSONResponse(content={"result": result})