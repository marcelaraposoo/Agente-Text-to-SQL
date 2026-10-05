import json
import sqlite3
import time
from dataclasses import dataclass, field

from .cache import AnswerCache
from .config import Settings
from .db import connect_readonly, describe_schema
from .guardrails import UnsafeSQLError, validate_sql
from .llm import LLMClient
from .prompts import SYSTEM_PROMPT, TOOLS


@dataclass
class Answer:
    text: str
    queries: list[str] = field(default_factory=list)
    last_rows: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    model: str = ""
    cached: bool = False


class CineAgent:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()
        self.llm = LLMClient(self.s.providers)
        self.conn = connect_readonly(self.s.db_path)
        self.system = SYSTEM_PROMPT.format(schema=describe_schema(self.s.db_path))
        self.cache = AnswerCache(self.s.cache_path)
        self.history: list[dict] = []  # memória de conversa (texto apenas)

    # ---- ferramenta ----
    def run_sql(self, query: str) -> dict:
        deadline = time.monotonic() + self.s.query_timeout
        try:
            safe = validate_sql(query, self.s.max_rows_query)
            # interrompe a consulta se passar do tempo (handler chamado a cada ~100 mil operações da VM do SQLite)
            self.conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 100000)
            cur = self.conn.execute(safe)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            return {"columns": cols, "rows": rows, "row_count": len(rows)}
        except UnsafeSQLError as e:
            return {"error": str(e)}
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e).lower():
                return {"error": f"A consulta demorou mais de {self.s.query_timeout}s e foi interrompida. "
                                 "Reescreva de forma mais leve: filtre primeiro em uma CTE (ex.: filmes do período, "
                                 "só atores, só diretores) antes de juntar as pontes, e evite COUNT(DISTINCT) quando "
                                 "a chave já é única."}
            return {"error": str(e)}
        except sqlite3.Error as e:
            return {"error": str(e)}
        finally:
            self.conn.set_progress_handler(None, 0)

    # ---- loop principal ----
    def ask(self, question: str, use_cache: bool = True) -> Answer:
        if use_cache and not self.history:
            hit = self.cache.get(question)
            if hit:
                return Answer(**{**hit, "cached": True})

        messages = [{"role": "system", "content": self.system}, *self.history,
                    {"role": "user", "content": question}]
        ans = Answer(text="")

        for _ in range(self.s.max_steps):
            resp, model = self.llm.chat(messages, tools=TOOLS)
            ans.model = model
            msg = resp.choices[0].message
            if not msg.tool_calls:
                ans.text = msg.content or ""
                break
            messages.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                try:
                    query = json.loads(call.function.arguments).get("query", "")
                except json.JSONDecodeError:
                    query = ""
                result = self.run_sql(query)
                ans.queries.append(query)
                if "error" not in result:
                    ans.columns, ans.last_rows = result["columns"], result["rows"]
                payload = dict(result)
                if "rows" in payload:
                    payload["rows"] = payload["rows"][: self.s.max_rows_to_llm]
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(payload, ensure_ascii=False, default=str)})
        else:
            ans.text = "Não consegui chegar a uma resposta dentro do limite de tentativas. Tente reformular a pergunta."

        self.history += [{"role": "user", "content": question},
                         {"role": "assistant", "content": ans.text}]
        self.history = self.history[-6:]  # últimas 3 trocas
        if use_cache and len(self.history) == 2 and ans.queries:
            self.cache.set(question, {"text": ans.text, "queries": ans.queries, "model": ans.model,
                                      "columns": ans.columns,
                                      "last_rows": [list(r) for r in ans.last_rows[:100]]})
        return ans
