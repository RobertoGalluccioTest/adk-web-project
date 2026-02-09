from google.adk.agents import Agent
from agents.tools.csv_loader import csv_mapping_tool
from agents.tools.enricher import enrichment_tool
from agents.tools.exporter import csv_export_tool
from agents.tools.pdf_parser import pdf_text_tool


pentest_agent = Agent(
    name="vulnerability_agent",
    model="gemini-2.5-flash",
    instruction="""
You are a cybersecurity automation agent.
 
Workflow:
1. Use extract_pdf_text to read the penetration test PDF.
2. From the extracted text, identify ALL vulnerability table rows.
3. Convert them into a JSON array with fields:
   - id_vulnerability
   - endpoint
   - severity
   - descrizione
4. Load the CSV endpoint mapping.
5. Enrich vulnerabilities with asset and team.
6. Export the final CSV.
 
Rules:
- Return ONLY valid JSON when producing structured data.
- Do NOT invent vulnerabilities.
- If an endpoint cannot be mapped, mark asset and team as UNKNOWN.
""",
    tools=[
        pdf_text_tool,
        csv_mapping_tool,
        enrichment_tool,
        csv_export_tool
    ]
)
