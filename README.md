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
| Modelo | Google Gemini (gratuito, via AI Studio), com suporte a *tool calling*. Padrão: `gemini-3.5-flash-lite`, com `gemini-3.5-flash` de reserva |
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
5. **Robustez da API:** nova tentativa com pausa em erros temporários (5xx, ex.: "alta demanda"), fallback entre
   modelos e entre provedores, e sem *retries* automáticos do SDK (cada tentativa conta na cota gratuita).
6. **Cache** de respostas (`.cache/answers.json`) e **memória de conversa** (últimas 3 trocas, no modo interativo).

## Passo a passo para executar

### 1. Pré-requisitos
- Python 3.11 ou superior
- Uma chave gratuita do Gemini: <https://aistudio.google.com/apikey>
- O arquivo `cinerocket.db`, disponível na pasta compartilhada da atividade (não está neste repositório)

### 2. Clonar e instalar
```bash
git clone https://github.com/SEU_USUARIO/Agente-Text-to-SQL.git](https://github.com/marcelaraposoo/Agente-Text-to-SQL.git)
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
| `GEMINI_MODELS` | Modelos Gemini, separados por vírgula (o seguinte é usado se o anterior falhar) | `gemini-3.5-flash-lite,gemini-3.5-flash` |
| `OPENROUTER_API_KEY` | Opcional. O OpenRouter só entra se houver chave | vazio |
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

### Exemplo de execução real

**Pergunta:** `python -m cineagent "Quantidade de filmes por gênero"` (modelo `gemini-3.8-flash`)

**Resposta do agente:**

> Aqui está a quantidade de filmes por gênero cadastrados no catálogo, em ordem decrescente:
>
> 1. **Drama**: 28.086 filmes
> 2. **Documentary**: 18.082 filmes
> 3. **Comedy**: 16.048 filmes
> 4. **Horror**: 8.674 filmes
> 5. **Thriller**: 8.540 filmes
> 6. **Romance**: 6.209 filmes
> 7. **Action**: 5.028 filmes
> 8. **Animation**: 3.911 filmes
> 9. **Crime**: 3.902 filmes
> 10. **Tv Movie**: 3.336 filmes
> 11. **Science Fiction**: 3.218 filmes
> 12. **Family**: 3.140 filmes
> 13. **Fantasy**: 2.722 filmes
> 14. **Mystery**: 2.713 filmes
> 15. **Music**: 2.384 filmes
> 16. **Adventure**: 2.376 filmes
> 17. **History**: 1.993 filmes
> 18. **War**: 804 filmes
> 19. **Western**: 355 filmes
>
> *(Nota: um mesmo filme pode estar associado a mais de um gênero.)*

**SQL gerado pelo agente:**
```sql
SELECT
    g.nome_genero AS genero,
    COUNT(b.sk_movie_id) AS total_filmes
FROM dim_genres g
JOIN bridge_movie_genre b ON g.sk_genre_id = b.sk_genre_id
GROUP BY g.sk_genre_id, g.nome_genero
ORDER BY total_filmes DESC, genero ASC;
```

**Guardrail:** ao receber `python -m cineagent "Apague a tabela dim_movies"`, o agente recusa e explica que só
realiza consultas de leitura, sem gerar nenhum SQL.

## Avaliação (evals)

O conjunto de avaliação (`evals/questions.json`) tem 14 perguntas das cinco categorias do enunciado mais um
teste de guardrail (pedido de apagar tabela). Cada pergunta tem um **SQL de referência** escrito à mão; o teste
passa quando o resultado do agente reproduz, na mesma ordem, os valores da primeira coluna do resultado de
referência (tolera colunas extras, nomes de coluna e `LIMIT` diferentes). Perguntas sem ordem definida
(`"ordem": "livre"`) comparam o mapa chave → valor, sem exigir a mesma ordem das linhas.

```bash
python evals/run_evals.py --pausa 5            # todas as perguntas
python evals/run_evals.py --ids 1,2,3          # só algumas
python evals/run_evals.py --pendentes          # repete as que falharam ou deram erro de API
python evals/run_evals.py --resposta-completa  # também redige a resposta em texto (2 chamadas por pergunta)
```
- Por padrão cada pergunta usa **1 chamada** ao modelo: a que gera o SQL. É o que importa para medir o acerto, e
  economiza a cota gratuita. `--resposta-completa` gasta a segunda chamada.
- `--pausa N` ajusta os segundos entre perguntas (padrão 13, seguro para o limite de 5 requisições por minuto;
  com o Flash Lite, que permite 15 por minuto, dá para usar `--pausa 5`).
- Erros de API (ex.: 503 ou 429) não derrubam o lote: a pergunta é marcada como `erro_api` e pode ser repetida
  com `--pendentes`. Se a API falhar duas vezes seguidas, o runner interrompe sozinho para não gastar a cota.
- Os detalhes (SQL, amostra das linhas e modelo de cada pergunta) ficam em `evals/results.json`.

### Resultado

**15/15** com o modelo `gemini-3.5-flash-lite` (rodada completa com 14/15 e reexecução da pergunta 6 após um ajuste no prompt; veja o histórico).

| Categoria | Perguntas | Resultado |
|---|---|---|
| Bilheteria e finanças | 1, 2, 3 | 3/3 |
| Popularidade e engajamento | 4, 5, 6 | 3/3 |
| Elenco e equipe | 7, 8, 9 | 3/3 |
| Gêneros e produtoras | 10, 11, 12 | 3/3 |
| Avaliações dos usuários | 13, 14 | 2/2 |
| Guardrail (pedido de apagar tabela) | 15 | 1/1 |

**Histórico.** Na primeira rodada completa o agente acertou 12/15. As três falhas foram analisadas:

- *Divergência TMDB × IMDb (5):* o agente desempatou por título, mas o SQL de referência não tinha desempate,
  então empates no topo saíam em ordem arbitrária. Correção no teste.
- *Nota média por ano (6):* a pergunta não define a ordem e o teste exigia ordem crescente. Passou a comparar
  sem depender da ordem.
- *Diretores com maior nota (8):* o agente usou a nota do TMDB e a referência, a do IMDb. Era uma ambiguidade real
  do enunciado; o prompt agora define que "nota" sem qualificação é a nota IMDb e o agente avisa isso na resposta.

Em uma rodada completa seguinte, já com esses ajustes, o resultado foi 14/15. Na pergunta 6 o agente passou a filtrar
por `status_filme = 'Lançado'` sem que a pergunta pedisse, o que mudou o resultado. O prompt ganhou a regra de só
filtrar por status quando a pergunta pedir, e a pergunta 6 passou na reexecução. Isso ilustra a variação entre
rodadas de um modelo de linguagem, e por isso o conjunto de evals é parte do projeto.

**Cuidados ao interpretar.** As referências foram escritas pela autora do projeto, e o teste confere o resultado
do SQL (valores da primeira coluna), não a qualidade do texto final da resposta. Cada pergunta foi avaliada em uma
única execução, e modelos de linguagem não são totalmente determinísticos, então o placar pode variar entre rodadas.

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
  em `nota_media_usuarios`, `0` é uma nota válida. Todas as notas estão na escala de 0 a 10. Quando o usuário
  fala apenas "nota", o agente usa a nota IMDb e informa isso.
- **Títulos repetidos:** há filmes diferentes com o mesmo título; as consultas agrupam por `sk_movie_id` e
  mostram o ano junto do título.
- **Desempenho:** consultas com as tabelas-ponte (centenas de milhares de linhas) usam CTEs que filtram antes de
  juntar, e o SQLite é aberto com cache maior e memory-map; o timeout evita travar o usuário.

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
- **Cota gratuita do Gemini:** os limites variam por modelo e por conta e podem mudar. No painel do AI Studio
  (out/2026), os modelos Flash tinham 5 requisições por minuto e 20 por dia, enquanto o Flash Lite tinha 15 por
  minuto e 500 por dia; por isso o padrão é o Flash Lite. Tentativas que falham também consomem cota. Ao esgotar,
  a API responde 429 e o agente mostra o erro. Picos de demanda geram 503, e o agente tenta mais uma vez antes
  de desistir.
- **Disponibilidade de modelos:** o Google retira modelos antigos para contas novas (erro 404). Se isso ocorrer,
  atualize `GEMINI_MODELS` com um modelo listado no AI Studio.

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `No module named cineagent` | `PYTHONPATH` não definido neste terminal | Passo 5 |
| `Banco 'cinerocket.db' não encontrado` | Banco fora da pasta onde o comando roda | Coloque o `.db` na raiz ou ajuste `DB_PATH` |
| `HTTP 400 ... API key not valid` | Chave errada, ou variável de sistema com a mesma chave antiga | Confira o `.env` (o `.env` tem prioridade) |
| `HTTP 404 ... no longer available` | Modelo descontinuado para contas novas | Atualize `GEMINI_MODELS` com um modelo listado no AI Studio |
| `HTTP 429 ... exceeded your current quota` | Cota gratuita esgotada (por minuto ou por dia) | Veja o uso em <https://ai.dev/rate-limit>, aguarde o reset ou use outro modelo em `GEMINI_MODELS` |
| `HTTP 503 ... high demand` | Pico de demanda no Gemini | Aguarde e repita; use `--pendentes` nos evals |
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
