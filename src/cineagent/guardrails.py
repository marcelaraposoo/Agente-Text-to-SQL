"""Validação do SQL gerado pelo LLM (somente leitura)."""
import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|truncate)\b",
    re.IGNORECASE,
)


class UnsafeSQLError(ValueError):
    pass


def validate_sql(sql: str, max_rows: int = 500) -> str:
    """Retorna o SQL limpo (com LIMIT de segurança) ou levanta UnsafeSQLError."""
    if not sql or not sql.strip():
        raise UnsafeSQLError("SQL vazio.")
    cleaned = re.sub(r"--.*?$|/\*.*?\*/", "", sql, flags=re.DOTALL | re.MULTILINE).strip()
    cleaned = cleaned.rstrip(";").strip()
    if ";" in cleaned:
        raise UnsafeSQLError("Apenas uma instrução SQL por vez é permitida.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise UnsafeSQLError("Apenas consultas SELECT são permitidas.")
    if FORBIDDEN.search(cleaned):
        raise UnsafeSQLError("A consulta contém comandos não permitidos (somente leitura).")
    if not re.search(r"\blimit\s+\d+\s*$", cleaned, re.IGNORECASE):
        cleaned = f"SELECT * FROM ({cleaned}) LIMIT {max_rows}"
    return cleaned
