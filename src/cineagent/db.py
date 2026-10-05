"""Acesso somente-leitura ao SQLite + introspecção do schema."""
import sqlite3
from pathlib import Path

# Colunas categóricas: o agente precisa saber os valores exatos para filtrar.
CATEGORICAL = {
    "dim_movies": ["status_filme"],
    "dim_people": ["tipo_pessoa"],
    "dim_genres": ["nome_genero"],
}
SKIP_TABLES = ("alembic_version", "sqlite_")


def _check_exists(db_path: str) -> None:
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"Banco '{db_path}' não encontrado. Coloque o cinerocket.db na pasta onde você "
            f"roda o comando (raiz do projeto) ou ajuste DB_PATH no .env."
        )


def connect_readonly(db_path: str) -> sqlite3.Connection:
    _check_exists(db_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    # Ajustes de desempenho (leitura apenas); precisam vir ANTES do authorizer, que bloqueia PRAGMA.
    conn.execute("PRAGMA temp_store=MEMORY")       # GROUP BY/ORDER BY grandes sem gravar temp em disco
    conn.execute("PRAGMA cache_size=-262144")      # ~256 MB de cache de páginas
    conn.execute("PRAGMA mmap_size=1073741824")    # leitura por memory-map (ajuda no Windows/OneDrive)
    conn.set_authorizer(_authorizer)  # 2ª camada: só permite leitura
    return conn


def _authorizer(action, arg1, arg2, db_name, source):
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
               sqlite3.SQLITE_RECURSIVE}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def _fmt(col: str, v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, str):
        if col.startswith("sk_"):
            return repr(v[:8] + "…")      # hashes de 64 chars gastam tokens à toa
        return repr(v if len(v) <= 40 else v[:40] + "…")
    return repr(v)


def describe_schema(db_path: str, sample_rows: int = 2) -> str:
    """Tabelas, colunas, FKs, valores categóricos e poucas linhas de exemplo (compactas)."""
    _check_exists(db_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    parts = []
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        if not r[0].startswith(SKIP_TABLES)]
    for t in tables:
        cols = conn.execute(f'PRAGMA table_info("{t}")').fetchall()
        names = [c[1] for c in cols]
        count = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        col_txt = ", ".join(f"{c[1]} {c[2]}{' PK' if c[5] else ''}" for c in cols)
        fks = conn.execute(f'PRAGMA foreign_key_list("{t}")').fetchall()
        fk_txt = "; ".join(f"{f[3]} -> {f[2]}.{f[4]}" for f in fks)
        block = f"TABELA {t} ({count} linhas)\n  colunas: {col_txt}"
        if fk_txt:
            block += f"\n  fks: {fk_txt}"
        for col in CATEGORICAL.get(t, []):
            vals = [r[0] for r in conn.execute(
                f'SELECT DISTINCT "{col}" FROM "{t}" WHERE "{col}" IS NOT NULL ORDER BY 1 LIMIT 30')]
            block += f"\n  valores de {col}: {vals}"
        for r in conn.execute(f'SELECT * FROM "{t}" LIMIT {sample_rows}').fetchall():
            block += "\n  ex: (" + ", ".join(_fmt(n, v) for n, v in zip(names, r)) + ")"
        parts.append(block)
    conn.close()
    return "\n\n".join(parts)
