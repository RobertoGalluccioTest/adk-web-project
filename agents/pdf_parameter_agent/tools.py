"""This is tools.py file"""
import os
import itertools
import pandas as pd
import pdfplumber


# Camelot is optional and can fail on some PDFs; we try it first if available
try:
    import camelot
    _CAM_AVAILABLE = True
except Exception:
    _CAM_AVAILABLE = False

def load_parameter_table(file_path: str):
    """
    Load the parameter table (.csv or .xlsx). Expected: 3 columns.
    Returns: list[dict]
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Parameter file not found: {file_path}")

    if file_path.lower().endswith(".csv"):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path, engine="openpyxl")

    # Optional: simple validation for 3 columns
    if df.shape[1] != 3:
        # Not hard failing, but warning via extra field
        df.attrs["warning"] = "Expected 3 columns; proceeding anyway."

    return df.to_dict(orient="records")


def extract_pdf_tables(pdf_path: str, table_indexes: list | None = None):
    """
    Extract exactly two tables from a PDF.
    Returns dict {"table1": list[dict], "table2": list[dict]}.

    Heuristic:
    - Try Camelot with flavor="lattice" (best on properly bordered tables).
    - Fallback to pdfplumber.
    - If multiple tables are detected, pick first two or by provided indexes.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    tables_as_records = []

    # Try Camelot if available and not explicitly disabled
    if _CAM_AVAILABLE and not os.environ.get("FORCE_PDFPLUMBER"):
        try:
            tables = camelot.read_pdf(pdf_path, pages="1-end", flavor="lattice")
            for t in tables:
                # t.df is a DataFrame with row 0 as header
                df = t.df.copy()
                if df.shape[0] > 1:
                    header = df.iloc[0].tolist()
                    data = df.iloc[1:]
                    data.columns = header
                    recs = data.to_dict(orient="records")
                    tables_as_records.append(recs)
        except Exception:
            pass  # silently fallback

    # Fallback: pdfplumber
    if len(tables_as_records) < 2:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_tables()
                for tbl in extracted or []:
                    if not tbl or len(tbl) < 2:
                        continue
                    header = tbl[0]
                    rows = tbl[1:]
                    # Normalize header (deduplicate None, '')
                    header = [h if h not in (None, "") else f"col_{i}" for i,
                              h in enumerate(header)]
                    recs = [dict(zip(header, r)) for r in rows]
                    tables_as_records.append(recs)

    if not tables_as_records:
        raise ValueError("No tables detected in the PDF.")

    # Choose 2 tables
    if table_indexes and len(table_indexes) == 2:
        idx1, idx2 = table_indexes
    else:
        idx1, idx2 = 0, 1 if len(tables_as_records) > 1 else (0, 0)

    if idx1 == idx2 and len(tables_as_records) > 1:
        idx2 = 1  # ensure two distinct tables if possible

    try:
        t1 = tables_as_records[idx1]
        t2 = tables_as_records[idx2]
    except Exception as ex:
        raise ValueError("Could not select two tables from extracted results.") from ex

    return {"table1": t1, "table2": t2}


def combine_and_match(param_rows: list[dict],
                      table1_rows: list[dict],
                      table2_rows: list[dict],
                      key: str | None = None):
    """
    Deterministically merge:
    - Identify a join key:
        1) If key provided and present in param_rows columns -> use it.
        2) Else use the first common column name shared by param_rows 
        and table1_rows or table2_rows.
        3) Else fallback to the first column of param_rows.
    - Build merged rows: param + best match from t1 + best match from t2.
      Columns from t1 prefixed as 't1_' and from t2 as 't2_' to avoid collisions.
    Returns: list[dict]
    """
    def cols(rows):
        return set(itertools.chain.from_iterable(r.keys() for r in rows)) if rows else set()

    param_cols = cols(param_rows)
    t1_cols = cols(table1_rows)
    t2_cols = cols(table2_rows)

    join_key = None
    if key and key in param_cols:
        join_key = key
    else:
        common = (param_cols & t1_cols) or (param_cols & t2_cols)
        if common:
            join_key = sorted(common)[0]
        elif param_cols:
            join_key = sorted(param_cols)[0]

    # Index tables by join_key for quick lookup (exact match)
    def index_by(rows, k):
        idx = {}
        for r in rows:
            v = r.get(k)
            idx.setdefault(v, []).append(r)
        return idx

    t1_idx = index_by(table1_rows, join_key) if join_key else {}
    t2_idx = index_by(table2_rows, join_key) if join_key else {}

    merged = []
    for prow in param_rows:
        keyval = prow.get(join_key) if join_key else None
        t1_matches = t1_idx.get(keyval, [None])
        t2_matches = t2_idx.get(keyval, [None])

        # take cartesian product so we don't lose multi-matches
        for m1 in (t1_matches or [None]):
            for m2 in (t2_matches or [None]):
                rec = dict(prow)  # base
                if m1:
                    for k, v in m1.items():
                        rec[f"t1_{k}"] = v
                if m2:
                    for k, v in m2.items():
                        rec[f"t2_{k}"] = v
                merged.append(rec)

    return merged


def save_csv_output(records: list[dict], output_path: str = "data/output/result.csv"):
    """
    Save records to CSV.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False)
    return {"status": "success", "path": os.path.abspath(output_path)}
