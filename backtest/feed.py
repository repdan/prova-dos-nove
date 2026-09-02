"""
Fonte de candles.

O engine nunca abre arquivo e nunca fala com o MT5. Ele consome um DataFeed e
pronto. Trocar backtest por operacao ao vivo e trocar a implementacao desta
interface - nenhuma linha do motor ou da estrategia muda.

O contrato tem uma regra so, e ela e a mais importante do projeto: o feed
entrega candles JA FECHADOS, em ordem cronologica, um por vez, e nunca
devolve nada do futuro. Um feed que respeita isso torna look-ahead bias
estruturalmente impossivel para quem consome.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

import pandas as pd

from strategy.base import Candle


class DataFeed(ABC):
    """Fonte de candles fechados, em ordem."""

    @abstractmethod
    def __iter__(self) -> Iterator[Candle]:
        ...

    @property
    def descricao(self) -> str:
        return self.__class__.__name__


class FeedParquet(DataFeed):
    """Le candles de um arquivo parquet gerado pela Etapa 1."""

    def __init__(self, caminho: str | Path, inicio: str | None = None,
                 fim: str | None = None):
        self.caminho = Path(caminho)
        if not self.caminho.exists():
            raise FileNotFoundError(
                f"Historico nao encontrado: {self.caminho}\n"
                "Rode 'python coletar.py' com o MetaTrader 5 aberto."
            )
        df = pd.read_parquet(self.caminho).sort_values("tempo_ativo")

        # O recorte de periodo vive aqui, e nao no motor: assim o walk-forward
        # da Etapa 4 so precisa criar feeds com janelas diferentes.
        if inicio:
            df = df[df["tempo_ativo"] >= pd.Timestamp(inicio, tz=df["tempo_ativo"].dt.tz)]
        if fim:
            df = df[df["tempo_ativo"] < pd.Timestamp(fim, tz=df["tempo_ativo"].dt.tz)]

        self._df = df.reset_index(drop=True)

    def __len__(self) -> int:
        return len(self._df)

    def __iter__(self) -> Iterator[Candle]:
        for l in self._df.itertuples():
            yield Candle(
                tempo=l.tempo_ativo,
                abertura=float(l.abertura),
                maxima=float(l.maxima),
                minima=float(l.minima),
                fechamento=float(l.fechamento),
                volume=float(l.volume_ticks),
                # O MT5 guarda spread em 'points' (0.01). Converter aqui, uma
                # vez so, evita que a unidade errada vaze para o calculo de
                # custo - onde o erro seria de 100x e passaria despercebido.
                spread=float(l.spread_pontos) / 100.0,
            )

    @property
    def quadro(self) -> pd.DataFrame:
        """Acesso ao DataFrame, para analises fora do laco do motor."""
        return self._df

    @property
    def descricao(self) -> str:
        if self._df.empty:
            return f"{self.caminho.name} (vazio)"
        return (f"{self.caminho.name} | {len(self._df):,} candles | "
                f"{self._df['tempo_ativo'].min():%Y-%m-%d} a "
                f"{self._df['tempo_ativo'].max():%Y-%m-%d}").replace(",", ".")


class ResolvedorIntrabar:
    """Reconstitui o caminho do preco DENTRO de um candle usando um timeframe menor.

    O problema que isto resolve: um candle M15 diz maxima e minima, mas nao diz
    qual das duas veio primeiro. Quando um alvo e um stop estao os dois dentro
    do mesmo candle, um backtester sem essa informacao precisa escolher - e
    escolher errado, de forma otimista, e uma das maneiras mais comuns de um
    backtest mentir para quem o escreveu.

    Com os M5 do mesmo periodo em maos, nao ha o que escolher: percorremos os
    sub-candles em ordem e vemos o que aconteceu antes.
    """

    def __init__(self, caminho_menor: str | Path, minutos_menor: int = 5):
        self.minutos = minutos_menor
        df = pd.read_parquet(Path(caminho_menor)).sort_values("tempo_ativo")
        self._tempos = df["tempo_ativo"].to_numpy()
        self._max = df["maxima"].to_numpy()
        self._min = df["minima"].to_numpy()
        self._fecha = df["fechamento"].to_numpy()

    def qual_veio_primeiro(self, candle: Candle, minutos_candle: int,
                           nivel_a: float, sobe_a: bool,
                           nivel_b: float, sobe_b: bool) -> str | None:
        """Diz qual dos dois niveis foi tocado antes dentro do candle.

        Retorna "a", "b", ou None se nenhum foi tocado (ou se nao ha M5 para
        aquele periodo - caso em que quem chamou decide o desempate).
        """
        inicio = pd.Timestamp(candle.tempo)
        fim = inicio + pd.Timedelta(minutes=minutos_candle)
        i0, i1 = self._tempos.searchsorted([inicio.to_datetime64(), fim.to_datetime64()])
        if i1 <= i0:
            return None

        for k in range(i0, i1):
            tocou_a = self._max[k] >= nivel_a if sobe_a else self._min[k] <= nivel_a
            tocou_b = self._max[k] >= nivel_b if sobe_b else self._min[k] <= nivel_b
            if tocou_a and tocou_b:
                # Os dois no mesmo sub-candle de 5 minutos: nem o M5 desempata.
                # Assume o pior caso para quem esta posicionado, que e a unica
                # escolha que nao infla o resultado.
                return "b"
            if tocou_a:
                return "a"
            if tocou_b:
                return "b"
        return None

    def excursao(self, candle: Candle, minutos_candle: int) -> tuple[float, float]:
        """(minima, maxima) do candle segundo o timeframe menor.

        Serve de checagem de consistencia entre as duas bases.
        """
        inicio = pd.Timestamp(candle.tempo)
        fim = inicio + pd.Timedelta(minutes=minutos_candle)
        i0, i1 = self._tempos.searchsorted([inicio.to_datetime64(), fim.to_datetime64()])
        if i1 <= i0:
            return candle.minima, candle.maxima
        return float(self._min[i0:i1].min()), float(self._max[i0:i1].max())
