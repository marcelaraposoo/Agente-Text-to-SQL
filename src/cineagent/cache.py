"""Cache simples em JSON para economizar a cota de 50 req/dia."""
import json
import re
import unicodedata
from pathlib import Path


def normalize(question: str) -> str:
    q = unicodedata.normalize("NFKD", question.lower())
    q = "".join(c for c in q if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", "", q).strip()


class AnswerCache:
    def __init__(self, path: str):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text("utf-8")) if self.path.exists() else {}

    def get(self, question: str):
        return self.data.get(normalize(question))

    def set(self, question: str, value: dict):
        self.data[normalize(question)] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
