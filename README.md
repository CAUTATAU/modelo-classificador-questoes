# Case: classificação de tópicos

Classifica 359 questões de Penal, Processo Penal, Legislação Penal Especial e Criminologia na árvore de temas da plataforma. Cada questão recebe uma decisão: `publicar`, `revisar` ou `fora`. A meta é ≥95% de acerto nas publicadas.

## Como rodar

Pré-requisitos:
- Python 3.12+.
- Uma conta AWS com Bedrock liberado para Claude Sonnet 4.6 e Haiku 4.5 (região `us-east-1`).
- Um perfil configurado no AWS CLI.

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
# coloque questoes.jsonl, temas.csv e LEIA-ME.md (anexos do case) em dados/ — não versionados
$env:AWS_PROFILE = "pessoal"   # perfil AWS local; nenhuma credencial fica no código

.venv\Scripts\python preparar.py            # limpa textos, monta a árvore, marca temas de risco
.venv\Scripts\python classificar.py teste   # confere acesso aos modelos
.venv\Scripts\python classificar.py votar   # votante A (Sonnet 4.6) e B (Haiku 4.5); rode 2x para refazer falhas
.venv\Scripts\python classificar.py juiz    # juiz (Sonnet 4.6) só nas candidatas a publicar
.venv\Scripts\python decidir.py amostra     # sorteia a amostra-ouro (72 questões, estratificada)
.venv\Scripts\python classificar.py rotular # Opus 4.6 pré-rotula a amostra às cegas (sem pista, sem ver os votos)
.venv\Scripts\python decidir.py preencher   # põe os rótulos do Opus na amostra e gera cache/conferir.md
#   → um humano confere todas as publicadas em que o Opus discorda + 15 concordâncias sorteadas
.venv\Scripts\python decidir.py             # regras → publicacao.csv; mede a precisão na amostra rotulada
```

As chamadas usam **boto3** (`bedrock-runtime.invoke_model`) com o corpo da Messages API da Anthropic. É o mesmo JSON que o SDK da Anthropic enviaria; os retries ficam no modo `adaptive` do botocore.

Todas as respostas dos modelos ficam em `cache/*.jsonl`. Rodar de novo só chama o que falta.

**Se mudar um prompt ou o esquema de resposta**, mova os `cache/votos_*.jsonl` para outra pasta. Assim todas as questões ficam classificadas com a mesma versão.

## Pipeline

| Etapa | Arquivo | O que faz |
|---|---|---|
| 1 | `preparar.py` | Limpa o HTML e monta a árvore dos temas ativos (indentada, com as descrições reais). Marca três flags de risco: tema **duplicado** em outra disciplina, irmão **"(Parte N)"** e título **genérico** (as lixeiras). |
| 2 | `classificar.py votar` | Dois modelos diferentes classificam cada questão com a árvore inteira no prompt, cacheada. A saída é estruturada, com `enum` dos ids reais. Só o votante A vê a pista de origem (`disciplina/assunto_origem`): entradas diferentes deixam os erros menos correlacionados. |
| 3 | `classificar.py juiz` | Outro prompt, sem a árvore, confere se o nó proposto está certo (`certo / errado / ambiguo`). |
| 4 | `decidir.py` | Aplica as regras abaixo, calcula a confiança e valida o CSV contra o LEIA-ME. |
| 5 | `decidir.py` + `amostra_ouro.csv` | Rótulos feitos à mão numa amostra estratificada, sem ver a escolha dos modelos. Gera a precisão com intervalo de Wilson de 95%. |

### Regras de decisão (fixadas antes de olhar a amostra)

| Situação | Decisão |
|---|---|
| Os dois modelos dizem "nenhum tema serve" | `fora` |
| Os modelos caem em ramos diferentes (o único ancestral comum é a disciplina) | `revisar` |
| O juiz não diz "certo" | `revisar` |
| Divergência entre subtemas que sobe para um tema genérico | `revisar` |
| Tema duplicado ou dividido em "(Parte N)", sem unanimidade, ou com o tema gêmeo como 2ª opção | `revisar` |
| `disciplina_origem` fora do recorte (Constitucional, Civil, Tributário, Ambiental) | `revisar` |
| Resto | `publicar` no ancestral comum mais baixo dos dois votos |

O ancestral comum é o mesmo nó quando há unanimidade. Quando os modelos divergem entre subtemas irmãos, é o tema pai, o que vale como acerto pela régua do case. **Nunca publicamos na disciplina raiz.**

## Modelos, custo e tempo

| Papel | Modelo (Bedrock) | Configuração |
|---|---|---|
| Votante A | `us.anthropic.claude-sonnet-4-6` | thinking adaptativo, effort `low` |
| Votante B | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | sem thinking |
| Juiz | `us.anthropic.claude-sonnet-4-6` | effort `medium` |

- **Por que esses modelos:** o plano era Sonnet 5.5 + Haiku 5.5, mas a conta usada não tem acesso aos modelos 5.x ("not available for this account"). Ficaram os mais novos liberados.
- **Custo:** a árvore (~12,8 mil tokens) vai em cache, e cada leitura em cache custa ~10% do preço normal. Rodada completa medida pelos tokens, a preço de lista:

  | Etapa | Custo |
  |---|---|
  | Votante A | ~US$ 2,70 |
  | Votante B | ~US$ 1,00 |
  | Juiz (238 questões) | ~US$ 1,60 |
  | **Total (~US$ 0,015 por questão)** | **~US$ 5,30** |

  Com os testes, o case inteiro ficou em ~US$ 6. O preço no Bedrock pode diferir um pouco do de lista.
- **Tempo:** ~40 min para as 359 questões (4 chamadas em paralelo; o limite de requisições da conta é o gargalo).

## Decisões tomadas à mão

- Os anexos e o PDF do case **não** estão no repositório: são dados reais da empresa.
- O conjunto de disciplinas "fora do recorte" e a regex de títulos genéricos foram definidos olhando os dados (`preparar.py`, `decidir.py`).
- O Haiku inventava ids parecidos com os reais, como 5688 no lugar de 4688. Corrigido com `enum` no esquema. A 1ª versão dos votos está em `cache/v1/` (fora do git).
