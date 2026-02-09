"""This is tools.py file"""
import os
import re
import itertools
import pandas as pd
import pdfplumber
from typing import List, Dict, Any, Optional

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




def _normalize_space_and_chars(s: str) -> str:
    """
    Normalizza stringhe per confronti robusti:
    - sostituisce NBSP e simili con spazio standard,
    - rimuove caratteri non stampabili,
    - collassa spazi multipli in uno,
    - trim,
    - casefold (case-insensitive robusto).
    """
    if s is None:
        return ""
    # NBSP e affini → spazio
    s = s.replace("\u00A0", " ").replace("\u2007", " ").replace("\u202F", " ")
    # rimuovi caratteri di controllo (eccetto newline, che poi collassiamo)
    s = re.sub(r"[^\x20-\x7E\n]+", " ", s)
    # collassa whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def _tokenize(s: str) -> List[str]:
    s = _normalize_space_and_chars(s)
    # tieni solo lettere/numeri/spazi
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.split() if s else []


def _jaccard_similarity(a_tokens: List[str], b_tokens: List[str]) -> float:
    a, b = set(a_tokens), set(b_tokens)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _page_matches_title(lines: List[str],
                        target_title: str,
                        allow_partial: bool = True,
                        min_token_coverage: float = 0.8,
                        jaccard_threshold: float = 0.6) -> bool:
    """
    Ritorna True se la pagina contiene il titolo (con diverse tolleranze):
    - match esatto normalizzato su una riga,
    - match parziale (contains) se allow_partial=True,
    - match su due righe adiacenti concatenate (titolo spezzato),
    - Jaccard similarity su token come ultima ratio.
    """
    target_norm = _normalize_space_and_chars(target_title)
    target_tokens = _tokenize(target_title)

    # 1) match riga per riga
    norm_lines = [_normalize_space_and_chars(l) for l in lines]
    if any(l == target_norm for l in norm_lines):
        return True

    # 2) contains (parziale)
    if allow_partial:
        # copertura token: almeno min_token_coverage dei token target devono apparire nell'insieme della riga
        for l in norm_lines:
            if target_norm in l:
                return True
            # coverage su token
            l_tokens = set(_tokenize(l))
            if l_tokens:
                covered = sum(1 for t in set(target_tokens) if t in l_tokens) / max(1, len(set(target_tokens)))
                if covered >= min_token_coverage:
                    return True

    # 3) titolo spezzato su 2 righe: concatena righe adiacenti
    for i in range(len(norm_lines) - 1):
        joined = _normalize_space_and_chars(norm_lines[i] + " " + norm_lines[i + 1])
        if joined == target_norm:
            return True
        if allow_partial and (target_norm in joined):
            return True
        # coverage token
        j_tokens = set(_tokenize(joined))
        if allow_partial and j_tokens:
            covered = sum(1 for t in set(target_tokens) if t in j_tokens) / max(1, len(set(target_tokens)))
            if covered >= min_token_coverage:
                return True

    # 4) Jaccard similarity su tutta la pagina (tutti i tokens)
    page_tokens = set()
    for l in norm_lines:
        page_tokens.update(_tokenize(l))
    if _jaccard_similarity(target_tokens, list(page_tokens)) >= jaccard_threshold:
        return True

    return False


def extract_pdf_table_by_title(
    pdf_path: str,
    title: str = "ndings below are leftovers from previous tests and were automatically pulled for the current test",
    flavor: str = "lattice",  # "lattice" o "stream"
    required_columns: Optional[List[str]] = None,  # es. ["Severity", "Assets", "Description"]
    allow_partial_title: bool = True,            # consente match parziale/robusto
    min_token_coverage: float = 0.8,             # % token del titolo che devono apparire
    jaccard_threshold: float = 0.6               # soglia similarità token su pagina
) -> List[Dict[str, Any]]:
    """
    Estrae UNA SINGOLA tabella dalla pagina che contiene (robustamente) il titolo passato.
    - Match titolo: tollerante a spazi speciali, spezzature di riga, contenuti parziali.
    - Estrattori: Camelot (se disponibile) → fallback a pdfplumber.
    - Se 'required_columns' è fornito, filtra e ordina tali colonne (aggiunge vuote se mancanti).
    """

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # 1) Trova la pagina con il titolo (con tolleranza)
    page_index_with_title: Optional[int] = None
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # rimuovi hyphenation a capo (es. "lega-\ncy" -> "legacy")
            text = re.sub(r"-\s*\n\s*", "", text)
            lines = text.splitlines()
            if _page_matches_title(
                lines,
                target_title=title,
                allow_partial=allow_partial_title,
                min_token_coverage=min_token_coverage,
                jaccard_threshold=jaccard_threshold
            ):
                page_index_with_title = i
                break

    if page_index_with_title is None:
        raise ValueError(f"Title '{title}' not found in PDF (even with tolerant matching).")

    page_num_for_camelot = page_index_with_title + 1  # Camelot usa 1-based

    # 2) Prova Camelot su quella pagina
    table_records: Optional[List[Dict[str, Any]]] = None

    if _CAM_AVAILABLE and not os.environ.get("FORCE_PDFPLUMBER"):
        try:
            tables = camelot.read_pdf(pdf_path, pages=str(page_num_for_camelot), flavor=flavor)
            for t in tables:
                df = t.df.copy()
                if df.shape[0] > 1:
                    header = df.iloc[0].astype(str).str.strip().tolist()
                    data = df.iloc[1:].copy()
                    data.columns = header
                    data = data.applymap(lambda v: re.sub(r"\s*\n\s*", " ", str(v)).strip())
                    table_records = data.to_dict(orient="records")
                    break  # prima tabella valida
        except Exception:
            pass  # fallback a pdfplumber

    # 3) Fallback: pdfplumber sulla stessa pagina
    if table_records is None:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_index_with_title]
            extracted = page.extract_tables() or []
            for tbl in extracted:
                if not tbl or len(tbl) < 2:
                    continue
                header = tbl[0]
                rows = tbl[1:]
                # Header normalizzati e unici
                norm_header = []
                seen = set()
                for i, h in enumerate(header):
                    name = (h or "").strip()
                    if name == "":
                        name = f"col_{i}"
                    while name in seen:
                        name = f"{name}_dup"
                    seen.add(name)
                    norm_header.append(name)
                # Records puliti
                records = []
                for r in rows:
                    rec = {}
                    for col, val in zip(norm_header, r):
                        v = "" if val is None else re.sub(r"\s*\n\s*", " ", str(val)).strip()
                        rec[col] = v
                    records.append(rec)
                table_records = records
                #break  # prima tabella valida

    if table_records is None:
        raise ValueError(
            f"No tables detected on the page containing the title '{title}'."
        )

    # 4) (Opzionale) Filtra colonne richieste
    if required_columns:
        def norm(s: str) -> str:
            return _normalize_space_and_chars(s)

        existing_cols = list(table_records[0].keys()) if table_records else []

        def map_column(existing_cols, req_col):
            req_norm = norm(req_col)
            # match esatto normalizzato
            for c in existing_cols:
                if norm(c) == req_norm:
                    return c
            # fallback: contenimento (asset vs assets)
            for c in existing_cols:
                if req_norm in norm(c) or norm(c) in req_norm:
                    return c
            return None

        col_map = {rc: map_column(existing_cols, rc) for rc in required_columns}

        filtered_records = []
        for rec in table_records:
            filtered = {}
            for rc in required_columns:
                src = col_map.get(rc)
                filtered[rc] = rec.get(src, "") if src else ""
            filtered_records.append(filtered)

        table_records = filtered_records

    return table_records



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
