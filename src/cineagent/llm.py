"""Cliente LLM (API compatível com OpenAI) com fallback entre provedores e modelos.

Importante: max_retries=0 — no OpenRouter cada request (mesmo falha) conta na cota diária,
então NÃO deixamos o SDK re-tentar sozinho.
"""
import time

from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError

from .config import Provider


TRANSIENT = {500, 502, 503, 504}
BACKOFF = (10,)  # 1 nova tentativa em erro temporário: cada tentativa conta na cota diária


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, providers: list[Provider]):
        if not providers:
            raise ValueError(
                "Nenhum provedor configurado. Defina GEMINI_API_KEY e/ou OPENROUTER_API_KEY no .env."
            )
        self.providers = providers
        self.clients = {
            p.name: OpenAI(api_key=p.api_key, base_url=p.base_url, max_retries=0, timeout=90)
            for p in providers
        }

    def chat(self, messages, tools=None):
        """Retorna (resposta, 'provedor/modelo'). Tenta cada modelo de cada provedor em ordem.

        Erros temporários (5xx, ex.: 503 "alta demanda") são re-tentados com pausa, exceto no
        OpenRouter, onde toda requisição (mesmo falha) consome a cota diária.
        """
        errors = []
        for p in self.providers:
            retries = 0 if p.name == "openrouter" else len(BACKOFF)
            auth_failed = False
            for model in p.models:
                label = f"{p.name}/{model}"
                for attempt in range(retries + 1):
                    try:
                        resp = self.clients[p.name].chat.completions.create(
                            model=model, messages=messages, tools=tools, temperature=0
                        )
                        if not resp.choices:
                            errors.append(f"{label}: resposta vazia")
                            break
                        return resp, label
                    except APIStatusError as e:
                        if e.status_code in TRANSIENT and attempt < retries:
                            time.sleep(BACKOFF[attempt])
                            continue
                        detalhe = " ".join(str(e.message).split())[:300]
                        errors.append(f"{label}: HTTP {e.status_code} - {detalhe}")
                        auth_failed = e.status_code in (401, 403)
                        break
                    except (APIConnectionError, APITimeoutError) as e:
                        errors.append(f"{label}: {type(e).__name__}")
                        break
                if auth_failed:
                    break  # chave inválida: não adianta outro modelo do mesmo provedor
        raise LLMUnavailable("Todos os modelos falharam -> " + " | ".join(errors))
