import pandas as pd
from google.adk.tools.function_tool import FunctionTool

def export_csv(data: list, output_path: str) -> str:
    """_summary_

    Args:
        data (list): _description_
        output_path (str): _description_

    Returns:
        str: _description_
    """
    pd.DataFrame(data).to_csv(output_path, index=False)
    return output_path
 
csv_export_tool = FunctionTool(export_csv)
