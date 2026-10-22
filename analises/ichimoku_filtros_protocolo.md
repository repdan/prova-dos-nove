# Filtros de entrada para o Ichimoku classico: protocolo fixado antes do teste

Registrado em 22/10/2026, **antes** de rodar qualquer filtro. Nada aqui muda
depois de ver resultado; se mudar, o teste recomeça com outro nome.

## Pergunta

Algum filtro de entrada melhora o Ichimoku classico em M15, sem cortar os trades
grandes que pagam o método?

## Filtros (parâmetros fixos, sem otimização)

Cada um decide, na vela do sinal e só com dados até ela, se a entrada é permitida.

| # | Filtro | Regra para comprar (vender é o espelho) | Motivo |
|---|---|---|---|
| F1 | Tendência maior | Último H1 fechado acima da nuvem do H1 | Rompimento a favor do tempo maior tende a durar mais |
| F2 | Tenkan × Kijun | Tenkan (9) acima da Kijun (26) no M15 | Confirmação clássica do Ichimoku |
| F3 | Chikou | Fechamento acima do fechamento de 26 velas atrás | Confirmação clássica do Ichimoku |
| F4 | Horário | Entrada entre 10:00 e 20:00 do servidor (Londres e NY) | Rompimento em hora de liquidez anda mais |
| F5 | Volatilidade | ATR(14) do M15 acima da mediana das últimas 20 × 96 velas | Rompimento sem volatilidade não vai longe |
| F6 | Cor da nuvem futura | Senkou A acima da Senkou B projetada (nuvem à frente "verde") | Nuvem à frente a favor da entrada |

## Etapas e critérios

1. **Descoberta: 2022–2024, ouro e USDJPY.** Antes de 2022 os dados da corretora
   têm outra natureza (ver docs/MAPA.md), então ficam de fora.
   Um filtro é **aprovado** se, nos **dois** ativos e com custo:
   - o resultado **total** por ano for maior que sem filtro; e
   - o resultado médio por trade for maior que sem filtro.
2. **Combinação:** só entre filtros aprovados, no máximo dois juntos.
3. **Confirmação, em dados não olhados:**
   - 2025–2026 em ouro e USDJPY;
   - 2022–2026 em EURUSD, GBPUSD, AUDUSD e USDCAD.

   O filtro (ou par) é **confirmado** se melhorar o total com custo em 2025–2026
   nos dois ativos **e** em pelo menos 3 dos 4 pares novos.
4. Os filtros são aplicados dentro do motor (um trade filtrado muda os seguintes),
   sempre com o espelho como controle.

## O que conta como resposta

- Nenhum aprovado ou confirmado: os perdedores do Ichimoku não são
  distinguíveis na entrada, e o método fica como está.
- Confirmado: vira uma **pista nova** (P3), congelada e com contagem própria. As
  pistas atuais não mudam.

## Desvio registrado antes do teste

O EURUSD da corretora so tem M1 real a partir de 2024 (antes, 1 vela por dia).
Nele a confirmacao usa 2024-2026. Limitacao de dado, nao escolha feita apos resultado.

