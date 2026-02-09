from difflib import get_close_matches
from google.adk.tools.function_tool import FunctionTool
 
def enrich_vulnerabilities(vulnerabilities: list, mapping: list) -> list:
    """_summary_

    Args:
        vulnerabilities (list): _description_
        mapping (list): _description_

    Returns:
        list: _description_
    """
    def normalize(e: str) -> str:
        return e.lower().strip().rstrip("/")
 
    index = {normalize(m["endpoint"]): m for m in mapping}
    enriched = []
 
    for v in vulnerabilities:
        ep = normalize(v["endpoint"])
        match = index.get(ep)
 
        if not match:
            close = get_close_matches(ep, index.keys(), n=1, cutoff=0.8)
            if close:
                match = index[close[0]]
 
        enriched.append({
            **v,
            "asset": match["asset"] if match else "UNKNOWN",
            "team": match["team"] if match else "UNKNOWN"
        })
 
    return enriched
 
 
enrichment_tool = FunctionTool(enrich_vulnerabilities)