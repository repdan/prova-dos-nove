"""
Execucao de ordens.

O engine nunca calcula preco de execucao nem custo. Ele pede ao Executor para
abrir e fechar, e recebe de volta o que aconteceu. A implementacao de hoje
simula; a de amanha chama mt5.order_send(). O motor nao percebe a diferenca.

Onde o custo entra - e por que isso decide o projeto: uma operacao paga o
spread inteiro no giro (entra no lado caro, sai no lado barato) mais a
derrapagem nas duas pontas. Com spread mediano de 4,5 pontos no HK50, um
backtest que ignora isso ganha ~5 pontos de presente em cada trade. Numa
estrategia que busca dezenas de pontos, isso e a diferenca entre um sistema
lucrativo e um prejuizo disfarcado.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any

from strategy.base import Candle, Direcao, Posicao


@dataclass
class Trade:
    """Uma operacao encerrada, com tudo que a Etapa 4 vai precisar."""

    direcao: str
    tempo_entrada: datetime
    tempo_saida: datetime
    preco_entrada: float          # ja com spread e derrapagem aplicados
    preco_saida: float
    preco_entrada_bruto: float    # preco de tela, para conferencia
    preco_saida_bruto: float
    lote: float
    motivo_saida: str
    candles_no_trade: int

    resultado_pontos: float       # liquido de custos, em pontos de indice
    resultado_bruto_pontos: float
    custo_pontos: float
    resultado_dinheiro: float

    excursao_favoravel: float     # o quanto chegou a ganhar antes de fechar
    excursao_contraria: float     # o quanto chegou a perder (perda maxima)
    noites_carregadas: int = 0
    swap_pontos: float = 0.0

    contexto: dict[str, Any] = field(default_factory=dict)

    def como_dict(self) -> dict:
        d = asdict(self)
        ctx = d.pop("contexto")
        return {**d, **{f"ctx_{k}": v for k, v in ctx.items()}}


class Executor(ABC):
    """Interface de execucao. Simulada agora, real na Fase 2."""

    @abstractmethod
    def abrir(self, direcao: Direcao, candle: Candle, lote: float,
              contexto: dict, preco_referencia: float | None = None) -> Posicao:
        ...

    @abstractmethod
    def fechar(self, posicao: Posicao, candle: Candle, motivo: str,
               preco_referencia: float | None = None) -> Trade:
        ...


class ExecutorSimulado(Executor):
    """Execucao simulada com spread e derrapagem realistas."""

    def __init__(self, spread_padrao: float, slippage: float,
                 comissao_por_lote: float, valor_ponto_por_lote: float,
                 usar_spread_do_candle: bool = True,
                 swap_compra: float = 0.0, swap_venda: float = 0.0,
                 dia_swap_triplo: int = 4, spread_forcado: float | None = None):
        self.spread_padrao = spread_padrao
        self.slippage = slippage
        self.comissao_por_lote = comissao_por_lote
        self.valor_ponto_por_lote = valor_ponto_por_lote
        self.usar_spread_do_candle = usar_spread_do_candle
        self.swap_compra = swap_compra
        self.swap_venda = swap_venda
        self.dia_swap_triplo = dia_swap_triplo
        # Quando preenchido, ignora o spread historico e usa este em tudo.
        self.spread_forcado = spread_forcado
        self.trades: list[Trade] = []

    def _swap(self, posicao: Posicao, saida: datetime) -> tuple[int, float]:
        """(noites carregadas, custo em pontos).

        Cada virada de data entre entrada e saida e uma noite cobrada. Na
        sexta o swap e triplo, porque a corretora cobra o fim de semana junto -
        e trades de rompimento em tendencia costumam ser justamente os que
        atravessam varios dias.
        """
        taxa = (self.swap_compra if posicao.direcao is Direcao.COMPRADO
                else self.swap_venda)
        if not taxa:
            return 0, 0.0

        d0, d1 = posicao.tempo_entrada.date(), saida.date()
        noites = (d1 - d0).days
        if noites <= 0:
            return 0, 0.0

        total = 0.0
        for k in range(noites):
            dia = d0 + timedelta(days=k)
            total += taxa * (3 if dia.weekday() == self.dia_swap_triplo else 1)
        return noites, total

    # ------------------------------------------------------------- custos

    def _spread(self, candle: Candle) -> float:
        """Spread daquele candle, se o historico trouxer; senao o do config.

        Usar o spread real de cada momento em vez de uma media importa porque
        ele nao e constante: alarga na abertura e em noticia, que e justamente
        quando a estrategia mais dispara sinal.
        """
        if self.spread_forcado is not None:
            return self.spread_forcado
        if self.usar_spread_do_candle and candle.spread > 0:
            return candle.spread
        return self.spread_padrao

    def _preco_com_custo(self, preco: float, candle: Candle,
                         direcao: Direcao, abrindo: bool) -> float:
        """Aplica meio spread + derrapagem sempre CONTRA quem opera.

        Metade do spread em cada ponta: no giro completo paga-se o spread
        inteiro, que e o que acontece de verdade.
        """
        penalidade = self._spread(candle) / 2 + self.slippage
        # Abrindo comprado paga mais caro; fechando comprado (vendendo) recebe
        # menos. Vendido e o espelho. O sinal abaixo cobre os quatro casos.
        sentido = direcao.multiplicador * (1 if abrindo else -1)
        return preco + sentido * penalidade

    # ------------------------------------------------------------ ordens

    def abrir(self, direcao: Direcao, candle: Candle, lote: float,
              contexto: dict, preco_referencia: float | None = None) -> Posicao:
        bruto = preco_referencia if preco_referencia is not None else candle.fechamento
        preco = self._preco_com_custo(bruto, candle, direcao, abrindo=True)

        posicao = Posicao(
            direcao=direcao,
            preco_entrada=preco,
            tempo_entrada=candle.tempo,
            lote=lote,
            contexto_entrada=dict(contexto),
        )
        posicao.estado["preco_bruto_entrada"] = bruto
        posicao.estado["spread_entrada"] = self._spread(candle)
        posicao.estado["candles"] = 0
        posicao.estado["melhor"] = bruto      # excursao favoravel
        posicao.estado["pior"] = bruto        # excursao contraria
        return posicao

    def acompanhar(self, posicao: Posicao, candle: Candle) -> None:
        """Atualiza as excursoes maxima e minima enquanto a posicao vive.

        Sem isso nao ha como saber a perda maxima por trade - a metrica que o
        projeto precisa justamente porque a estrategia base nao tem stop.
        """
        posicao.estado["candles"] = posicao.estado.get("candles", 0) + 1
        if posicao.direcao is Direcao.COMPRADO:
            posicao.estado["melhor"] = max(posicao.estado["melhor"], candle.maxima)
            posicao.estado["pior"] = min(posicao.estado["pior"], candle.minima)
        else:
            posicao.estado["melhor"] = min(posicao.estado["melhor"], candle.minima)
            posicao.estado["pior"] = max(posicao.estado["pior"], candle.maxima)

    def fechar(self, posicao: Posicao, candle: Candle, motivo: str,
               preco_referencia: float | None = None) -> Trade:
        bruto = preco_referencia if preco_referencia is not None else candle.fechamento
        preco = self._preco_com_custo(bruto, candle, posicao.direcao, abrindo=False)

        pontos = (preco - posicao.preco_entrada) * posicao.direcao.multiplicador
        bruto_entrada = posicao.estado["preco_bruto_entrada"]
        pontos_brutos = (bruto - bruto_entrada) * posicao.direcao.multiplicador

        # A comissao e cobrada em dinheiro; para manter tudo em pontos,
        # converte usando o valor do ponto.
        comissao_pontos = 0.0
        if self.valor_ponto_por_lote > 0:
            comissao_pontos = self.comissao_por_lote / self.valor_ponto_por_lote

        noites, swap_pontos = self._swap(posicao, candle.tempo)
        # swap negativo e custo; a soma abaixo ja tem o sinal certo.
        pontos_liquidos = pontos - comissao_pontos + swap_pontos
        mult = posicao.direcao.multiplicador

        trade = Trade(
            direcao=posicao.direcao.value,
            tempo_entrada=posicao.tempo_entrada,
            tempo_saida=candle.tempo,
            preco_entrada=posicao.preco_entrada,
            preco_saida=preco,
            preco_entrada_bruto=bruto_entrada,
            preco_saida_bruto=bruto,
            lote=posicao.lote,
            motivo_saida=motivo,
            candles_no_trade=posicao.estado.get("candles", 0),
            resultado_pontos=pontos_liquidos,
            resultado_bruto_pontos=pontos_brutos,
            custo_pontos=pontos_brutos - pontos_liquidos,
            resultado_dinheiro=pontos_liquidos * self.valor_ponto_por_lote * posicao.lote,
            excursao_favoravel=(posicao.estado["melhor"] - bruto_entrada) * mult,
            excursao_contraria=(bruto_entrada - posicao.estado["pior"]) * mult,
            noites_carregadas=noites,
            swap_pontos=swap_pontos,
            contexto=posicao.contexto_entrada,
        )
        self.trades.append(trade)
        return trade
