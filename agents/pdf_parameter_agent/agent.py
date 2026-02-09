"""This is the Agent-py file which creates the agent as processor_agent"""
import os
from google.adk.agents import Agent
from .tools import (
    load_parameter_table,
    extract_pdf_table_by_title,
    combine_and_match,
    save_csv_output
)

def _load_prompt() -> str:
    """Load a prompt from a file.

    Returns:
        str: return the prompt text.
    """
    pwd = os.path.dirname(__file__)
    prompt_text = ""
    with open(os.path.join(pwd, "prompt.md"), "r", encoding="utf-8") as f:
        prompt_text = f.read()
    return prompt_text

# Create a processor_angent (this is a single agent app)
processor_agent = Agent(
    name="pdf_parameter_agent",
    description="Merges parameter table with two PDF tables and saves CSV",
    model="gemini-2.5-flash",
    instruction=_load_prompt(),
     tools=[
          load_parameter_table,
          extract_pdf_table_by_title,
          combine_and_match,
          save_csv_output
     ]
)
