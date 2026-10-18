# Relatório — Classificação de tópicos

## Resultado

| | |
|---|---|
| **Publicadas** | 191 de 359 (**53,2%**) · 166 em revisão · 2 fora |
| **Precisão medida** (amostra aleatória de publicadas, conferida por humano) | **46/46**, Wilson 95%: 92,3%–100% |
| **Previsão** (ver `previsao.txt`) | precisão **96%** (91–99%) · cobertura **53%** (51–55%) |
| **Custo / tempo** | ~US$ 15 no total (~US$ 0,04 por questão) · ~2 h de processamento |

Detalhes da arquitetura, da estratégia e do plano de ML em [`docs/arquitetura.md`](docs/arquitetura.md).

## a) Como pensei

**O problema real não é classificar, é saber quando não publicar.** Um LLM acerta o tema "razoavelmente bem". A régua, porém, é ≥95% nas publicadas, e o erro mais caro é o aluno estudar a matéria errada. Por isso desenhei o sistema em torno de uma pergunta: *em quais questões eu tenho evidência independente de que o tema está certo?* O resto vai para o professor.

**Hipóteses, em ordem:**

1. **Treinar um classificador (ML clássico).** Descartado. Não há nenhuma questão rotulada, e são 377 temas para 359 questões: mesmo rotulando tudo à mão, ficaria menos de um exemplo por tema. O ML entra em produção, quando a fila do professor gerar rótulos limpos (seção c).
2. **Embeddings para filtrar 10–15 temas candidatos antes do LLM.** Descartado sem testar, por custo-benefício. A árvore inteira (375 temas, ~12,8 mil tokens) cabe no prompt e, com *prompt caching*, cada leitura custa ~10% do preço. O filtro só acrescentaria um jeito novo de errar: o tema certo ficar fora da lista quando a questão usa vocabulário diferente do título.
3. **Um LLM só, com "confiança" auto-declarada.** Descartado. A confiança que o modelo declara sobre si mesmo é mal calibrada. A troquei por três sinais que eu consigo medir:
   - concordância entre **dois modelos diferentes** (Sonnet 4.6 e Haiku 4.5), que erram de formas diferentes;
   - um **juiz** com outro prompt, que vê só o tema proposto, os subtemas e os irmãos dele;
   - uma **amostra rotulada à mão**, para medir o acerto de verdade.
4. **Entradas diferentes para os votantes.** Só o votante A vê o `assunto_origem` (com o aviso de que pode estar errado). Se os dois vissem a mesma pista errada, poderiam concordar no erro, e é exatamente essa concordância que libera a publicação.
5. **Usar a régua a favor do aluno, sem trapaça.** Publicar no tema pai conta como certo. Quando os modelos divergem entre subtemas irmãos, publico no tema de nível 1. Nunca publico na disciplina raiz: tecnicamente "contaria", mas é o comportamento que criou as lixeiras.
6. **Medir antes de confiar.** Uma amostra estratificada de 72 questões (50 publicadas) foi rotulada às cegas pelo Opus 4.6. Depois, um humano conferiu todas as publicadas. O Opus e o humano concordaram em 50/50.
7. **Apertar quando a medida mandou.** A primeira medição deu **46/50 = 92%**, abaixo da meta. Os 4 erros eram questões que cruzam dois temas. Em vez de inventar uma regra sob medida para eles, acrescentei um **3º votante independente** (Opus 4.6, às cegas) para todas as questões: só publica se ele também cair no mesmo ramo. A cobertura caiu de 56% para 53%, e as 46 publicadas que sobraram na amostra estão todas certas. Como o Opus passou a votar, a precisão final é medida **só com os rótulos conferidos por humano**, para não ser circular.

**Becos sem saída:**
- **Modelos indisponíveis.** O plano era Claude Sonnet 5.5 + Haiku 5.5, mas a conta AWS usada responde "not available for this account" para toda a família 5.x. Fiquei com os mais novos liberados.
- **Ids inventados.** Na 1ª rodada, o Haiku inventou ids vizinhos dos reais (5688 no lugar de 4688), em 3 de 30 questões. Corrigi forçando, no esquema de saída, um `enum` com os ids existentes.
- **Respostas em laço.** Raramente, um modelo entra em laço e repete texto até estourar o limite. Pus um teto de tokens baixo e uma segunda rodada só para as falhas.
- **Cobertura baixa nas 30 primeiras.** Só 13 de 30 passaram por todos os filtros. A maior parte das divergências vem do Haiku escolhendo temas genéricos ("Procedimento Ordinário") ou o tema duplicado da outra disciplina. Mantive a regra: divergência vai para revisão. O custo é cobertura, não precisão.
- **O juiz quase não discorda.** Ele barrou só 9 de 238. Fica como filtro barato, mas não serve para estimar a precisão.
- **Limite de requisições da conta.** O Opus recebeu `ThrottlingException` em 95 de 151 chamadas na 1ª passada. Refiz com menos paralelismo. Uma questão (Q0293) estoura o limite de tokens de raciocínio sempre e ficou em revisão.

## b) Diagnóstico: o que atrapalha máquina e humano

1. **Temas duplicados entre disciplinas.** Lei Maria da Penha, Abuso de Autoridade, Tráfico de Drogas, Lavagem de Dinheiro, Organizações Criminosas e Crimes Ambientais existem em *Penal* (sem descrição) e em *Legislação Especial*. Ação Penal está em *Penal* e em *Processo Penal*, e LEP em *Legislação Especial* e *Processo Penal*. Para a régua, escolher o lado errado é erro, e não há critério escrito para escolher. Os modelos se dividem exatamente aí.
2. **Temas partidos em "(Parte 1)/(Parte 2)".** Teoria da Pena, Competência, Sentença Penal, Crimes contra o Patrimônio e Crimes contra a Administração Pública existem como tema completo, com subtemas, *e* como "Parte 1/Parte 2" irmãs, sem descrição e sem dizer o que vai em cada parte. Nem um humano consegue escolher sem uma convenção.
3. **Lixeiras.** Temas introdutórios acumularam centenas de questões no sistema de origem:
   - Sistemas e Princípios Processuais Penais (538)
   - Teoria da Pena (453)
   - Introdução ao Estudo do Direito Penal (424)
   - Conceito e Fontes (310)

   Como "falam de tudo", atraem qualquer questão. Tratei títulos genéricos como sinal de risco.
4. **Descrições que não descrevem.** 337 dos 377 temas têm uma descrição gerada automaticamente ("Subtema de X. N questões no source"), e 20 não têm nenhuma. Só 20 explicam o que entra no tema.
5. **Dados de origem pouco confiáveis.** Só 143 das 359 questões têm um `assunto_origem` igual a algum tema, e 18 vêm vazias. Algumas vêm marcadas como Constitucional, Civil ou Tributário.
6. **Texto sujo.** HTML cru, `\n` literal dentro das alternativas e erros de digitação nos temas ("Crimonológicas", "Legitimidoras", "Caractéristas").
7. **Questões difíceis por natureza:**
   - **Múltiplas assertivas (I, II, III, IV)** sobre assuntos diferentes: não existe *um* tema central;
   - **Questões que cruzam Penal e Processo Penal** (ex.: absolvição sumária e recurso cabível);
   - **Questões de Criminologia ancoradas num autor** ("segundo Vera Andrade..."), que cabem em mais de uma corrente.

## c) Produção: 50 mil questões por semana

**Não reclassificar tudo toda semana.** Só entram questões novas, alteradas ou reportadas. Questão repetida (mesmo hash de texto) herda o rótulo.

```
Importação → S3 → EventBridge → Step Functions
  1. Lambda: limpeza + dedupe por hash
  2. Bedrock embeddings (Cohere embed v4) → vetor guardado junto da questão
  3. Classificador treinado (regressão logística sobre embeddings, numa Lambda)
       treinado SÓ com rótulos limpos (professor + especialistas), nunca com os rótulos atuais
       → probabilidade alta: segue para a decisão; custo ≈ US$ 0,0001/questão
  4. LLM (2 votantes + juiz + 3º votante, árvore em cache; Bedrock Batch Inference em lotes) só no resto
  5. Lambda de decisão (as mesmas regras deste case) → publicar / revisar / fora
  6. revisar → fila do professor (Amazon A2I ou tela interna) → decisão vira rótulo → re-treino mensal
Reportes de alunos → SQS → a questão volta para revisar; tema com muitos reportes → alerta
```

**Onde entra cada tipo de IA:**

| Tipo | Papel |
|---|---|
| Embeddings | Entrada do classificador e detecção de duplicatas. |
| Classificador treinado | O "cavalo de carga" barato, depois que existirem rótulos. Não sabe classificar em tema novo. |
| LLM | Casos de baixa confiança, temas novos e mudanças na árvore. |
| Agentes | Fora do caminho principal. Fazem sentido para investigar um tema com muitos reportes e propor temas novos para o grupo `fora`. |
| Professor | Decide os casos difíceis e produz os rótulos que treinam o resto. |

**Custo por questão** (preço de lista; confirmar no Bedrock):

| Caminho | Custo |
|---|---|
| Caminho ML | ~US$ 0,0001 |
| Caminho LLM, medido neste case (2 votos + juiz em todas, Opus nas ~55% publicáveis) | ~US$ 0,036 |
| Caminho LLM com Batch Inference (~50% mais barato, a confirmar) | ~US$ 0,018 |

| Cenário | Custo por semana |
|---|---|
| 5 mil questões novas, só LLM | ~US$ 180 (~US$ 90 em batch) |
| Reprocessar as 50 mil, só LLM | ~US$ 1.800 (por isso só entram novas, alteradas ou reportadas) |
| 5 mil novas, com o ML resolvendo ~70% | ~US$ 55 |

Com acesso aos modelos 5.x (o Haiku 5.5 custa 10× menos que o Haiku 4.5), o caminho LLM ficaria ainda mais barato.

**Qualidade contínua:**
- **Auditoria semanal:** ~100 questões publicadas, sorteadas e revisadas pelo professor. Isso dá a precisão com intervalo, num painel do CloudWatch.
- **Alarme:** se o limite inferior cair abaixo de 95%, o corte sobe sozinho e mais questões vão para a revisão.
- **Reportes dos alunos:** contam como sinal de erro, por tema.
- **Mudança de padrão:** se a distribuição de temas da semana mudar muito, é provável que tenha surgido um assunto que a árvore não cobre.

## d) Memo para o professor

Ver `memo_professor.md`.

## O que eu faria com mais tempo

1. **Amostra maior.** Com 46 publicadas conferidas, o limite inferior é 92%. Com ~150, ele ficaria perto de 97% se o acerto se mantiver, e a previsão sairia mais estreita.
2. **Perguntar à equipe a convenção dos temas duplicados e das "Partes".** Só essa resposta liberaria boa parte das 23 questões que hoje vão para revisão por isso.
3. **Votante B mais forte.** Com acesso aos modelos 5.x, trocar o Haiku 4.5, que causa a maior parte das 119 divergências. É a maior alavanca de cobertura.
4. **Testar o filtro por embeddings na prática.** Descartei por custo-benefício, sem medir. Vale comparar com a árvore inteira na mesma amostra.
5. **Investigar as poucas `fora`.** Só 2 em 359. Testar exemplos no prompt para os modelos aceitarem melhor que "nenhum tema serve".
6. **Conferir também as questões em revisão.** Medir com rótulo humano quantas sugestões estão certas, para saber quanto do tempo do professor vira só "confirmar".
