import pandas as pd
from google.adk.tools.function_tool import FunctionTool

def load_mapping_csv(csv_path: str) -> list[dict]:
    """
    Load endpoint to asset/team mapping from CSV.
    """
    df = pd.read_csv(csv_path)
    return df.to_dict(orient="records")
 
 
csv_mapping_tool = FunctionTool(load_mapping_csv)