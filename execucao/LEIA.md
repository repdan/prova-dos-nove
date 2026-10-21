# Robô da conta demo

Opera as pistas congeladas (`acompanhamento/regras_congeladas.md`) na conta
demo, com lote 0,01. Não tem lógica própria: roda o mesmo código do backtest
no modo ao vivo, conferido vela a vela em `tests/test_ao_vivo.py`.

## Antes de ligar

1. **MetaTrader aberto e logado na conta demo.** Em conta real, o robô se recusa a rodar.
2. **Botão "Algo Trading" ligado** na barra do MetaTrader (fica verde). Sem ele,
   as ordens são recusadas, mesmo no modo de envio.
3. **PC sem suspender.** Em Configurações > Sistema > Energia, deixe "suspender"
   como "Nunca" enquanto o robô estiver ligado.

## Ligar

Primeiro um dia só em **simulação**, para ver o que ele faria sem enviar nada:

```
.venv/Scripts/python.exe -m execucao.robo_demo
```

Depois, **enviando ordens para a demo**:

```
.venv/Scripts/python.exe -m execucao.robo_demo --valendo
```

Deixe o terminal aberto. Ele avalia uma vez por minuto, poucos segundos depois
de cada vela fechar.

## Desligar

- **Com segurança:** crie um arquivo vazio chamado `PARAR` dentro desta pasta.
  O robô zera as posições dele e encerra.
- **Ctrl+C:** encerra na hora. Posições abertas ficam com o stop de proteção.

## O que ele faz sozinho

| Situação | Ação |
|---|---|
| A estratégia entra na vela que acabou de fechar | Abre 0,01 com stop de proteção (2× o risco) e o alvo, quando há |
| A estratégia já estava posicionada antes de o robô ligar | **Não entra atrasado**, só registra |
| A estratégia sai (stop por fechamento, alvo, virada de mão) | Zera a mercado |
| A estratégia vai para o 0x0 | Move o stop para a entrada |
| 23:57 do servidor | Zera tudo (fim do dia; às 00:00 o ouro entra em pausa) |
| Perda de 3% no dia | Zera tudo e pausa até o dia seguinte |

Cada pista tem um número próprio na coluna "Mágico" do MetaTrader:
P1-A 51001, P1-B 51002, P2-USDJPY 52001, P2-ouro 52002.

## O que olhar

- `diario.csv`: cada ação, com o preço que o backtest usaria e o preço
  executado. A coluna `diferenca` é o custo real de execução.
- `robo.log`: tudo o que o robô decidiu e por quê.
- O placar contra o backtest continua no acompanhamento:
  `.venv/Scripts/python.exe -m acompanhamento.acompanhar`

## Tamanho do risco

Com 0,01 lote, cada trade arrisca pouco perto dos 10 mil dólares:

| Pista | Risco típico por trade | Trades por semana |
|---|---|---|
| P1-A (ouro M15) | 10 a 30 dólares | ~2 |
| P1-B (ouro M30) | 10 a 30 dólares | ~5 |
| P2-ouro (Ichimoku M15) | 3 a 10 dólares | ~15 |
| P2-USDJPY (Ichimoku M15) | menos de 1 dólar | ~15 |

Os números de resultado que importam estão em R (múltiplos do risco), não em
dólares: o lote fixo de 0,01 não representa 1% da conta em nenhuma das pistas.
