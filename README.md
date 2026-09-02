# HK50 Bot — Backtest e Otimização de Estratégia de Rompimento de Canal

Projeto de **backtest e pesquisa**, sem execução ao vivo. Roda 100% offline sobre
dados históricos puxados do MetaTrader 5.

- **Ativo:** HK50 (índice Hang Seng) — corretora corretora, plataforma MT5
- **Timeframe prioritário:** M15 (M5 coletado em paralelo, backtestado depois)
- **Sessão:** apenas pregão regular de Hong Kong — 09:15–12:00 e 13:00–16:30 (UTC+8)

---

## Instalação

```bash
cd C:\dev\hk50-bot
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

O ambiente virtual já está criado com Python 3.12.10 oficial (python.org).
Não use o Python da Microsoft Store: ele roda em sandbox e conflita com a
biblioteca MetaTrader5.

## Como rodar a Etapa 1 (coleta)

**Antes de rodar**, no MetaTrader 5:

1. Abra o terminal e **faça login** na conta.
2. `Ferramentas > Opções > Gráficos > Máx. barras no gráfico` → **Ilimitado**.
3. Abra o gráfico do HK50 em M15 e em M5 e **role para trás até o início** do
   histórico (ou use `Exibir > Símbolos > HK50 > Barras > baixar`).
   O terminal só entrega pelo Python o que ele já baixou — sem esse passo você
   coleta poucos meses e nem percebe.

Depois:

```bash
.venv\Scripts\python.exe coletar.py
```

Saída em `data/historico/`:

| Arquivo | Conteúdo |
|---|---|
| `HK50_M15_bruto.parquet` | tudo que o terminal devolveu, nada removido |
| `HK50_M15_pregao.parquet` | **só pregão regular, limpo — é o que o backtest usa** |
| `HK50_M15_pregao_amostra.csv` | últimas 500 linhas, para conferir a olho |
| `metadados_coleta.json` | período coberto, fuso do servidor, spec do contrato, qualidade |

## Testes

```bash
.venv\Scripts\python.exe -m pytest tests/ -q
```

Os testes usam candles sintéticos e **não precisam do MT5 aberto**. Validam
inferência de fuso, filtro de pregão, limpeza e detecção de buracos.

---

## Decisões técnicas que valem explicar

### Fuso horário do servidor é inferido, não chutado
O MT5 devolve o horário do **servidor da corretora**, que não é UTC nem o seu
horário local. Errar isso desloca toda a análise por horário do dia — que é
justamente uma das saídas da Etapa 4.

Em vez de pedir o número, o script testa cada offset de UTC−12 a UTC+14 e fica
com aquele que joga a maior fração do volume negociado para dentro do pregão de
Hong Kong. É auto-corretivo e reporta a confiança da escolha.

### Buraco de dado ≠ mercado fechado
Cada candle é marcado com a sessão a que pertence (`sessao_id`). Só conta como
buraco a ausência de candles **dentro do mesmo bloco contínuo** (mesmo dia,
mesma sessão). A pausa do almoço e a virada de dia são troca de bloco, não falha
de download. Isso funciona para qualquer timeframe sem ajuste.

### Nada é apagado em silêncio
Toda linha removida vai para o relatório de qualidade com o motivo, e o arquivo
`_bruto` guarda o original intacto.

---

## Estado das etapas

| Etapa | Status |
|---|---|
| 1 — Coleta e tratamento de dados | ✅ implementada, testada, aguardando execução com MT5 aberto |
| 2 — Estratégia de canal (plugin) | ⬜ não iniciada |
| 3 — Engine de backtest event-driven | ⬜ não iniciada |
| 4 — Camada de machine learning | ⬜ não iniciada |
| 5 — Relatório final | ⬜ não iniciada |

---

## Fora de escopo nesta fase (Fase 2)

Registrado aqui para não se perder:

- **Gestão de risco de 2% do capital por dia** e **position sizing real.**
  O backtest usa lote fixo (`estrategia.lote`, padrão 0.1). Não há capital real
  definido na simulação, então limite diário e cálculo de lote como % do capital
  ficam para quando entrar dinheiro de verdade.
- **Execução ao vivo.** As interfaces `DataFeed` e `Executor` (Etapa 3) já
  nascem desenhadas para o encaixe futuro de `mt5.order_send()`, mas nenhuma
  ordem é enviada neste projeto.

### Aviso sobre a estratégia base: ela não tem stop loss

A regra base é *stop-gain* — a posição só fecha no rompimento da média oposta.
Isso significa que a perda de um trade é **ilimitada** até o próximo candle.
Num gap de abertura ou evento rápido, o prejuízo pode ser muito maior do que
qualquer trade do backtest sugere.

A regra base **não será alterada** (é o baseline que o projeto quer medir), mas:
- a engine reporta a **perda máxima por trade** como métrica de primeira classe;
- existe um `stop_catastrofico_ativo` no config, **desligado por padrão**, para
  medir quanto custaria ter uma rede de segurança.

### Retreino do modelo (Etapa 4)

O modelo de ML **não deve ser treinado uma vez e usado para sempre** — o
comportamento do mercado muda. Cadência recomendada: **retreino mensal**, com a
mesma janela de walk-forward usada na validação. A validação reporta a
performance de **cada janela de teste separadamente**, não só a média, para
deixar visível se o modelo é consistente ou só teve sorte num período.
