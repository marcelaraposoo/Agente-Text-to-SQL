"""Compara o resultado do SQL do agente com o resultado do reference_sql.

Uso:
  python evals/run_evals.py                 # todas as perguntas
  python evals/run_evals.py --ids 1,2,3     # só algumas
  python evals/run_evals.py --pendentes     # só as que ainda não passaram (ou deram erro de API)

Por padrão cada pergunta gasta 1 request (só o SQL; --resposta-completa gasta 2). Passa se alguma coluna do resultado do agente reproduz,
na mesma ordem, os valores da 1ª coluna do reference_sql (top-5 ou menos): tolera colunas
extras, aliases e LIMIT diferentes. Erros de API (ex.: 503) NÃO derrubam o lote: a pergunta
fica marcada como 'erro_api' e pode ser repetida com --pendentes.
Os resultados ficam em evals/results.json (úteis para o README).
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cineagent.agent import CineAgent  # noqa: E402
from cineagent.config import Settings  # noqa: E402
from cineagent.llm import LLMUnavailable  # noqa: E402

RESULTS = Path(__file__).with_name("results.json")


def _n(v):
    return round(v, 2) if isinstance(v, float) else v


def matches(ref_rows, got_rows, k: int = 5) -> bool:
    if not ref_rows or not got_rows:
        return False
    ref_col = [_n(r[0]) for r in ref_rows[:k]]
    n = min(len(ref_col), len(got_rows))
    for j in range(len(got_rows[0])):
        if [_n(r[j]) for r in got_rows[:n]] == ref_col[:n]:
            return True
    return False


def _close(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 0.011
    return a == b


def matches_free(ref_rows, got_rows) -> bool:
    """Para perguntas sem ordem definida: compara o MAPA chave -> valor, ignorando a ordem das linhas.
    A chave é a 1ª coluna do reference_sql e o valor, a 2ª (se existir)."""
    if not ref_rows or not got_rows:
        return False
    ref = {_n(r[0]): (_n(r[1]) if len(r) > 1 else None) for r in ref_rows}
    for j in range(len(got_rows[0])):
        if {_n(r[j]) for r in got_rows} != set(ref):
            continue
        if len(ref_rows[0]) < 2:
            return True
        for k in range(len(got_rows[0])):
            if k != j:
                got = {_n(r[j]): _n(r[k]) for r in got_rows}
                if all(_close(got[key], ref[key]) for key in ref):
                    return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--pendentes", action="store_true", help="só perguntas que ainda não passaram")
    ap.add_argument("--pausa", type=float, default=13.0,
                    help="segundos entre perguntas (o plano gratuito permite ~5 req/min)")
    ap.add_argument("--resposta-completa", action="store_true",
                    help="gasta a 2ª chamada para também redigir a resposta em texto")
    a = ap.parse_args()

    saved = json.loads(RESULTS.read_text("utf-8")) if RESULTS.exists() else {}
    ids = {int(i) for i in a.ids.split(",") if i}
    qs = json.loads(Path(__file__).with_name("questions.json").read_text("utf-8"))
    qs = [q for q in qs if q["reference_sql"] or q.get("esperado") == "recusa"]
    todas = qs
    if ids:
        qs = [q for q in qs if q["id"] in ids]
    if a.pendentes:
        qs = [q for q in qs if saved.get(str(q["id"]), {}).get("status") != "ok"]

    s = Settings()
    agent = CineAgent(s)
    ref = sqlite3.connect(f"file:{s.db_path}?mode=ro", uri=True)

    erros_seguidos = 0
    for i, q in enumerate(qs):
        agent.history = []
        try:
            ans = agent.ask(q["pergunta"], use_cache=False, final_answer=a.resposta_completa)
        except LLMUnavailable as e:
            print(f"[{q['id']:>2}] ERRO API  {q['pergunta'][:55]}")
            print(f"      {' '.join(str(e).split())[:400]}")
            saved[str(q["id"])] = {"pergunta": q["pergunta"], "status": "erro_api"}
            RESULTS.write_text(json.dumps(saved, ensure_ascii=False, indent=2), "utf-8")
            erros_seguidos += 1
            if erros_seguidos >= 2:
                print("\nA API falhou 2 vezes seguidas: interrompendo para não gastar a cota. "
                      "Aguarde e rode de novo com --pendentes.")
                break
            time.sleep(a.pausa * 3)
            continue
        erros_seguidos = 0
        if q.get("esperado") == "recusa":
            passed = not ans.queries or not ans.last_rows
        else:
            ref_rows = ref.execute(q["reference_sql"]).fetchall()
            check = matches_free if q.get("ordem") == "livre" else matches
            passed = check(ref_rows, ans.last_rows)
        print(f"[{q['id']:>2}] {'OK    ' if passed else 'FALHOU'}  {q['pergunta'][:55]}  ({ans.model})")
        if not passed and ans.queries:
            print("      SQL do agente:", ans.queries[-1][:300].replace("\n", " "))
        saved[str(q["id"])] = {
            "pergunta": q["pergunta"], "status": "ok" if passed else "falhou", "modelo": ans.model,
            "sql": ans.queries[-1] if ans.queries else "", "resposta": ans.text,
            "amostra": [[str(v) for v in r] for r in ans.last_rows[:3]],
        }
        RESULTS.write_text(json.dumps(saved, ensure_ascii=False, indent=2), "utf-8")
        if i < len(qs) - 1:
            time.sleep(a.pausa)

    status = [saved.get(str(q["id"]), {}).get("status") for q in todas]
    print(f"\nAcumulado: {status.count('ok')}/{len(todas)} ok | {status.count('falhou')} falharam | "
          f"{status.count('erro_api')} com erro de API | {status.count(None)} ainda não rodaram")
    print(f"Detalhes em {RESULTS}")


if __name__ == "__main__":
    main()
