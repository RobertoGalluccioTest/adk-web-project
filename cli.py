import argparse
from agents.pdf_parameter_agent.agent import processor_agent

def main():
    parser = argparse.ArgumentParser(description="Run PDF parameter merge agent")
    parser.add_argument("--params", required=True, help="Path to parameter CSV/XLSX")
    parser.add_argument("--pdf", required=True, help="Path to PDF")
    parser.add_argument("--key", default="", help="Optional join key/column name")
    parser.add_argument("--output", default="data/output/result.csv", help="Output CSV path")
    args = parser.parse_args()

    query = f"""
Load parameter table from: {args.params}
Load PDF from: {args.pdf}
Extract exactly two tables.
Combine & match data (use key="{args.key}" if provided).
Save the output CSV to: {args.output}
"""

    resp = processor_agent.run(query)
    print(resp)

if __name__ == "__main__":
    main()