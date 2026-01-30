import os
from google.adk.agents import Agent
from .tools import (
    load_parameter_table,
    extract_pdf_tables,
    combine_and_match,
    save_csv_output
)

def _load_prompt() -> str:
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "prompt.md"), "r", encoding="utf-8") as f:
        return f.read()

processor_agent = Agent(
    name="pdf_parameter_agent",
    description="Merges parameter table with two PDF tables and saves CSV",
    model="gemini-2.5-flash",
    instruction=_load_prompt(),
    tools=[
        load_parameter_table,
        extract_pdf_tables,
        combine_and_match,
        save_csv_output
    ],
)
