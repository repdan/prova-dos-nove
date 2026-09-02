"""
Contexto do dia, anexado a cada trade.

Estas sao as features que as analises da Etapa 2.5 e 2.6 mostraram ter valor:
tamanho do gap, movimento do after-hours, primeiro candle, ordem do sinal no
dia. Todas ficam gravadas em cada trade para a Etapa 4 treinar em cima.

REGRA CRITICA: uma feature so pode entrar no contexto de um trade se ja era
conhecida no instante da entrada. Por isso a classe entrega os valores de
forma incremental, conforme o dia avanca, em vez de calcular o dia inteiro de
uma vez. Medidas que so existem no fechamento do pregao - como a
direcionalidade - existem aqui, mas com o prefixo 'posterior_', e servem
apenas para rotular regime depois do fato. Nunca como entrada de modelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from strategy.base import Candle


@dataclass
class EstadoDoDia:
    """Acumula, ao longo do pregao, o que ja se sabe sobre ele."""

    dia: date
    abertura: float
    fecha_anterior: float | None
    ultimo_negociado_anterior: float | None

    primeiro_candle_amplitude: float | None = None
    primeiro_candle_corpo: float | None = None
    primeiro_candle_volume: float | None = None
    candles_vistos: int = 0
    sinais_ate_agora: int = 0

    maxima_ate_agora: float = field(default=float("-inf"))
    minima_ate_agora: float = field(default=float("inf"))

    @property
    def gap(self) -> float:
        if self.fecha_anterior is None:
            return 0.0
        return self.abertura - self.fecha_anterior

    @property
    def andou_after_hours(self) -> float:
        """Quanto o preco caminhou na sessao estendida, antes da abertura.

        Disponivel as 09:15 e responde por ~63% do gap de sessao - a analise da
        Etapa 2.5 mostrou que e informacao real que a estrategia ignorava.
        """
        if self.fecha_anterior is None or self.ultimo_negociado_anterior is None:
            return 0.0
        return self.ultimo_negociado_anterior - self.fecha_anterior


class ContextoDiario:
    """Mantem o estado do dia corrente e produz o contexto de cada entrada."""

    def __init__(self, quadro_pregao: pd.DataFrame,
                 quadro_bruto: pd.DataFrame | None = None):
        # Referencias do dia anterior, pre-calculadas uma vez. Sao dados de
        # ONTEM: consulta-los hoje nao e olhar para o futuro.
        p = quadro_pregao.sort_values("tempo_ativo").copy()
        p["dia"] = p["tempo_ativo"].dt.date
        dias = p.groupby("dia").agg(abertura=("abertura", "first"),
                                    fechamento=("fechamento", "last"),
                                    tempo_abertura=("tempo_ativo", "min"))
        self._fecha_anterior = dias["fechamento"].shift().to_dict()

        self._ultimo_negociado: dict[date, float] = {}
        if quadro_bruto is not None and not quadro_bruto.empty:
            b = quadro_bruto.sort_values("tempo_ativo")
            esq = (dias["tempo_abertura"].rename("tempo_ativo").reset_index()
                   .sort_values("tempo_ativo"))
            junto = pd.merge_asof(
                esq,
                b[["tempo_ativo", "fechamento"]].rename(columns={"fechamento": "ultimo"}),
                on="tempo_ativo", direction="backward", allow_exact_matches=False)
            self._ultimo_negociado = junto.set_index("dia")["ultimo"].to_dict()

        self._estado: EstadoDoDia | None = None

    # ------------------------------------------------------------ ciclo

    def observar(self, candle: Candle) -> None:
        """Chamado para todo candle, antes de qualquer decisao."""
        dia = candle.tempo.date()

        if self._estado is None or self._estado.dia != dia:
            self._estado = EstadoDoDia(
                dia=dia,
                abertura=candle.abertura,
                fecha_anterior=self._fecha_anterior.get(dia),
                ultimo_negociado_anterior=self._ultimo_negociado.get(dia),
            )

        e = self._estado
        e.candles_vistos += 1
        e.maxima_ate_agora = max(e.maxima_ate_agora, candle.maxima)
        e.minima_ate_agora = min(e.minima_ate_agora, candle.minima)

        if e.candles_vistos == 1:
            e.primeiro_candle_amplitude = candle.maxima - candle.minima
            e.primeiro_candle_corpo = abs(candle.fechamento - candle.abertura)
            e.primeiro_candle_volume = candle.volume

    def registrar_sinal(self) -> int:
        """Conta o sinal e devolve a ordem dele dentro do dia (1 = primeiro)."""
        assert self._estado is not None, "observar() precisa vir antes"
        self._estado.sinais_ate_agora += 1
        return self._estado.sinais_ate_agora

    def contexto(self, candle: Candle, ordem_do_sinal: int) -> dict[str, Any]:
        """Fotografia do que se sabe AGORA. Nada aqui vem do futuro."""
        e = self._estado
        assert e is not None

        return {
            # --- conhecido na abertura ---
            "gap_pontos": e.gap,
            "gap_direcao": 1 if e.gap > 0 else (-1 if e.gap < 0 else 0),
            "gap_absoluto": abs(e.gap),
            "after_hours_pontos": e.andou_after_hours,
            # --- conhecido apos o primeiro candle ---
            "primeiro_candle_amplitude": e.primeiro_candle_amplitude,
            "primeiro_candle_corpo": e.primeiro_candle_corpo,
            "primeiro_candle_volume": e.primeiro_candle_volume,
            # --- posicao no dia ---
            "ordem_do_sinal_no_dia": ordem_do_sinal,
            "primeiro_candle_do_dia": e.candles_vistos == 1,
            "candles_desde_abertura": e.candles_vistos - 1,
            "amplitude_ate_agora": e.maxima_ate_agora - e.minima_ate_agora,
            # --- calendario ---
            "hora": candle.tempo.strftime("%H:%M"),
            "dia_semana": candle.tempo.weekday(),
            "volume_candle": candle.volume,
            "spread_no_sinal": candle.spread,
        }


def direcionalidade_por_dia(quadro_pregao: pd.DataFrame) -> pd.DataFrame:
    """Rotulo de regime, calculado DEPOIS do fechamento de cada pregao.

    Direcionalidade = |fechamento - abertura| / amplitude do dia. Perto de 100%
    o dia andou em linha reta; perto de 0% ele balancou e voltou. E a traducao
    numerica de "mercado lateral", o regime que a Etapa 4 precisa isolar.

    Sai separado do ContextoDiario de proposito: e informacao do futuro em
    relacao a qualquer trade do proprio dia, e serve so para analisar
    resultados por regime - nunca como feature de decisao.
    """
    p = quadro_pregao.copy()
    p["dia"] = p["tempo_ativo"].dt.date
    d = p.groupby("dia").agg(abertura=("abertura", "first"),
                             fechamento=("fechamento", "last"),
                             maxima=("maxima", "max"), minima=("minima", "min"),
                             volume=("volume_ticks", "sum"))
    d["amplitude"] = d["maxima"] - d["minima"]
    d["posterior_direcionalidade"] = (
        (d["fechamento"] - d["abertura"]).abs() / d["amplitude"].replace(0, pd.NA))
    d["posterior_amplitude_dia"] = d["amplitude"]
    d["posterior_volume_dia"] = d["volume"]
    return d[["posterior_direcionalidade", "posterior_amplitude_dia",
              "posterior_volume_dia"]]
