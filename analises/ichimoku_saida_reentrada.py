"""
Ichimoku: sair quando o preco volta para DENTRO da nuvem, contra a saida classico
(fechar alem do outro lado e virar a mao).

    .venv/Scripts/python.exe -m analises.ichimoku_saida_reentrada
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analises import ichimoku_referencia as ic                          # noqa: E402
from strategy.grade import Custos                                # noqa: E402
from strategy.ichimoku import ParametrosIchimoku, simular_ichimoku  # noqa: E402

SAIDAS = {"classico (outro lado, vira a mao)": "nuvem", "reentrada na nuvem": "reentrada"}
CASOS = [("ouro", "M15"), ("ouro", "H1"), ("USDJPY", "M15"), ("USDJPY", "H1")]


def rodar(spec):
    mk, tf, saida, com_custo, inv = spec
    cfg = ic.MERCADOS[mk]
    p = ParametrosIchimoku(saida=SAIDAS[saida], controle_inverter=inv)
    return spec, simular_ichimoku(ic.carregar(mk, tf), p, cfg["custo"] if com_custo else Custos(0, 0, 0.0),
                                  cfg["ponto"])


def main() -> int:
    specs = [(mk, tf, s, c, inv) for mk, tf in CASOS for s in SAIDAS
             for c, inv in ((False, False), (False, True), (True, False))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))
    for mk, tf in CASOS:
        print(f"\n  {mk} {tf}")
        print(f"  {'saida':<32}{'periodo':<16}{'trades':>7}{'acerto':>8}{'sem custo':>16}"
              f"{'ESPELHO':>16}{'com custo':>16}{'dur. med':>10}")
        print("  " + "-" * 119)
        for s in SAIDAS:
            sem, esp, com = (res[(mk, tf, s, False, False)], res[(mk, tf, s, False, True)],
                             res[(mk, tf, s, True, False)])
            for rot, filtro in [("completo", lambda t: t),
                                ("2022 em diante", lambda t: t[pd.to_datetime(t["tempo_entrada"]).dt.year >= 2022])]:
                a, b, c = filtro(sem), filtro(esp), filtro(com)
                dur = (pd.to_datetime(c["tempo_saida"]) - pd.to_datetime(c["tempo_entrada"])).dt.total_seconds() / 3600
                print(f"  {s:<32}{rot:<16}{len(a):>7}{(c['resultado'] > 0).mean():>8.0%}"
                      f"{ic.fr(ic.m(a)):>16}{ic.fr(ic.m(b)):>16}{ic.fr(ic.m(c)):>16}{dur.median():>8.1f} h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
