"""_summary_

    Returns:
        _type_: _description_
    """
import pdfplumber
from google.adk.tools.function_tool import FunctionTool
 
def extract_pdf_text(pdf_path: str) -> str:
    """_summary_

    Args:
        pdf_path (str): _description_

    Returns:
        str: _description_
    """
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

pdf_text_tool = FunctionTool(extract_pdf_text)

