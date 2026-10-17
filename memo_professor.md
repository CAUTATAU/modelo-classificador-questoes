# Memo para o professor

**Assunto:** classificação automática das questões de Penal, Processo Penal, Legislação Especial e Criminologia

## O que foi feito

Dois programas de IA diferentes leram cada uma das 359 questões e escolheram, cada um por conta própria, o tema da árvore. Um terceiro conferiu a escolha. A questão só vai direto para o aluno quando os três concordam. Quando há divergência ou dúvida, ela vai para a sua fila, já com uma sugestão de tema e o motivo da dúvida.

A meta é que pelo menos 95 de cada 100 questões publicadas estejam no tema certo. Para medir isso, uma amostra foi conferida à mão.

## O que encontramos na árvore de temas

A maior parte das dúvidas não vem das questões, e sim da própria árvore:

1. **Temas repetidos em duas disciplinas.** "Lei Maria da Penha", "Abuso de Autoridade", "Tráfico de Drogas", "Lavagem de Dinheiro", "Organizações Criminosas" e "Crimes Ambientais" existem em *Penal* e em *Legislação Especial*. "Ação Penal" existe em *Penal* e em *Processo Penal*, e "Lei de Execução Penal" em *Legislação Especial* e em *Processo Penal*. O aluno que escolhe um não vê as questões do outro.
2. **Temas partidos em "Parte 1" e "Parte 2".** Teoria da Pena, Competência, Sentença Penal, Crimes contra o Patrimônio e Crimes contra a Administração Pública aparecem inteiros (com subtemas) e também como "Parte 1/Parte 2", sem dizer o que vai em cada parte.
3. **Temas "lixeira".** "Introdução ao Estudo do Direito Penal", "Sistemas e Princípios Processuais Penais", "Conceito e Fontes" e "Teoria Geral das Prisões" acumularam centenas de questões que não são deles. São genéricos demais e atraem tudo.
4. **Temas sem explicação.** Quase nenhum tema diz o que entra e o que não entra nele.
5. **Erros de digitação.** "Escolas Crimonológicas", "Teorias Legitimidoras", "Caractéristas".

## O que recomendamos mudar

- **Unificar os temas repetidos.** Manter um só (sugestão: o de Legislação Especial) e mover as questões do outro.
- **Acabar com "Parte 1/Parte 2".** Transformar as partes em subtemas com nomes de conteúdo (ex.: "Teoria da Pena > Dosimetria").
- **Quebrar as lixeiras** em subtemas específicos, ou pelo menos escrever o que *não* entra nelas.
- **Escrever uma ou duas linhas de descrição por tema**, com exemplos do que entra. É a informação que mais ajuda tanto a máquina quanto o revisor humano.

## Do que precisamos do senhor

1. **Uma decisão sobre os temas repetidos e as "Partes":** qual versão é a oficial. Com essa resposta, várias questões que hoje vão para revisão podem ser publicadas direto.
2. **Revisar a fila.** Cada questão chega com a sugestão de tema e o motivo da dúvida. Na maioria dos casos, basta confirmar ou trocar.
3. **Uma auditoria semanal curta:** conferir cerca de 100 questões publicadas, sorteadas. É assim que sabemos se a qualidade continua acima de 95%.
4. **Cada correção sua vira aprendizado.** Com o tempo, as revisões permitem treinar um sistema mais barato, e a fila diminui.
