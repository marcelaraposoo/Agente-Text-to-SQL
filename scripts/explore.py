"""Diagnóstico do cinerocket.db (NÃO usa API). Uso: python scripts/explore.py > diagnostico.txt"""
import os
import sqlite3
import sys

db = os.getenv("DB_PATH", "cinerocket.db")
if not os.path.exists(db):
    sys.exit(f"Banco '{db}' não encontrado.")
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def show(title, sql):
    print(f"\n## {title}")
    try:
        cur = c.execute(sql)
        print("   colunas:", [d[0] for d in cur.description])
        for r in cur.fetchall():
            print("  ", r)
    except sqlite3.Error as e:
        print("   ERRO:", e)


show("status_filme", "SELECT status_filme, COUNT(*) FROM dim_movies GROUP BY 1 ORDER BY 2 DESC")
show("tipo_pessoa", "SELECT tipo_pessoa, COUNT(*) FROM dim_people GROUP BY 1")
show("datas (todos / lançados <= hoje)",
     "SELECT MIN(data_lancamento), MAX(data_lancamento), "
     "(SELECT MAX(data_lancamento) FROM dim_movies WHERE status_filme='Lançado' AND data_lancamento<=date('now')) FROM dim_movies")
show("fact: receita/orcamento (nulos, zeros, >0)",
     "SELECT SUM(receita_brl IS NULL), SUM(receita_brl=0), SUM(receita_brl>0), "
     "SUM(orcamento_brl IS NULL), SUM(orcamento_brl=0), SUM(orcamento_brl>0) FROM fact_movies_performance")
show("fact: lucro com receita/orcamento ausentes",
     "SELECT COUNT(*), SUM(lucro_brl=0), SUM(lucro_brl IS NULL) FROM fact_movies_performance WHERE receita_brl IS NULL OR orcamento_brl IS NULL")
show("fact: notas e popularidade (min, max, nulos, zeros)",
     "SELECT MIN(nota_tmdb),MAX(nota_tmdb),SUM(nota_tmdb IS NULL),SUM(nota_tmdb=0),"
     "MIN(nota_imdb),MAX(nota_imdb),SUM(nota_imdb IS NULL),SUM(nota_imdb=0),"
     "MIN(popularidade),MAX(popularidade) FROM fact_movies_performance")
show("ESCALA dim_reviews.nota_media_usuarios", "SELECT MIN(nota_media_usuarios), MAX(nota_media_usuarios), AVG(nota_media_usuarios) FROM dim_reviews")
show("ESCALA movie_reviews.rating", "SELECT MIN(rating), MAX(rating), AVG(rating), MIN(created_at), MAX(created_at) FROM movie_reviews")
show("dim_reviews bate com média de movie_reviews? (10 exemplos)",
     "SELECT r.sk_movie_id, r.qtd_avaliacoes_usuarios, r.nota_media_usuarios, "
     "(SELECT COUNT(*) FROM movie_reviews x WHERE x.sk_movie_id=r.sk_movie_id), "
     "(SELECT AVG(rating) FROM movie_reviews x WHERE x.sk_movie_id=r.sk_movie_id) FROM dim_reviews r LIMIT 10")
show("qtd_avaliacoes: distribuição", "SELECT qtd_avaliacoes_usuarios, COUNT(*) FROM dim_reviews GROUP BY 1 ORDER BY 1 DESC LIMIT 8")
show("filmes duplicados por título (top 5)", "SELECT titulo, COUNT(*) FROM dim_movies GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
show("dim_movies sem fact / fact sem dim_movies",
     "SELECT (SELECT COUNT(*) FROM dim_movies m WHERE NOT EXISTS (SELECT 1 FROM fact_movies_performance f WHERE f.sk_movie_id=m.sk_movie_id)),"
     "(SELECT COUNT(*) FROM fact_movies_performance f WHERE NOT EXISTS (SELECT 1 FROM dim_movies m WHERE f.sk_movie_id=m.sk_movie_id))")
