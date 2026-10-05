import argparse
import sys

from .agent import CineAgent
from .config import Settings
from .db import describe_schema
from .llm import LLMUnavailable


def main():
    p = argparse.ArgumentParser(prog="cineagent", description="Agente Text-to-SQL da CineData")
    p.add_argument("question", nargs="?", help="Pergunta (omita para modo interativo)")
    p.add_argument("--schema", action="store_true", help="Imprime o schema do banco e sai (não usa API)")
    p.add_argument("--no-cache", action="store_true")
    a = p.parse_args()
    s = Settings()

    if a.schema:
        print(describe_schema(s.db_path)); return

    agent = CineAgent(s)

    def run(q):
        try:
            r = agent.ask(q, use_cache=not a.no_cache)
        except LLMUnavailable as e:
            print(f"[erro] {e}"); return
        tag = "(cache)" if r.cached else f"[{r.model}]"
        print(f"\n{r.text}\n{tag}\n")

    if a.question:
        run(a.question); return
    print("CineAgent — digite sua pergunta (ou 'sair').")
    while True:
        try:
            q = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"sair", "exit", "quit"}:
            break
        if q:
            run(q)


if __name__ == "__main__":
    sys.exit(main())
