# Case: classificação de tópicos

Classifica 359 questões de Penal, Processo Penal, Legislação Penal Especial e Criminologia na árvore de temas da plataforma. Cada questão recebe uma decisão: `publicar`, `revisar` ou `fora`. A meta é ≥95% de acerto nas publicadas.

**Documentos:**
- [`docs/arquitetura.md`](docs/arquitetura.md): arquitetura completa, estratégia, medição de qualidade, custos e o plano de produção com ML.
- [`relatorio.md`](relatorio.md): o relatório do case.
- [`memo_professor.md`](memo_professor.md): o memo para o professor.

## Como rodar

Pré-requisitos:
- Python 3.12+.
- Uma conta AWS com Bedrock liberado para Claude Sonnet 4.6 e Haiku 4.5 (região `us-east-1`).
- Um perfil configurado no AWS CLI.

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
# coloque questoes.jsonl, temas.csv e LEIA-ME.md (anexos do case) em dados/ — não versionados
# usa o perfil default do AWS CLI; para outro: $env:AWS_PROFILE = "nome". Nenhuma credencial fica no código

.venv\Scripts\python preparar.py            # limpa textos, monta a árvore, marca temas de risco
.venv\Scripts\python classificar.py teste   # confere acesso aos modelos
.venv\Scripts\python classificar.py votar   # votante A (Sonnet 4.6) e B (Haiku 4.5); rode 2x para refazer falhas
.venv\Scripts\python classificar.py juiz    # juiz (Sonnet 4.6) só nas candidatas a publicar
.venv\Scripts\python decidir.py amostra     # sorteia a amostra-ouro (72 questões, estratificada)
.venv\Scripts\python classificar.py rotular # Opus 4.6 às cegas (sem pista, sem ver os votos): pré-rótulo da amostra
                                            # e 3º votante nas publicáveis; rode 2x para refazer falhas
.venv\Scripts\python decidir.py preencher   # põe os rótulos do Opus na amostra e lista em cache/conferir.md
#   → um humano confere as publicadas da amostra que ainda não foram conferidas
.venv\Scripts\python decidir.py             # regras → publicacao.csv; mede a precisão na amostra rotulada
```

As chamadas usam **boto3** (`bedrock-runtime.invoke_model`) com o corpo da Messages API da Anthropic. É o mesmo JSON que o SDK da Anthropic enviaria; os retries ficam no modo `adaptive` do botocore.

Todas as respostas dos modelos ficam em `cache/*.jsonl`. Rodar de novo só chama o que falta.

**Reproduzir sem a AWS:** as respostas usadas na entrega estão versionadas (`cache/votos_A.jsonl`, `votos_B.jsonl`, `juiz.jsonl`, `rotulos_opus.jsonl`). Com os anexos em `dados/`, rode `python decidir.py`: ele regenera exatamente o `publicacao.csv` e a medição de precisão, sem nenhuma chamada a modelo.

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
| O 3º votante (Opus 4.6, às cegas) não cai no mesmo ramo do nó | `revisar` |
| Resto | `publicar` no ancestral comum mais baixo dos dois votos |

A regra do 3º votante **não** estava nas regras iniciais. Ela entrou depois da 1ª medição: 46/50 = 92% na amostra, abaixo da meta. Os 4 erros eram questões entre dois temas, e o Opus discordou em todos. Por isso, a precisão final é medida **só com rótulos conferidos por humano**: usar o Opus como votante e como gabarito ao mesmo tempo seria circular.

O ancestral comum é o mesmo nó quando há unanimidade. Quando os modelos divergem entre subtemas irmãos, é o tema pai, o que vale como acerto pela régua do case. **Nunca publicamos na disciplina raiz.**

## Modelos, custo e tempo

| Papel | Modelo (Bedrock) | Configuração |
|---|---|---|
| Votante A | `us.anthropic.claude-sonnet-4-6` | thinking adaptativo, effort `low` |
| Votante B | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | sem thinking |
| Juiz | `us.anthropic.claude-sonnet-4-6` | effort `medium` |
| 3º votante + pré-rótulo da amostra | `us.anthropic.claude-opus-4-6-v1` | thinking adaptativo, effort `high`, sem pista |

- **Por que esses modelos:** o plano era Sonnet 5.5 + Haiku 5.5, mas a conta usada não tem acesso aos modelos 5.x ("not available for this account"). Ficaram os mais novos liberados.
- **Custo:** a árvore (~12,8 mil tokens) vai em cache, e cada leitura em cache custa ~10% do preço normal. Rodada completa medida pelos tokens, a preço de lista:

  | Etapa | Custo |
  |---|---|
  | Votante A (359) | ~US$ 3,00 |
  | Votante B (359) | ~US$ 1,10 |
  | Juiz (238) | ~US$ 1,70 |
  | Opus: amostra (72) + 3º votante (150) | ~US$ 8,00 |
  | 1ª versão, testes e falhas | ~US$ 1,40 |
  | **Total (~US$ 0,036 por questão no pipeline final)** | **~US$ 15,30** |

  O preço no Bedrock pode diferir um pouco do de lista.
- **Tempo:** ~2 h de processamento. São ~40 min para os votos e o juiz e ~1 h para o Opus, por causa do limite de requisições da conta.

## Decisões tomadas à mão

- Os anexos e o PDF do case **não** estão no repositório: são dados reais da empresa.
- O conjunto de disciplinas "fora do recorte" e a regex de títulos genéricos foram definidos olhando os dados (`preparar.py`, `decidir.py`).
- O Haiku inventava ids parecidos com os reais, como 5688 no lugar de 4688. Corrigido com `enum` no esquema. A 1ª versão dos votos está em `cache/v1/` (fora do git).
- **Conferência humana da amostra-ouro.** O Opus 4.6 pré-rotulou as 72 questões às cegas. Um humano conferiu, uma a uma, **todas as 50 publicadas** da amostra (coluna `observacao = conferido` em `amostra_ouro.csv`) e concordou com o Opus em 50/50. As 22 da amostra em `revisar`/`fora` ficaram só com o rótulo do Opus, porque não entram na precisão.
- **Regra do 3º votante, criada depois da 1ª medição.** As regras iniciais deram 46/50 = 92%. A única regra acrescentada depois de ver a amostra foi exigir que o Opus 4.6 também caia no mesmo ramo. Ela vale para todas as questões; não foi feita sob medida para os erros. Resultado: 46/46.
- **Q0293** estoura o limite de raciocínio do Opus em todas as tentativas. Ficou em `revisar` por falta do 3º voto; não foi forçada.
