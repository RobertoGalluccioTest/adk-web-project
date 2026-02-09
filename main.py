import tempfile
import os
from fastapi import FastAPI, UploadFile, File
from agents.agent import pentest_agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.cli.fast_api import get_fast_api_app
from google.genai import types




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
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, pdf.filename)
        csv_path = os.path.join(tmp, mapping_csv.filename)
        with open(pdf_path, "wb") as f:
            f.write(await pdf.read())
        with open(csv_path, "wb") as f:
            f.write(await mapping_csv.read())
        output_path = os.path.join(tmp, "output.csv")
        # await pentest_agent.run({
        #     "pdf_path": pdf_path,
        #     "mapping_csv": csv_path,
        #     "output_path": output_path
        # })
    session = await session_service.create_session(
        app_name="agents",
        user_id="web",
        state={"file1_data": pdf_path, "file2_data": csv_path}
    )
    runner = Runner(agent=pentest_agent, app_name="agents", session_service=session_service)
    content = types.Content(role='user', parts=[types.Part(text="")])
    # Esegui l'agente
    response_text = ""
    events = runner.run_async(session_id=session.id, user_id="web", new_message=content)
    async for eve in events:
        if eve.is_final_response():
            #if eve.content and eve.content.parts:
            response_text = eve.content.parts[0].text

    return {"response": response_text}