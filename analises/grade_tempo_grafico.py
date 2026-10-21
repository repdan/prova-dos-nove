"""
Grade: tempo grafico maior melhora o quadro?

    .venv/Scripts/python.exe -m analises.grade_tempo_grafico

Monta M5, M15, M30 e H1 a partir do M1 (dentro de cada sessao, ancorado no
inicio dela, sem misturar sessoes) e roda a mesma estrategia em todos:
gestao do autor (alvo 1,5 canal, 2 stops, 1 gain, 0x0 em 1 canal), canal na
1a vela ou nas 4 primeiras velas DAQUELE tempo grafico (escala sozinho).

HK50: pregao de HK, tendencia pelo gap, spread 4,5.
Ouro: aberturas corretora / Londres / NY, tendencia neutra, spread 0,21.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from strategy.grade import Custos, ParametrosGrade, simular   # noqa: E402

TFS = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60}
AUTOR = ParametrosGrade(max_stops_dia=2, take_niveis=1.5)
CANAIS = {"1a vela": dict(velas_minimas=1, velas_maximas=1, largura_minima=0.0, usar_vela_gigante=False),
          "4 velas": dict(velas_minimas=4, velas_maximas=4, largura_minima=0.0, usar_vela_gigante=False)}
MERCADOS = {
    "HK50": dict(p=replace(AUTOR, tendencia="gap"), custo=Custos(0.5, 0.78, 4.5)),
    "ouro corretora": dict(p=replace(AUTOR, tendencia="neutra"), custo=Custos(0.02, 0.001, 0.21), h=None),
    "ouro Londres": dict(p=replace(AUTOR, tendencia="neutra"), custo=Custos(0.02, 0.001, 0.21), h=(10, 0)),
    "ouro NY": dict(p=replace(AUTOR, tendencia="neutra"), custo=Custos(0.02, 0.001, 0.21), h=(16, 30)),
}
_CACHE: dict = {}


def reamostrar(d: pd.DataFrame, minutos: int) -> pd.DataFrame:
    """Velas de N minutos dentro de cada sessao, contadas a partir do inicio dela."""
    if minutos == 1:
        return d
    t0 = d.groupby("sessao_id")["tempo_ativo"].transform("min")
    balde = ((d["tempo_ativo"] - t0).dt.total_seconds() // (60 * minutos)).astype(int)
    g = d.groupby([d["sessao_id"], balde], sort=True)
    return pd.DataFrame({
        "tempo_ativo": g["tempo_ativo"].first(), "abertura": g["abertura"].first(),
        "maxima": g["maxima"].max(), "minima": g["minima"].min(),
        "fechamento": g["fechamento"].last(), "spread_pontos": g["spread_pontos"].median(),
        "sessao_id": g["sessao_id"].first(),
    }).reset_index(drop=True)


def carregar(mercado: str, tf: str) -> pd.DataFrame:
    chave = (mercado, tf)
    if chave in _CACHE:
        return _CACHE[chave]
    if mercado == "HK50":
        d = pd.read_parquet(RAIZ / "data" / "historico" / "HK50" / "HK50_M1_pregao.parquet")
        d = d[d["tempo_ativo"] >= pd.Timestamp("2022-03-01", tz="Asia/Hong_Kong")]
    else:
        d = pd.read_parquet(RAIZ / "data" / "historico" / "XAUUSD" / "XAUUSD_M1_dias.parquet")
        d = d[d["tempo_ativo"].dt.year >= 2019]
        h = MERCADOS[mercado]["h"]
        if h is not None:
            ts = d["tempo_servidor"]
            d = d[(ts.dt.hour > h[0]) | ((ts.dt.hour == h[0]) & (ts.dt.minute >= h[1]))]
    d = reamostrar(d.sort_values("tempo_ativo").reset_index(drop=True), TFS[tf])
    _CACHE[chave] = d
    return d


def rodar(spec):
    mercado, tf, canal, custo, inverter = spec
    cfg = MERCADOS[mercado]
    p = replace(cfg["p"], **CANAIS[canal], controle_inverter=inverter)
    c = cfg["custo"] if custo else Custos(0, 0, 0.0)
    return spec, simular(carregar(mercado, tf), p, c)


def m(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"n": 0, "r": np.nan, "s": np.nan, "w": np.nan, "cr": np.nan}
    r = t["r"].dropna()
    e = r.std() / np.sqrt(len(r))
    return {"n": len(r), "r": r.mean(), "s": r.mean() / e, "w": t["largura"].median(),
            "cr": (t["custo"] / t["risco"]).median()}


def fr(x):
    return f"{x['r']:+.3f}R {x['s']:+5.1f}s"


def main() -> int:
    specs = [(mk, tf, cn, custo, inv) for mk in MERCADOS for tf in TFS for cn in CANAIS
             for custo, inv in ((False, False), (False, True), (True, False))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))
    for mk in MERCADOS:
        print(f"\n  {mk.upper()}")
        print(f"  {'tempo grafico / canal':<22}{'trades':>7}{'w':>9}{'sem custo':>16}{'ESPELHO':>16}"
              f"{'com custo':>16}{'custo':>8}")
        print("  " + "-" * 94)
        for tf in TFS:
            for cn in CANAIS:
                sem = m(res[(mk, tf, cn, False, False)])
                esp = m(res[(mk, tf, cn, False, True)])
                com = m(res[(mk, tf, cn, True, False)])
                print(f"  {tf + ' / ' + cn:<22}{sem['n']:>7}{sem['w']:>9.2f}{fr(sem):>16}{fr(esp):>16}"
                      f"{fr(com):>16}{com['cr']:>7.2f}R")
    return 0


if __name__ == "__main__":
    sys.exit(main())
