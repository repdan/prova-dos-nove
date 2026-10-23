# Pausa depois de um trade grande no Ichimoku classico: protocolo fixado antes do teste

Registrado em 23/10/2026, **antes** de rodar. Ideia do autor: depois de uma
tendência forte o mercado tende a lateralizar ("briga de preços") até tomar novo
rumo, e o Ichimoku toma stops pequenos nesse vai e vem. Nada aqui muda depois de
ver resultado; se mudar, o teste recomeça com outro nome.

## Pergunta

Ficar de fora dos próximos sinais depois de um trade grande melhora o Ichimoku
classico em M15?

## Duas partes

1. **A premissa, descritiva (sem regra nova):** no Ichimoku classico, qual o R médio
   do 1º, 2º e 3º trade depois de um trade de ≥ 3 R e de ≥ 5 R, comparado com a
   média de todos? Se a premissa estiver certa, eles ficam claramente abaixo da
   média (e abaixo de zero com custo).
2. **A regra, dentro do motor:** depois que um trade fecha com resultado ≥ X R,
   os próximos N sinais que virariam entrada são ignorados. Saídas nunca são
   bloqueadas. Grade fixa, 6 variantes, sem otimização:
   - X ∈ {3, 5} R;
   - N ∈ {1, 2, 3} sinais.

## Critérios (os mesmos dos filtros de entrada)

1. **Descoberta: 2022–2024, ouro e USDJPY.** Uma variante é **aprovada** se, nos
   **dois** ativos e com custo, melhorar o total por ano **e** o R por trade.
2. **Confirmação, em dados não olhados:** 2025–2026 em ouro e USDJPY;
   EURUSD (2024–2026), GBPUSD, AUDUSD e USDCAD (2022–2026). **Confirmada** se
   melhorar o total com custo em 2025–26 nos dois ativos **e** em pelo menos 3
   dos 4 pares novos.
3. Se mais de uma variante for aprovada, todas vão para a confirmação; para virar
   pista, vale a confirmada com menor N (menos regra).

## Cuidado registrado antes

Nos pares em que o Ichimoku sem regra **perde**, qualquer regra que corte trades
perde menos. Por isso a aprovação exige melhora no ouro e no USDJPY, e o R por
trade é olhado junto com o total.

## O que conta como resposta

- Nenhuma aprovada ou confirmada: os trades depois de uma tendência não são
  piores que os outros, e o método fica como está.
- Confirmada: vira uma **pista nova** (P3), congelada e com contagem própria. As
  pistas atuais não mudam.
