# Mapa do projeto

Ponto de entrada para quem chega (inclusive o Claude numa conversa nova).
Atualizado em 22/10/2026.

## 1. O que está rodando agora

| O quê | Onde | Estado |
|---|---|---|
| Acompanhamento das pistas (placar contra o backtest) | `acompanhamento/` | Congelado em 22/10/2026, contagem oficial desde **26/10/2026** |
| Robô da conta demo (lote 0,01, só demo) | `execucao/robo_demo.py` | Em simulação; o autor liga o modo `--valendo` |
| Atalhos de duplo clique | `atalhos/` | Guia em `atalhos/COMANDOS.md` |

**Pistas congeladas** (regras em `acompanhamento/regras_congeladas.md`):

| Pista | O quê | Esperado (líquido, 2022–2026) |
|---|---|---|
| P1-A | Grade, ouro, abertura NY, M15, canal na 1ª vela, gestão semanal dom–qua | +0,034 R/trade, ~2 trades/semana |
| P1-B | Grade, ouro, abertura NY, M30, gestão diária | +0,025 R/trade |
| P2-USDJPY | Ichimoku classico M15 | +0,107 R/trade (só existe de 2022 em diante) |
| P2-ouro | Ichimoku classico M15 | +0,014 R/trade |

Nenhuma é confirmada: confirmar levaria de 5 a 27 anos de trades. O
acompanhamento serve para **matar** uma pista que piore além do acaso e para
medir a execução real.

## 2. O que já foi testado (e o veredito)

Antes de testar algo, confira aqui. "R" = múltiplo do risco; "espelho" = mesmas
entradas no sentido oposto (controle).

| Linha | Veredito | Número-chave | Onde |
|---|---|---|---|
| Rompimento de canal no HK50 M15 | Só funcionou numa janela de 2 anos; custo de 22% de um candle | tag `hk50-final` | `rodar_backtest.py` |
| Reversão à média (ouro, EURUSD) | Mecanismo coerente, edge decai a zero | — | `strategy/reversao_media.py` |
| Trend following diário em carteira (26 mercados) | −0,167 R/trade; universo da corretora não comporta | 3,7σ negativo | `rodar_carteira.py` |
| Grade no HK50 M5 | 60% de acerto, bruto zero; o espelho também acerta 60% | −0,085 R líquido | `rodar_grade.py` |
| Grade no HK50 M1 | Sinal fraco real, mas +0,3 pt bruto contra 6,3 pt de custo | −0,094 R líquido | `rodar_grade.py M1` |
| Gestão do autor (1 gain, 2 stops, alvo 1,5 canal, 0x0) | Muda o acerto, não a esperança | −0,089 R | `analises/grade_regras_autor.py` |
| Canal de 4 velas mirando 40–60 pts | Igual ao canal da 1ª vela | — | `analises/grade_canal_autor.py` |
| Primeira vela pequena = lateralidade | Prevê dia **menor**, não dia **lateral** | correlação −0,05 | idem |
| Evitar a primeira ordem do dia | Ruído: muda de sinal conforme o canal | — | `analises/grade_primeira_ordem.py` |
| Operar só o gap (fechamento) | Pior; o espelho ganha | — | `analises/grade_so_gap.py` |
| A favor do gap | +0,086 R no HK50, **falhou fora da amostra** (FR40, ES35, CN50) | — | `analises/gap_fora_da_amostra.py` |
| Grade no ouro M1 | Perde antes do custo | custo 0,07–0,17 R | `analises/grade_ouro.py` |
| Grade no ouro M15 | Zero, exceto abertura de NY (levemente +) | NY +0,016 R | idem |
| Tempo gráfico maior (M1 a H1) | Custo cai, sinal não cresce | líquido ~0 | `analises/grade_tempo_grafico.py` |
| Abertura de NY fora da amostra (US500, US100, US30) | Só o US100 confirma; critério fixado falhou | — | `analises/grade_ny_fora_da_amostra.py` |
| Gestão semanal no ouro | Mais semanas positivas, mesmo resultado por trade | — | `analises/grade_ouro_semanal.py` |
| Carregar a posição para o dia seguinte | Pior com alvo; sem alvo, o espelho ganha junto | −0,17 a −0,26 R | `analises/grade_ouro_carregar.py` |
| Canal semanal (montado na segunda) | Não melhora o diário | — | `analises/grade_canal_semanal.py` |
| Ichimoku de referencia (classico e adaptaçãa grade) | Sem resultado líquido no período completo | — | `analises/ichimoku_referencia.py` |
| Ichimoku: sair na reentrada da nuvem | Pior que o classico (corta os ganhos grandes) | — | `analises/ichimoku_saida_reentrada.py` |
| Ichimoku: 6 filtros de entrada (protocolo registrado antes) | Nenhum aprovado: o que ajuda o ouro atrapalha o USDJPY; filtros cortam os trades grandes na mesma proporção | — | `analises/ichimoku_filtros.py` |
| Ichimoku: melhor filtro escolhido por ativo (ouro com F2, USDJPY sem) | Ouro com F2 em 2025–26: +6,5 R/ano contra +80,5 sem filtro. Escolher por ativo acertou 3 de 6 (cara ou coroa); onde "acertou", o método sem filtro perdia e o filtro só reduziu o número de trades | — | `analises/ichimoku_filtro_por_ativo.py` |
| Ichimoku: pausa de 1–3 sinais depois de trade ≥ 3 R ou ≥ 5 R (protocolo registrado antes) | Nenhuma aprovada. O trade logo depois de um grande tem o R médio de qualquer outro; os desvios trocam de sinal entre períodos | — | `analises/ichimoku_pausa.py` |

## 3. Armadilhas dos dados

- **Em 2022 a corretora mudou a fonte de preço** do ouro e do USDJPY (spread 5 a
  10 vezes menor, mais ticks por vela). Comparar antes e depois de 2022 pode
  medir a corretora, não o mercado.
- HK50 antes de 2022 e ouro em 2017–2018: histórico esparso.
- Spread histórico do ouro é zero antes de 2019: use o spread ao vivo (0,21).
- Arquivos de M1 não vão para o git (centenas de MB); os coletores em
  `analises/coletar_*` recriam.
- "Dia" do ouro = bloco da corretora, 01:00–23:59 do servidor; no relógio da
  estratégia (`tempo_ativo`) fica 1 h antes.
- USDJPY: os "dias" do coletor são semanas; em ~1 a cada 7 semanas o bloco abre
  às 00:05 e as velas de M15 ficam deslocadas 5 min em relação ao MetaTrader.

## 4. Onde está cada coisa

| Pasta | Conteúdo |
|---|---|
| `strategy/` | Estratégias: `grade.py` (com modo ao vivo), `grade_gap.py`, `ichimoku.py`, e as antigas |
| `backtest/` | Motores antigos (HK50 intradiário, carteira diária) |
| `analises/` | Cada teste é um script; resultados em `reports/*.txt` |
| `acompanhamento/` | Pistas congeladas e placar |
| `execucao/` | Robô da demo (`LEIA.md`) |
| `tests/` | 100 testes; `test_ao_vivo.py` garante que o robô = backtest |

Linha do tempo no git: `hk50-final` → `grade-hk50-final` → `grade-final` →
`acompanhamento-v1` (branch `grade-hk50`).
