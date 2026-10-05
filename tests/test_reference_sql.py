"""Executa os reference_sql no cinerocket.db real (sem usar a API). Pulado se o banco não existir."""
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "cinerocket.db"
QS = [q for q in json.loads((ROOT / "evals" / "questions.json").read_text("utf-8")) if q["reference_sql"]]


@pytest.mark.skipif(not DB.exists(), reason="cinerocket.db não encontrado")
@pytest.mark.parametrize("q", QS, ids=[str(q["id"]) for q in QS])
def test_reference_sql_runs(q):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(q["reference_sql"]).fetchall()
    assert rows, f"consulta {q['id']} não retornou linhas"
