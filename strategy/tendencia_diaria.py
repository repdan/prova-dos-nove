"""
Trend following classico, em grafico diario.

Esta e a versao da estrategia que tem evidencia publica de decadas - a mesma
familia usada por fundos CTA desde os anos 70 e documentada nos Turtle Traders.
As diferencas em relacao ao que testamos ate aqui nao sao cosmeticas:

  horizonte   dias a meses, nao horas. O custo por giro cai de 12-25% de um
              candle para 2-3%.
  canal       Donchian - MAIOR maxima e MENOR minima da janela, nao a media.
              E o que a literatura descreve e testa.
  saida       canal oposto MAIS CURTO que o de entrada. Entra com 55 dias, sai
              com 20. Assim o trade so encerra quando a tendencia realmente
              virou, e nao a cada respiro.
  stop        2 x ATR, obrigatorio. Em D1 um trade pode andar semanas contra.
  carteira    o resultado vem de operar dezenas de mercados descorrelacionados.
              Nenhum ativo isolado justifica a estrategia.

O ponto que mais importa e o ultimo. Testar esta estrategia num ativo so e
medir a coisa errada: ela nao promete acertar um mercado, promete que a soma
de muitos apostas independentes tem esperanca positiva.
"""

from __future__ import annotations

from typing import Any

from strategy.base import Candle, DecisaoSaida, Direcao, Estrategia, Posicao, Sinal
from strategy.indicadores import ATR, Extremo
from strategy.stops import Stop


class TendenciaDiaria(Estrategia):
    """Rompimento de canal de Donchian com saida por canal curto e stop em ATR."""

    nome = "tendencia_diaria"

    def __init__(
        self,
        periodo_entrada: int = 55,
        periodo_saida: int = 20,
        periodo_atr: int = 20,
        stop_mult_atr: float = 2.0,
        lote: float = 0.01,          # ignorado pela carteira, que dimensiona por risco
        so_a_favor_da_tendencia_longa: int | None = None,
    ):
        self.periodo_entrada = periodo_entrada
        self.periodo_saida = periodo_saida
        self.lote = lote
        # Filtro opcional: so compra se o preco estiver acima da media de N dias.
        # E o jeito classico de evitar comprar rompimento contra a mare grande.
        self.so_a_favor = so_a_favor_da_tendencia_longa

        self._alta_entrada = Extremo(periodo_entrada, maior=True)
        self._baixa_entrada = Extremo(periodo_entrada, maior=False)
        self._alta_saida = Extremo(periodo_saida, maior=True)
        self._baixa_saida = Extremo(periodo_saida, maior=False)
        self._atr = ATR(periodo_atr)
        self.stop = Stop("atr", mult_atr=stop_mult_atr)

        self._soma_longa = 0.0
        self._fechamentos: list[float] = []
        self._cache_tempo: Any = None
        self._cache: dict[str, float | None] = {}

    # ------------------------------------------------------------------ util

    def _niveis(self, candle: Candle) -> dict[str, float | None]:
        """Congela os niveis do candle atual - lidos ANTES de absorve-lo."""
        if self._cache_tempo != candle.tempo:
            self._cache_tempo = candle.tempo
            self._cache = {
                "alta_entrada": self._alta_entrada.valor,
                "baixa_entrada": self._baixa_entrada.valor,
                "alta_saida": self._alta_saida.valor,
                "baixa_saida": self._baixa_saida.valor,
                "atr": self._atr.valor,
                "media_longa": (self._soma_longa / len(self._fechamentos)
                                if self._fechamentos else None),
            }
        return self._cache

    def _absorver(self, candle: Candle) -> None:
        self._alta_entrada.atualizar(candle.maxima)
        self._baixa_entrada.atualizar(candle.minima)
        self._alta_saida.atualizar(candle.maxima)
        self._baixa_saida.atualizar(candle.minima)
        self._atr.atualizar(candle.maxima, candle.minima, candle.fechamento)

        if self.so_a_favor:
            self._fechamentos.append(candle.fechamento)
            self._soma_longa += candle.fechamento
            if len(self._fechamentos) > self.so_a_favor:
                self._soma_longa -= self._fechamentos.pop(0)

    def pronta(self) -> bool:
        return self._alta_entrada.cheia and self._atr.cheia

    @property
    def atr_atual(self) -> float | None:
        return self._atr.valor

    # -------------------------------------------------------------- entrada

    def on_candle(self, candle: Candle) -> Sinal:
        n = self._niveis(candle)
        sinal = Sinal.NENHUM

        if self.pronta() and n["alta_entrada"] is not None:
            # Rompimento pelo FECHAMENTO: exigir que o dia feche fora do canal
            # evita o pavio que fura e volta - em D1 isso e comum em noticia.
            acima = candle.fechamento > n["alta_entrada"]
            abaixo = candle.fechamento < n["baixa_entrada"]

            permite_compra = permite_venda = True
            if self.so_a_favor and n["media_longa"] is not None:
                permite_compra = candle.fechamento > n["media_longa"]
                permite_venda = candle.fechamento < n["media_longa"]

            if acima and permite_compra:
                sinal = Sinal.COMPRA
            elif abaixo and permite_venda:
                sinal = Sinal.VENDA

        self._absorver(candle)
        return sinal

    def armar_stop(self, posicao: Posicao, candle: Candle) -> None:
        nivel = self.stop.nivel_inicial(posicao, candle, self._niveis(candle)["atr"], None)
        posicao.estado["nivel_stop"] = nivel
        posicao.estado["stop_inicial"] = nivel

    def checar_stop(self, posicao: Posicao, candle: Candle) -> DecisaoSaida:
        nivel = posicao.estado.get("nivel_stop")
        if not self.stop.foi_atingido(posicao, candle, nivel):
            return DecisaoSaida(sair=False)
        return DecisaoSaida(sair=True, motivo="stop",
                            preco_sugerido=self.stop.preco_de_execucao(
                                posicao, candle, nivel))

    # ---------------------------------------------------------------- saida

    def deve_sair(self, posicao: Posicao, candle: Candle) -> DecisaoSaida:
        n = self._niveis(candle)
        if n["alta_saida"] is None:
            return DecisaoSaida(sair=False)

        # Canal de saida mais curto que o de entrada: e o que deixa o trade
        # respirar durante a tendencia e o encerra quando ela vira.
        if posicao.direcao is Direcao.COMPRADO:
            if candle.fechamento < n["baixa_saida"]:
                return DecisaoSaida(sair=True, motivo="canal_de_saida")
        elif candle.fechamento > n["alta_saida"]:
            return DecisaoSaida(sair=True, motivo="canal_de_saida")
        return DecisaoSaida(sair=False)

    def contexto_atual(self) -> dict[str, Any]:
        n = dict(self._cache)
        return {k: v for k, v in n.items() if v is not None}
