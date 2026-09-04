"""
Estrategia de reversao a media.

E o espelho da de rompimento, e existe por causa de uma pista que os proprios
dados deram: no ouro e no EURUSD o rompimento perde no BRUTO, antes de
qualquer custo. Perder consistentemente no bruto significa que o preco faz o
contrario do que a estrategia aposta - ele volta em vez de seguir. Se e assim,
apostar na volta e a leitura correta daquele mercado.

  ROMPIMENTO  entra quando o preco SAI do canal, apostando que vai continuar
  REVERSAO    entra quando o preco esta FORA do canal, apostando que vai voltar

ENTRADA
  O preco fecha fora do canal por uma margem minima (em multiplos de ATR, para
  se ajustar a volatilidade do momento). Fechou abaixo da banda inferior por
  margem suficiente -> COMPRA, apostando na volta. Acima da superior -> VENDA.

  A margem minima existe para nao comprar todo tostao de excesso. Sem ela a
  estrategia entra em qualquer roce na banda, que e ruido e nao exagero.

SAIDA
  O preco volta ao MEIO do canal. E o alvo natural: se a tese e "esticou
  demais e vai voltar", a tese se cumpre quando ele volta ao normal, nao
  quando atravessa para o outro extremo.

  Diferenca importante em relacao ao rompimento: aqui o alvo e proximo e o
  risco e o que fica aberto. Por isso esta estrategia PRECISA de stop - e o
  espelho da outra, que precisava deixar o ganho correr.
"""

from __future__ import annotations

from typing import Any

from strategy.base import Candle, DecisaoSaida, Direcao, Estrategia, Posicao, Sinal
from strategy.canal_rompimento import Canal, PosicaoNoCanal
from strategy.indicadores import ATR, Extremo, MediaMovel
from strategy.stops import Stop


class ReversaoMedia(Estrategia):
    """Compra o exagero para baixo, vende o exagero para cima."""

    nome = "reversao_media"

    def __init__(
        self,
        periodo_canal: int,
        lote: float,
        margem_atr: float = 0.5,
        alvo: str = "meio",
        tipo_canal: str = "media",
        periodo_atr: int = 14,
        tipo_stop: str = "atr",
        stop_mult_atr: float = 3.0,
        stop_folga_atr: float = 0.25,
        stop_breakeven_atr: float | None = None,
        max_candles_no_trade: int | None = None,
    ):
        self.periodo_canal = periodo_canal
        self.lote = lote
        # Quanto o preco precisa exceder a banda para o exagero contar.
        self.margem_atr = margem_atr
        # "meio" = volta ao centro do canal; "banda" = volta so ate a banda.
        self.alvo = alvo
        self.max_candles_no_trade = max_candles_no_trade
        self.stop = Stop(tipo_stop, stop_mult_atr, stop_folga_atr, stop_breakeven_atr)

        if tipo_canal == "media":
            self._sup: Any = MediaMovel(periodo_canal)
            self._inf: Any = MediaMovel(periodo_canal)
        elif tipo_canal == "donchian":
            self._sup = Extremo(periodo_canal, maior=True)
            self._inf = Extremo(periodo_canal, maior=False)
        else:
            raise ValueError(f"tipo_canal invalido: {tipo_canal!r}")

        self._atr = ATR(periodo_atr)
        self._cache_tempo: Any = None
        self._cache_canal: Canal | None = None
        self._candles_vistos = 0

    # ------------------------------------------------------------------ util

    def _canal_para(self, candle: Candle) -> Canal | None:
        """Canal formado pelos candles ANTERIORES - mesma garantia da outra."""
        if self._cache_tempo != candle.tempo:
            self._cache_tempo = candle.tempo
            sup, inf = self._sup.valor, self._inf.valor
            self._cache_canal = (Canal(superior=sup, inferior=inf)
                                 if sup is not None and inf is not None else None)
        return self._cache_canal

    def _absorver(self, candle: Candle) -> None:
        self._sup.atualizar(candle.maxima)
        self._inf.atualizar(candle.minima)
        self._atr.atualizar(candle.maxima, candle.minima, candle.fechamento)
        self._candles_vistos += 1

    def pronta(self) -> bool:
        return self._sup.cheia and self._atr.cheia

    # -------------------------------------------------------------- entrada

    def on_candle(self, candle: Candle) -> Sinal:
        canal = self._canal_para(candle)
        atr = self._atr.valor
        sinal = Sinal.NENHUM

        if canal is not None and atr and self.pronta():
            margem = self.margem_atr * atr
            if candle.fechamento < canal.inferior - margem:
                sinal = Sinal.COMPRA        # esticou para baixo, aposta na volta
            elif candle.fechamento > canal.superior + margem:
                sinal = Sinal.VENDA

        self._absorver(candle)
        return sinal

    def armar_stop(self, posicao: Posicao, candle: Candle) -> None:
        canal = self._canal_para(candle)
        # O "canal oposto" de uma reversao e a banda do lado da entrada: quem
        # comprou o exagero para baixo tem o stop ainda mais para baixo.
        oposto = None
        if canal is not None:
            oposto = (canal.inferior if posicao.direcao is Direcao.COMPRADO
                      else canal.superior)
        nivel = self.stop.nivel_inicial(posicao, candle, self._atr.valor, oposto)
        posicao.estado["nivel_stop"] = nivel

    def checar_stop(self, posicao: Posicao, candle: Candle) -> DecisaoSaida:
        if not self.stop.ativo:
            return DecisaoSaida(sair=False)
        nivel = self.stop.atualizar(posicao, candle, self._atr.valor)
        if not self.stop.foi_atingido(posicao, candle, nivel):
            return DecisaoSaida(sair=False)
        return DecisaoSaida(sair=True, motivo="stop",
                            preco_sugerido=self.stop.preco_de_execucao(
                                posicao, candle, nivel))

    # ---------------------------------------------------------------- saida

    def deve_sair(self, posicao: Posicao, candle: Candle) -> DecisaoSaida:
        canal = self._canal_para(candle)
        if canal is None:
            return DecisaoSaida(sair=False)

        # Saida por tempo: numa aposta de volta ao normal, um trade que nao
        # voltou depois de muitos candles provavelmente nao era exagero, era
        # tendencia - e ficar nele e teimosia cara.
        n = posicao.estado.get("candles", 0) + 1
        posicao.estado["candles"] = n
        if self.max_candles_no_trade and n >= self.max_candles_no_trade:
            return DecisaoSaida(sair=True, motivo="tempo_esgotado")

        meio = (canal.superior + canal.inferior) / 2
        if self.alvo == "meio":
            alvo = meio
        else:
            alvo = (canal.superior if posicao.direcao is Direcao.COMPRADO
                    else canal.inferior)

        if posicao.direcao is Direcao.COMPRADO:
            if candle.maxima >= alvo:
                return DecisaoSaida(sair=True, motivo="voltou_ao_alvo",
                                    preco_sugerido=alvo)
        elif candle.minima <= alvo:
            return DecisaoSaida(sair=True, motivo="voltou_ao_alvo",
                                preco_sugerido=alvo)
        return DecisaoSaida(sair=False)

    def contexto_atual(self) -> dict[str, Any]:
        canal = self._canal_para_atual()
        if canal is None:
            return {}
        return {"canal_superior": canal.superior, "canal_inferior": canal.inferior,
                "largura_canal": canal.largura, "atr": self._atr.valor,
                "candles_vistos": self._candles_vistos}

    def _canal_para_atual(self) -> Canal | None:
        sup, inf = self._sup.valor, self._inf.valor
        return (Canal(superior=sup, inferior=inf)
                if sup is not None and inf is not None else None)
