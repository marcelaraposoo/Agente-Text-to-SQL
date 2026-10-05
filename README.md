# CineData Agent — Text-to-SQL sobre a camada Gold

Agente que responde perguntas em linguagem natural sobre o catálogo de filmes da
CineData Analytics, gerando e executando SQL (somente leitura) no `cinerocket.db`.

## Stack
Python 3.11+ · OpenRouter (modelos `:free`, tool calling) · SDK `openai` · SQLite3

## Como funciona
1. O schema do banco (tabelas, colunas, FKs e linhas de exemplo) é lido automaticamente e injetado no prompt.
2. O LLM chama a ferramenta `run_sql(query)`.
3. **Guardrails**: só `SELECT/WITH`, uma instrução, `LIMIT` automático, banco aberto em
   `mode=ro` e `set_authorizer` do SQLite bloqueando qualquer escrita.
4. O resultado volta ao LLM, que responde em português para o usuário.

Extras: cache de respostas, fallback entre modelos gratuitos, memória de conversa (modo interativo),
avaliação (`evals/`) e zero retries automáticos (preserva a cota de 50 req/dia).

## Passo a passo
```bash
git clone <seu-repo> && cd cinedata-agent
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # preencha OPENROUTER_API_KEY
# coloque o cinerocket.db na raiz do projeto
export PYTHONPATH=src                                  # PowerShell: $env:PYTHONPATH="src"
python -m cineagent --schema                           # confere o schema (sem usar a API)
python -m cineagent "Top 10 filmes com maior receita"  # pergunta única
python -m cineagent                                    # modo interativo
python -m cineagent --quota                            # cota restante
pytest                                                 # testes dos guardrails (sem API)
python evals/run_evals.py --ids 1,2                    # avaliação
```

## Estrutura
```
src/cineagent/  config, db, guardrails, llm, prompts, agent, cache, CLI
tests/          testes dos guardrails
evals/          perguntas + runner de avaliação
```
