# CineData Agent — Text-to-SQL sobre a camada Gold

Agente que permite a usuários **não técnicos** fazerem perguntas em linguagem natural sobre o catálogo de
filmes da CineData Analytics. Ele gera o SQL, executa em modo **somente leitura** na camada Gold
(`cinerocket.db`, SQLite) e responde em português.

> Atividade GenAI — Visagio | Rocket Lab 2026

## Sumário
- [Stack](#stack)
- [Como funciona](#como-funciona)
- [Passo a passo para executar](#passo-a-passo-para-executar)
- [Uso](#uso)
- [Avaliação (evals)](#avaliação-evals)
- [Testes](#testes)
- [Decisões de projeto](#decisões-de-projeto)
- [Limitações conhecidas](#limitações-conhecidas)
- [Solução de problemas](#solução-de-problemas)
- [Estrutura do projeto](#estrutura-do-projeto)

## Stack

| Item | Escolha |
|---|---|
| Linguagem | Python 3.11+ |
| Modelo | Google Gemini (gratuito, via AI Studio), com suporte a *tool calling* |
| Acesso ao modelo | SDK `openai` apontando para o endpoint compatível do Gemini |
| Agente | Loop próprio de *tool calling* (sem framework pesado) com a ferramenta `run_sql` |
| Banco | SQLite3 (`cinerocket.db`), 10 tabelas do modelo dimensional |
| Provedor alternativo | OpenRouter (opcional, modelos `:free`) |

## Como funciona

```
Pergunta ──► Cache? ──sim──► Resposta
                │ não
                ▼
        Prompt = regras de negócio + schema do banco (lido automaticamente)
                ▼
        LLM (Gemini) ──► chama a ferramenta run_sql(query)
                ▼
   Guardrails: valida o SQL ─► executa em banco read-only (com timeout) ─► linhas
                ▼
        LLM redige a resposta em português, com o SQL usado
```

1. **Schema automático.** Tabelas, colunas, FKs, valores categóricos (`status_filme`, `tipo_pessoa`,
   `nome_genero`) e poucas linhas de exemplo são lidos do próprio banco e injetados no prompt.
2. **Regras de negócio no prompt.** Tratamento de dados ausentes (NULL/0 = "não informado"), moeda padrão em R$,
   definição de margem, recorte de "últimos N anos", desempate, títulos repetidos e padrões de consulta eficientes.
3. **Guardrails em três camadas:**
   - o modelo é instruído a recusar pedidos fora do escopo ou de escrita;
   - o validador (`guardrails.py`) aceita só `SELECT`/`WITH`, uma instrução, bloqueia palavras de escrita e
     aplica `LIMIT` automático;
   - o banco é aberto em `mode=ro` e com `set_authorizer` do SQLite, que nega qualquer operação que não seja leitura.
4. **Timeout por consulta** (padrão 60 s): consultas lentas são interrompidas e o modelo recebe uma dica para
   reescrever o SQL de forma mais leve.
5. **Robustez da API:** *retry* com pausa em erros temporários (5xx, ex.: "alta demanda"), fallback entre modelos
   e entre provedores, sem *retries* automáticos do SDK.
6. **Cache** de respostas (`.cache/answers.json`) e **memória de conversa** (últimas 3 trocas, no modo interativo).

## Passo a passo para executar

### 1. Pré-requisitos
- Python 3.11 ou superior
- Uma chave gratuita do Gemini: <https://aistudio.google.com/apikey>
- O arquivo `cinerocket.db`, disponível na pasta compartilhada da atividade (não está neste repositório)

### 2. Clonar e instalar
```bash
git clone https://github.com/SEU_USUARIO/Agente-Text-to-SQL.git
cd Agente-Text-to-SQL

python -m venv .venv
source .venv/bin/activate        # Linux/macOS
source .venv/Scripts/activate    # Windows (Git Bash)
.venv\Scripts\Activate.ps1       # Windows (PowerShell)

pip install -r requirements.txt
```

### 3. Configurar a chave
Copie o modelo e preencha `GEMINI_API_KEY`:
```bash
cp .env.example .env             # Windows (PowerShell/cmd): copy .env.example .env
```
O `.env` **não** vai para o Git (está no `.gitignore`).

| Variável | Descrição | Padrão |
|---|---|---|
| `LLM_PROVIDERS` | Provedores em ordem de prioridade (fallback) | `gemini,openrouter` |
| `GEMINI_API_KEY` | Chave do Google AI Studio | — |
| `GEMINI_MODELS` | Modelos Gemini, separados por vírgula (fallback) | `gemini-3.8-flash` |
| `OPENROUTER_API_KEY` | Opcional. Só entra se houver chave | vazio |
| `OPENROUTER_MODELS` | Modelos gratuitos do OpenRouter | `openrouter/free,...` |
| `DB_PATH` | Caminho do banco | `cinerocket.db` |
| `QUERY_TIMEOUT` | Segundos máximos por consulta SQL | `60` |

### 4. Colocar o banco
Copie o `cinerocket.db` para a **raiz do projeto** (a mesma pasta do `README.md`).

### 5. Definir o caminho dos módulos
O código fica em `src/`, então informe isso ao Python em cada terminal novo:
```bash
export PYTHONPATH=src            # Linux/macOS/Git Bash
$env:PYTHONPATH="src"            # Windows (PowerShell)
set PYTHONPATH=src               # Windows (cmd)
```

### 6. Conferir que está tudo certo (não usa a API)
```bash
python -m cineagent --schema     # deve listar as tabelas do banco
pytest                           # guardrails + SQLs de referência no banco real
```

## Uso

```bash
# Pergunta única
python -m cineagent "Top 10 filmes com maior receita em R$"

# Modo interativo (com memória de conversa)
python -m cineagent

# Ignorar o cache
python -m cineagent --no-cache "Quantidade de filmes por gênero"
```

Exemplos de perguntas:

- *Quantidade de filmes por gênero*
- *Top 10 filmes com maior receita em R$*
- *Filmes com maior margem de lucro, entre os que possuem receita e orçamento informados*
- *Qual dupla ator–diretor mais trabalhou junta?*
- *Diretores com maior nota média (mínimo de 5 filmes)*
- *Nota média IMDb por ano de lançamento*
- *Filmes em que a nota média dos usuários mais diverge da nota IMDb*

<!-- PREENCHER: cole aqui 1 ou 2 respostas reais do agente (pergunta, resposta e SQL). -->

## Avaliação (evals)

O conjunto de avaliação (`evals/questions.json`) tem 14 perguntas das cinco categorias do enunciado mais um
teste de guardrail (pedido de apagar tabela). Cada pergunta tem um **SQL de referência** escrito à mão; o teste
passa quando o resultado do agente reproduz, na mesma ordem, os valores da primeira coluna do resultado de
referência (tolera colunas extras, nomes de coluna e `LIMIT` diferentes).

```bash
python evals/run_evals.py                # todas as perguntas
python evals/run_evals.py --ids 1,2,3    # só algumas
python evals/run_evals.py --pendentes    # repete as que falharam ou deram erro de API
```
Erros de API (ex.: 503 ou 429) não derrubam o lote: a pergunta é marcada como `erro_api` e pode ser repetida
com `--pendentes`. Se a API falhar duas vezes seguidas, o runner interrompe sozinho para não gastar a cota.
Os detalhes (SQL e resposta de cada pergunta) ficam em `evals/results.json`.

**Resultado:** <!-- PREENCHER: X/15 --> 

<!-- PREENCHER: tabela com id, categoria, status. Comentar falhas e o que foi ajustado no prompt. -->

## Testes

```bash
pytest
```
- `tests/test_guardrails.py`: o validador aceita `SELECT`/`WITH` e bloqueia `DROP`, `DELETE`, `UPDATE`,
  `PRAGMA`, `ATTACH` e múltiplas instruções.
- `tests/test_reference_sql.py`: executa os SQLs de referência no `cinerocket.db` (pulado se o banco não existir).

Scripts úteis, sem uso da API:
- `python scripts/explore.py` — diagnóstico do banco (nulos, zeros, escalas, valores categóricos).
- `python scripts/bench_sql.py` — tempo de cada SQL de referência.

## Decisões de projeto

- **Sem framework de agentes.** O fluxo é um único loop de *tool calling* com uma ferramenta; um framework
  adicionaria dependências sem ganho aqui, e o loop é fácil de auditar.
- **Schema introspectado em vez de escrito à mão**, para o prompt acompanhar o banco.
- **Moeda:** colunas `*_brl` (R$) por padrão; `*_usd` só se o usuário pedir dólar.
- **Margem de lucro = lucro / receita.** Para retorno sobre o orçamento (lucro / orçamento) o agente usa a
  fórmula de ROI se o usuário pedir.
- **"Últimos N anos":** a base tem datas futuras (até 2029). O limite é a maior data de lançamento entre filmes
  com status `Lançado` e data até hoje, e o período considera apenas filmes lançados.
- **Notas:** `NULL`/`0` em `nota_imdb`, `nota_tmdb` e `popularidade` significam "sem dado" e são ignorados;
  em `nota_media_usuarios`, `0` é uma nota válida. Todas as notas estão na escala de 0 a 10.
- **Títulos repetidos:** há filmes diferentes com o mesmo título; as consultas agrupam por `sk_movie_id` e
  mostram o ano junto do título.

## Limitações conhecidas

- **Poucos filmes com dados financeiros:** apenas 3.373 de 95.645 têm receita informada (≈ 3,5 %) e 7.926 têm
  orçamento informado (≈ 8,3 %). Os rankings financeiros refletem só esses filmes, e o agente avisa isso na resposta.
- **Lucro pode ficar inflado** quando há receita mas não há orçamento (o lucro vira a própria receita).
  As perguntas "lucro médio por gênero" e "produtora com maior lucro" seguem o enunciado literalmente
  (filtram só `receita > 0`).
- **Divergência entre notas** não exige número mínimo de votos; o topo do ranking pode incluir filmes com
  poucas avaliações.
- **Nomes de gêneros** vêm em inglês, como estão na base.
- **Respostas dependem do modelo:** o Gemini pode errar o SQL em perguntas complexas; por isso há o conjunto de
  evals e o validador de SQL.
- **Picos de demanda do Gemini** podem gerar erro 503; o agente tenta de novo com pausa antes de desistir.
- **Cota gratuita:** o plano gratuito do Gemini tem limite diário de requisições. Cada pergunta usa 2 chamadas
  (ou mais, se o SQL precisar de correção), então rodar os 15 evals de uma vez pode esgotar a cota (erro 429).
  Nesse caso, rode em lotes (`--ids`) ou use `--pendentes` depois que a cota renovar.

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `No module named cineagent` | `PYTHONPATH` não definido neste terminal | Passo 5 |
| `Banco 'cinerocket.db' não encontrado` | Banco fora da pasta onde o comando roda | Coloque o `.db` na raiz ou ajuste `DB_PATH` |
| `HTTP 400 ... API key not valid` | Chave errada, ou variável de sistema com a mesma chave antiga | Confira o `.env` (o `.env` tem prioridade) |
| `HTTP 404 ... model ... no longer available` | Nome de modelo descontinuado | Atualize `GEMINI_MODELS` com um modelo listado no AI Studio |
| `HTTP 503 ... high demand` | Pico de demanda no Gemini | Aguarde e repita; use `--pendentes` nos evals |
| `HTTP 429 ... exceeded your current quota` | Cota gratuita do Gemini esgotada (por minuto ou por dia) | Veja o uso em <https://ai.dev/rate-limit>, aguarde o reset ou use outro modelo em `GEMINI_MODELS` |
| `Nenhum provedor configurado` | `.env` sem chave ou fora da raiz | Preencha `GEMINI_API_KEY` |

## Estrutura do projeto

```
.
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── src/cineagent/
│   ├── __main__.py     # CLI (pergunta única, modo interativo, --schema)
│   ├── agent.py        # loop de tool calling, ferramenta run_sql, memória e cache
│   ├── llm.py          # cliente do LLM: retry, fallback entre modelos e provedores
│   ├── prompts.py      # prompt do sistema e definição da ferramenta
│   ├── db.py           # conexão read-only, authorizer, introspecção do schema
│   ├── guardrails.py   # validação do SQL gerado
│   ├── cache.py        # cache de respostas
│   └── config.py       # configuração via .env
├── evals/              # perguntas, SQLs de referência, runner e resultados
├── tests/              # testes dos guardrails e dos SQLs de referência
└── scripts/            # diagnóstico do banco e benchmark
```
