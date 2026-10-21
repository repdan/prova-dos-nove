"""
Ichimoku de referencia em ouro, USDJPY e HK50.

    .venv/Scripts/python.exe -m analises.ichimoku_referencia

Versoes: classico (entra ao romper a nuvem, sai e vira a mao no outro lado),
classico so com entradas fortes, classico so com nuvem fina, e adaptacao Grade
(alvo de 1 ou 2 niveis do canal das ultimas 4 velas, 0x0). Todas fecham a
posicao no fim do dia. Espelho = mesmas entradas e saidas, sentido oposto.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analises.grade_tempo_grafico import reamostrar                  # noqa: E402
from strategy.grade import Custos                                     # noqa: E402
from strategy.ichimoku import ParametrosIchimoku, simular_ichimoku      # noqa: E402

TFS = {"M1": 1, "M15": 15, "H1": 60}
MERCADOS = {
    "ouro": dict(arq="XAUUSD/XAUUSD_M1_dias.parquet", desde=2019, ponto=0.01,
                 custo=Custos(0.02, 0.001, 0.21), tfs=("M15", "H1")),
    "USDJPY": dict(arq="USDJPY/USDJPY_M1_dias.parquet", desde=2016, ponto=0.001,
                   custo=Custos(0.0008, 0.1 / 628.79), tfs=("M15", "H1")),
    "HK50": dict(arq="HK50/HK50_M1_pregao.parquet", desde=2022, ponto=0.01,
                 custo=Custos(0.5, 0.78, 4.5), tfs=("M1", "M15")),
}
VERSOES = {
    "classico": ParametrosIchimoku(),
    "classico, so fortes": ParametrosIchimoku(so_fortes=True),
    "classico, nuvem fina": ParametrosIchimoku(nuvem_fina=1.0),
    "Grade, alvo 1 nivel": ParametrosIchimoku(saida="grade", take_niveis=1.0),
    "Grade, alvo 2 niveis": ParametrosIchimoku(saida="grade", take_niveis=2.0),
}
_CACHE: dict = {}


def carregar(mk: str, tf: str) -> pd.DataFrame:
    if (mk, tf) not in _CACHE:
        cfg = MERCADOS[mk]
        d = pd.read_parquet(RAIZ / "data" / "historico" / cfg["arq"])
        d = d[d["tempo_ativo"].dt.year >= cfg["desde"]].sort_values("tempo_ativo").reset_index(drop=True)
        d = reamostrar(d, TFS[tf])
        d["dia"] = d["tempo_ativo"].dt.date
        _CACHE[(mk, tf)] = d
    return _CACHE[(mk, tf)]


def rodar(spec):
    mk, tf, versao, com_custo, inv = spec
    p = replace(VERSOES[versao], controle_inverter=inv)
    cfg = MERCADOS[mk]
    c = cfg["custo"] if com_custo else Custos(0, 0, 0.0)
    return spec, simular_ichimoku(carregar(mk, tf), p, c, cfg["ponto"])


def m(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"n": 0, "r": np.nan, "s": np.nan, "ac": np.nan, "cr": np.nan}
    r = t["r"].replace([np.inf, -np.inf], np.nan).dropna()
    e = r.std() / np.sqrt(len(r))
    return {"n": len(r), "r": r.mean(), "s": r.mean() / e, "ac": (t["resultado"] > 0).mean(),
            "cr": (t["custo"] / t["risco"]).median()}


def fr(x):
    return f"{x['r']:+.3f}R {x['s']:+5.1f}s"


def main() -> int:
    specs = [(mk, tf, v, c, inv) for mk, cfg in MERCADOS.items() for tf in cfg["tfs"]
             for v in VERSOES for c, inv in ((False, False), (False, True), (True, False))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))
    for mk, cfg in MERCADOS.items():
        for tf in cfg["tfs"]:
            print(f"\n  {mk} {tf} (desde {cfg['desde']})")
            print(f"  {'versao':<26}{'trades':>7}{'acerto':>8}{'sem custo':>16}{'ESPELHO':>16}"
                  f"{'com custo':>16}{'custo':>8}")
            print("  " + "-" * 97)
            for v in VERSOES:
                sem, esp = m(res[(mk, tf, v, False, False)]), m(res[(mk, tf, v, False, True)])
                com = m(res[(mk, tf, v, True, False)])
                print(f"  {v:<26}{sem['n']:>7}{sem['ac']:>8.0%}{fr(sem):>16}{fr(esp):>16}"
                      f"{fr(com):>16}{com['cr']:>7.2f}R")
            t = res[(mk, tf, "classico", False, False)]
            anos = pd.to_datetime(t["tempo_entrada"]).dt.year
            print("  classico por ano, sem custo: " + "  ".join(f"{a}:{m(g)['r']:+.2f}" for a, g in t.groupby(anos)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
