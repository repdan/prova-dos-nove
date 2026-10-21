"""
O modo ao vivo reproduz o backtest, vela a vela.

Para cada vela k de um periodo real, roda a estrategia com os dados cortados
em k (modo ao vivo) e compara a posicao que deve estar aberta com a posicao
que o backtest completo tinha aberta logo depois de k. Se divergir, o robo
estaria operando outra estrategia.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from analises.grade_tempo_grafico import reamostrar
from strategy.grade import Custos, ParametrosGrade, simular
from strategy.ichimoku import ParametrosIchimoku, simular_ichimoku

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "data" / "historico" / "XAUUSD" / "XAUUSD_M15_dias.parquet"
SEM = Custos(0, 0, 0.0)
pytestmark = pytest.mark.skipif(not ARQ.exists(), reason="sem dados do ouro")


def dados_ouro_ny(semanas: int = 6) -> pd.DataFrame:
    d = pd.read_parquet(ARQ)
    d = d[d["tempo_ativo"] >= d["tempo_ativo"].max() - pd.Timedelta(weeks=semanas)]
    ts = d["tempo_servidor"]
    d = d[(ts.dt.hour > 16) | ((ts.dt.hour == 16) & (ts.dt.minute >= 30))]
    return d.sort_values("tempo_ativo").reset_index(drop=True)


def aberta_no_backtest(t: pd.DataFrame, momento) -> pd.Series | None:
    if t.empty:
        return None
    ent, sai = pd.to_datetime(t["tempo_entrada"]), pd.to_datetime(t["tempo_saida"])
    sel = t[(ent <= momento) & (sai > momento)]
    return None if sel.empty else sel.iloc[0]


@pytest.mark.parametrize("semanal", [False, True])
def test_grade_ao_vivo_igual_ao_backtest(semanal):
    p = ParametrosGrade(tendencia="neutra", max_stops_dia=2, take_niveis=1.5, velas_minimas=1,
                          velas_maximas=1, largura_minima=0.0, usar_vela_gigante=False)
    if semanal:
        p = replace(p, gestao_semanal=True, dias_semana=(0, 1, 2))
    d = dados_ouro_ny()
    completo = simular(d, p, SEM)
    fim_dia = d.groupby(d["tempo_ativo"].dt.date)["tempo_ativo"].transform("max")
    divergencias, conferidas = 0, 0
    for k in range(len(d) // 3, len(d) - 1):
        momento = d["tempo_ativo"].iloc[k]
        vivo = {"fim_previsto": fim_dia.iloc[k]}
        simular(d.iloc[: k + 1], p, SEM, ao_vivo=vivo)
        bt = aberta_no_backtest(completo, momento)
        pos = vivo["pos"]
        if (pos is None) != (bt is None) or (pos is not None and pos["t"] != pd.Timestamp(bt["tempo_entrada"])):
            divergencias += 1
        conferidas += 1
    assert conferidas > 200
    assert divergencias == 0


def test_ichimoku_ao_vivo_igual_ao_backtest():
    d = reamostrar(dados_ouro_ny(4).assign(sessao_id=lambda x: x["sessao_id"]), 15)
    d["dia"] = d["tempo_ativo"].dt.date
    p = ParametrosIchimoku()
    completo = simular_ichimoku(d, p, SEM)
    fim_dia = d.groupby("dia")["tempo_ativo"].transform("max")
    divergencias = 0
    for k in range(len(d) // 2, len(d) - 1):
        vivo = {"fim_previsto": fim_dia.iloc[k]}
        simular_ichimoku(d.iloc[: k + 1], p, SEM, ao_vivo=vivo)
        bt = aberta_no_backtest(completo, d["tempo_ativo"].iloc[k])
        pos = vivo["pos"]
        if (pos is None) != (bt is None) or (pos is not None and pos["t"] != pd.Timestamp(bt["tempo_entrada"])):
            divergencias += 1
    assert divergencias == 0
