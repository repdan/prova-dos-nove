# Prova dos nove

Toda ideia passa pela prova antes de valer. Laboratório para testar estratégias de trading com rigor: backtest com custo
real, controle espelho, protocolos registrados antes do teste e validação fora
da amostra. Inclui acompanhamento de pistas congeladas e um robô para
MetaTrader 5 que opera só em conta demo.

> **Aviso.** Projeto de estudo, não recomendação de investimento. Até aqui,
> **nenhuma estratégia sobreviveu** a custo real e teste fora da amostra. O robô
> recusa conta real e tem o lote travado no mínimo.

---

## O que já foi testado

Rompimento de canal, reversão à média, trend following em carteira, a grade de
níveis (HK50, ouro, índices) e o Ichimoku, com dezenas de variações de gestão,
canal, tempo gráfico e filtro de entrada. O padrão que se repete:

- o sinal bruto fica entre 0 e 0,05 R por trade;
- o custo come de 0,02 R (H1) a 0,17 R (M1) por trade;
- acerto alto costuma vir da geometria stop/alvo: o espelho (as mesmas entradas
  no sentido oposto) acerta igual.

A tabela completa, com veredito e o script de cada teste, está em
[`docs/MAPA.md`](docs/MAPA.md). **Comece por ela.**

## Método

Cada ideia passa pelas mesmas etapas antes de valer alguma coisa:

1. **Custo real**: spread, deslize, comissão e swap medidos na corretora.
2. **Espelho**: se as entradas invertidas também ganham, o mérito é da
   geometria stop/alvo, não da entrada.
3. **Protocolo antes do teste**: regra, parâmetros e critério de aprovação ficam
   num arquivo commitado antes de rodar (ex.:
   [`analises/ichimoku_filtros_protocolo.md`](analises/ichimoku_filtros_protocolo.md)).
4. **Fora da amostra**: escolhe num período e mede noutro, ou em outros mercados.
5. **Congelar**: o que sobra vira uma pista com regras fixas e passa a ser
   acompanhada contra o esperado do backtest. Ideia nova vira pista nova, nunca
   ajuste de uma antiga.

## As quatro estratégias em acompanhamento

São duas famílias, cada uma em dois ativos ou tempos gráficos. Elas sobraram
como **pistas fracas**: positivas no backtest com custo, mas sem confirmação
estatística. Por isso foram congeladas e passaram a ser acompanhadas contra o
esperado. As regras completas estão em
[`acompanhamento/regras_congeladas.md`](acompanhamento/regras_congeladas.md).

### Família 1: Grade de níveis presa ao canal de abertura

O método vira uma máquina de estados sobre uma grade:

- **Canal:** topo e fundo das primeiras velas depois da abertura de Nova York.
  A largura do canal define o espaçamento da grade, que se repete para cima e
  para baixo.
- **Estado:** o canal de referência é o nível onde o preço fechou; a zona
  neutra é o nível logo atrás dele.
- **Entradas, sempre no fechamento do candle:**
  - continuação: o preço fecha além do canal de referência;
  - retomada: visita a zona de recuo e volta a fechar além do meio do canal;
  - reversão: fecha além da zona de recuo, contra a tendência.
- **Saída:**
  - stop do outro lado da zona de recuo;
  - alvo a um número fixo de níveis;
  - depois de um nível a favor, o stop vai para o preço de entrada.
- **Gestão:** encerra o período ao bater o alvo. Depois de um stop, continua
  operando até um limite de perdas.

| Pista | Ativo | Tempo gráfico | Gestão |
|---|---|---|---|
| P1-A | Ouro | M15 | Semanal: opera só no começo da semana; 1 ganho ou o limite de stops encerra a semana |
| P1-B | Ouro | M30 | Diária |

### Família 2: Ichimoku clássico (só a nuvem)

- **Nuvem:** a padrão do Ichimoku, projetada para a frente, calculada só com
  dados passados.
- **Entrada:** compra quando o candle fecha acima da nuvem, vende quando fecha
  abaixo.
- **Saída:** quando o preço fecha do outro lado da nuvem, e a posição já vira.
- **Fim do dia:** não carrega posição de um dia para o outro.
- **Risco mínimo:** o stop tem um piso proporcional à amplitude recente, para
  que uma nuvem muito fina não gere um risco quase zero e resultados absurdos
  em R.

O perfil é o de seguir tendência: muitos stops pequenos e poucos ganhos muito
grandes. Cerca de 5% dos trades passam de 5 R e pagam o resto.

| Pista | Ativo | Tempo gráfico |
|---|---|---|
| P2-USDJPY | USDJPY | M15 |
| P2-ouro | Ouro | M15 |

### O placar

[`acompanhamento/acompanhar.py`](acompanhamento/acompanhar.py) roda as quatro
pistas nos dados novos e compara o resultado acumulado com uma faixa de ±2
desvios em torno do esperado do backtest:

- abaixo da faixa: a pista é descartada;
- dentro da faixa: segue em observação;
- acima: é acompanhada com mais atenção.

Confirmar uma vantagem tão pequena leva anos de trades. O placar existe
principalmente para **matar** cedo o que piorar além do acaso.

## Como o robô roda

[`execucao/robo_demo.py`](execucao/robo_demo.py) opera as quatro pistas ao
mesmo tempo no MetaTrader 5.

```
a cada minuto
  ├─ lê as velas de M1 recentes do MT5 e monta os candles de cada pista
  ├─ descarta a vela ainda em formação
  ├─ roda o MESMO simulador do backtest em modo ao vivo
  │     → "que posição esta estratégia deveria ter agora?"
  ├─ alinha a conta com essa resposta
  │     abre · fecha · move o stop para a entrada · nunca entra atrasado
  └─ imprime um bloco por vela e registra cada ação no diário
```

- **Uma única fonte de verdade:** o robô não reimplementa as regras. Ele chama
  o mesmo código do backtest, e
  [`tests/test_ao_vivo.py`](tests/test_ao_vivo.py) prova, vela a vela, que as
  decisões ao vivo são idênticas às do backtest.
- **Estado persistente:** as entradas já feitas ou perdidas ficam em
  `estado.json`, para que um reinício não duplique nem invente posições.
- **Stop de proteção no servidor:** cada ordem sai com um stop largo na
  corretora, que protege a conta se o robô ou o PC cair.
- **Diário de execução:** cada ação vai para `diario.csv` com o preço do
  backtest, o preço executado e o spread do momento. É isso que mede o custo
  real e o deslize.
- **Dois modos:** simulação (padrão, não envia nada) e `--valendo` (envia ordens
  na conta demo).
- **Travas:**
  - recusa conta real;
  - lote fixo no mínimo, com recusa de qualquer volume acima;
  - limite de perda diária;
  - zera tudo antes do fim do dia;
  - para com segurança ao criar um arquivo `execucao/PARAR`.

Guia de uso em [`execucao/LEIA.md`](execucao/LEIA.md); atalhos de duplo clique
em [`atalhos/COMANDOS.md`](atalhos/COMANDOS.md).

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `strategy/` | Estratégias: `grade.py`, `grade_gap.py`, `ichimoku.py` (com modo ao vivo) e as antigas |
| `backtest/` | Motores antigos (intradiário HK50, carteira diária) |
| `analises/` | Um script por teste, coletores de dados e protocolos; saída em `reports/*.txt` |
| `acompanhamento/` | Pistas congeladas, regras e placar contra o esperado |
| `execucao/` | Robô da conta demo ([`LEIA.md`](execucao/LEIA.md)) |
| `atalhos/` | Atalhos `.bat` de duplo clique ([`COMANDOS.md`](atalhos/COMANDOS.md)) |
| `tests/` | Testes; `test_ao_vivo.py` garante que o robô decide igual ao backtest, vela a vela |

## Como rodar

**Requisitos:** Windows, Python 3.12 do python.org (o da Microsoft Store
conflita com a biblioteca `MetaTrader5`) e o terminal MetaTrader 5 aberto e
logado. O login é feito no terminal; o projeto nunca lida com senha.

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest tests -q
```

Os testes usam velas sintéticas. Os poucos que precisam de dados reais são
pulados quando os dados não existem.

### Dados

Nenhum dado de preço vai para o git: são da corretora e pesam centenas de MB.
Os coletores recriam tudo a partir do terminal MT5 (antes, role o gráfico até o
início do histórico, porque o terminal só entrega o que já baixou):

```bash
.venv\Scripts\python.exe analises\coletar_ouro_grade.py
.venv\Scripts\python.exe analises\coletar_m1_hk50.py
.venv\Scripts\python.exe analises\coletar_m1_dias.py US500 US100 US30
```

Armadilhas conhecidas dos dados (troca de fonte da corretora em 2022, histórico
esparso, relógio do servidor) estão no [`MAPA`](docs/MAPA.md#3-armadilhas-dos-dados).

### Um teste, o placar, o robô

```bash
.venv\Scripts\python.exe -m analises.ichimoku_filtros       # um estudo
.venv\Scripts\python.exe -m acompanhamento.acompanhar       # placar das pistas
.venv\Scripts\python.exe -m execucao.robo_demo              # robô em simulação
.venv\Scripts\python.exe -m execucao.robo_demo --valendo    # robô enviando ordens na DEMO
```

Travas do robô:

- só roda em conta **demo**; em conta real, recusa e sai;
- lote fixo em 0,01;
- para no limite de perda diária;
- zera tudo no fim do dia;
- para com segurança ao criar um arquivo `execucao/PARAR`.

## Linha do tempo

Tags no git, da mais antiga à mais nova:

1. `hk50-final`: rompimento de canal no HK50 M15. O README daquela fase tem a
   coleta, os fusos e os custos medidos.
2. `grade-hk50-final`: a grade de níveis no HK50.
3. `grade-final`: Grade no ouro e nos índices.
4. `acompanhamento-v1`: pistas congeladas e robô da demo.
