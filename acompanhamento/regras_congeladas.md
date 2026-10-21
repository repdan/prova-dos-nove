# Acompanhamento das pistas: regras congeladas

Congelado em 22/10/2026, na tag `grade-final` mais este diretório. A contagem
oficial começa na segunda-feira, **26/10/2026**. Nenhuma regra muda depois disso.
Se uma regra mudar, o acompanhamento recomeça do zero, porque mudar regra no meio
é ajustar ao passado.

Como rodar (MetaTrader aberto e logado; o script só lê dados, não envia ordem):

```
.venv/Scripts/python.exe -m acompanhamento.acompanhar
```

O script baixa o M1 recente, monta os dias como no backtest e roda as
estratégias. Validação feita: no período de 03/08 a 20/10/2026, ele produziu
exatamente os mesmos trades do backtest nas quatro estratégias.

## Pista 1: Grade no ouro, na abertura de Nova York

**Por que é uma pista.** No ouro, o canal marcado na abertura de NY foi o único
caso em que o método ficou acima do espelho em todos os tempos gráficos (M5 a
H1). O resultado bruto é parecido antes e depois de 2022 (+0,05 e +0,07 R),
então não depende da troca de dados da corretora.

**Contra ela.** Falhou fora da amostra nos índices americanos (US500, US30). Só
o US100 confirmou. O efeito é pequeno.

**Regras (iguais nas duas versões, exceto onde indicado):**

1. Ignora tudo antes das 16:30 do servidor (09:30 em Nova York, abertura da
   bolsa). O "dia" começa ali e termina na pausa diária do ouro.
2. Canal = máxima e mínima da **1ª vela** depois das 16:30. Largura w. A grade
   são os níveis canal ± k·w, válida até o fim do dia.
3. Tendência inicial neutra: a primeira vela que fecha fora do canal define a
   direção. Daí em diante vale a grade: NR, ZR, continuação, compra/venda no
   50%, reversão ao perder dois níveis.
4. Tudo no fechamento da vela.
5. Stop fora da zona, executado no fechamento. Alvo de 1,5 canal a partir
   da entrada. 0x0 quando fecha 1 canal além da entrada.
6. Nenhuma entrada nos 30 minutos finais do dia. O que estiver aberto fecha no
   fim do dia (sem dormir posicionado).

| Versão | Tempo gráfico | Gestão | Esperado (líquido, 2022–2026) | Trades por ano |
|---|---|---|---|---|
| **P1-A** (a sua regra) | M15 | 1 gain **ou** 2 stops encerram a **semana**; opera só de domingo a quarta (Brasília) | +0,034 R por trade | ~117 (2 por semana) |
| **P1-B** | M30 | 1 gain ou 2 stops encerram o **dia** | +0,025 R por trade | ~277 |

## Pista 2: Ichimoku classico em M15 (USDJPY e ouro)

**Por que é uma pista.** De 2022 em diante, o rompimento da nuvem em M15 passou
a continuar na direção do rompimento: +0,107 R líquido por trade no USDJPY e
+0,014 R no ouro.

**Contra ela.** Antes de 2022 o resultado era fortemente negativo. Em 2022 os
dados da corretora mudaram de natureza nos dois ativos (spread 5 a 10 vezes
menor, mais ticks por vela), então a "mudança de regime" pode ser, em parte,
mudança da fonte de preço. Além disso, "de 2022 em diante" foi escolhido depois
de olhar os dados.

**Regras:**

1. Ichimoku padrão 9 / 26 / 52, usando só a nuvem: cúmulo superior e inferior.
2. Compra quando a vela fecha acima do cúmulo superior, vindo de dentro ou de
   baixo da nuvem. Venda quando fecha abaixo do cúmulo inferior.
3. Sai quando a vela fecha além do **outro** lado da nuvem e já vira a mão.
4. Risco mínimo (para medir em R) = amplitude média das últimas 14 velas.
5. Fecha tudo no fim do dia (USDJPY: meia-noite do servidor). Nenhuma entrada
   nos 30 minutos finais.

| Versão | Esperado (líquido, 2022–2026) | Desvio por trade | Trades por ano |
|---|---|---|---|
| **P2-USDJPY** | +0,107 R | 3,26 R | ~762 |
| **P2-ouro** | +0,014 R | 2,77 R | ~774 |

O desvio alto é a cara do método: cerca de 70% dos trades perdem um pouco, e
de vez em quando um trade ganha 20, 30 ou 50 vezes o risco.

## Como ler o placar

Para cada pista, o script mostra o acumulado em R e uma **faixa esperada**:
o resultado do backtest × número de trades, ± 2 desvios. Três estados:

- **dentro do esperado**: o real é compatível com o backtest. Não confirma nada.
- **ABAIXO do esperado**: pior que o backtest além do acaso. **A pista morre.**
- **ACIMA do esperado**: melhor que o backtest. Também pede cautela.

## O limite honesto deste acompanhamento

As vantagens esperadas são tão pequenas perto da variação que **confirmar**
alguma delas exige muitos trades:

| Pista | Trades para o resultado sair do acaso (2σ) | Tempo |
|---|---|---|
| P1-A | ~3.200 | ~27 anos |
| P1-B | ~4.200 | ~15 anos |
| P2-USDJPY | ~3.700 | ~5 anos |
| P2-ouro | ~150.000 | inviável |

Então o acompanhamento serve para três coisas, nesta ordem:

1. **Matar** uma pista que esteja claramente pior que o backtest.
2. **Medir a execução real**: se você operar em demo junto, compare os seus
   trades com os do robô. Diferenças mostram o custo que o backtest não vê.
3. **Praticar** o método com disciplina, sem dinheiro em risco.

Ele **não** vai dizer, em meses, que alguma pista "funciona". Se em algum
momento parecer que sim, a pergunta certa é se a amostra já é grande o bastante
segundo a tabela acima.
