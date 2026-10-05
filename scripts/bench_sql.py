"""Mede o tempo de cada reference_sql com as configurações do projeto (sem API).
Uso: python scripts/bench_sql.py   (defina PYTHONPATH=src)"""
import json
import time
from pathlib import Path

from cineagent.config import Settings
from cineagent.db import connect_readonly

s = Settings()
conn = connect_readonly(s.db_path)
qs = json.loads((Path(__file__).resolve().parents[1] / "evals" / "questions.json").read_text("utf-8"))
for q in qs:
    if not q["reference_sql"]:
        continue
    t = time.time()
    n = len(conn.execute(q["reference_sql"]).fetchall())
    print(f"[{q['id']:>2}] {time.time() - t:6.1f}s  {n:>4} linhas  {q['pergunta'][:60]}")
