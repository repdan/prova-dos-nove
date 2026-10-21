"""
Estatisticas das duas pistas, para calibrar o acompanhamento futuro.

    .venv/Scripts/python.exe -m analises.pistas_estatisticas

Pista 1: Grade no ouro, canal na abertura de NY.
Pista 2: Ichimoku classico em M15 (ouro e USDJPY) - a mudanca de regime de 2022.
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
from analises.grade_tempo_grafico import CANAIS, AUTOR, MERCADOS, carregar  # noqa: E402
from analises import ichimoku_referencia as ic                                      # noqa: E402
from strategy.grade import Custos, simular                                   # noqa: E402
from strategy.ichimoku import ParametrosIchimoku, simular_ichimoku             # noqa: E402

PISTA1 = {
    "P1-A ouro NY M15 1a vela, semanal dom-qua": ("M15", dict(gestao_semanal=True, dias_semana=(0, 1, 2))),
    "P1-B ouro NY M30 1a vela, diaria": ("M30", dict()),
}
PISTA2 = {"P2 ouro M15 Ichimoku classico": "ouro", "P2 USDJPY M15 Ichimoku classico": "USDJPY"}


def rodar(spec):
    tipo, nome, com_custo = spec
    if tipo == 1:
        tf, kw = PISTA1[nome]
        p = replace(MERCADOS["ouro NY"]["p"], **CANAIS["1a vela"], **kw)
        c = MERCADOS["ouro NY"]["custo"] if com_custo else Custos(0, 0, 0.0)
        return spec, simular(carregar("ouro NY", tf), p, c)
    mk = PISTA2[nome]
    cfg = ic.MERCADOS[mk]
    c = cfg["custo"] if com_custo else Custos(0, 0, 0.0)
    return spec, simular_ichimoku(ic.carregar(mk, "M15"), ParametrosIchimoku(), c, cfg["ponto"])


def resumo(t: pd.DataFrame, rot: str) -> None:
    anos_tot = (pd.Timestamp(t["tempo_saida"].max()) - pd.Timestamp(t["tempo_entrada"].min())).days / 365.25
    r = t["r"]
    print(f"    {rot:<14}{len(r):>6}{len(r) / anos_tot:>8.0f}/ano{(t['resultado'] > 0).mean():>8.0%}"
          f"{r.mean():>+9.3f}R{r.std():>8.2f}{r.mean() / (r.std() / np.sqrt(len(r))):>+7.1f}s"
          f"{r.quantile(0.05):>8.2f}{r.max():>8.2f}")


def main() -> int:
    specs = [(1, n, c) for n in PISTA1 for c in (False, True)] + [(2, n, c) for n in PISTA2 for c in (False, True)]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))
    for (tipo, nome, com_custo), t in sorted(res.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
        print(f"\n  {nome} - {'COM' if com_custo else 'sem'} custo")
        print(f"    {'periodo':<14}{'trades':>6}{'freq':>12}{'acerto':>8}{'R medio':>10}{'desvio':>8}"
              f"{'sig':>8}{'pior 5%':>8}{'maior':>8}")
        anos = pd.to_datetime(t["tempo_entrada"]).dt.year
        resumo(t, "completo")
        resumo(t[anos < 2022], "ate 2021")
        resumo(t[anos >= 2022], "2022 em diante")
    return 0


if __name__ == "__main__":
    sys.exit(main())
