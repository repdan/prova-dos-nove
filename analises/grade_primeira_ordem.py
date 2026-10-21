"""
Grade M1 - evitar a primeira ordem do dia.

    .venv/Scripts/python.exe analises/grade_primeira_ordem.py

Versao do autor (1 gain, 2 stops, take 1,5 canal, 0x0 1 canal, canal de 4
velas mirando 50 pontos) com 0, 1 e 2 sinais evitados. Mostra tambem o que
o sinal evitado teria dado, e a que horas ele costuma aparecer.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analises.grade_canal_autor import ATUAL, BAIXO, DF, SEM, VERSAO, cab, linha, m  # noqa: E402
from strategy.grade import simular                                              # noqa: E402

AUTOR = replace(VERSAO, canal_modo="alvo")


def main() -> int:
    cab("A) EVITAR A PRIMEIRA ORDEM - canal de 4 velas (alvo 50)")
    for k in (0, 1, 2):
        linha(f"evita {k} sinal(is)", replace(AUTOR, pular_sinais=k))
    cab("A2) MESMO TESTE - canal da 1a vela")
    for k in (0, 1, 2):
        linha(f"evita {k} sinal(is)", replace(VERSAO, pular_sinais=k))

    # O que o primeiro sinal teria dado: 1o trade do dia quando nada e evitado.
    t0 = simular(DF, AUTOR, SEM)
    t0["ordem"] = t0.groupby("dia").cumcount() + 1
    abre = pd.to_datetime(t0["tempo_entrada"])
    t0["min"] = (abre.dt.hour * 60 + abre.dt.minute) - (9 * 60 + 15)
    print("\n  B) O SINAL QUE SERIA EVITADO (1o trade do dia, sem custo)")
    for k, g in t0.groupby(t0["ordem"].clip(upper=3)):
        x = m(g)
        print(f"    {k}{'+' if k == 3 else ''}o trade do dia: {x['n']:>5} trades  "
              f"{x['r']:+.3f}R ({x['s']:+.1f}s)  acerto {(g['resultado'] > 0).mean():.0%}")
    p1 = t0[t0["ordem"] == 1]
    print(f"\n    minutos apos a abertura ate o 1o trade: mediana {p1['min'].median():.0f}, "
          f"25% ate {p1['min'].quantile(.25):.0f}, 75% ate {p1['min'].quantile(.75):.0f}")
    for rot, faixa in [("nos primeiros 10 min", p1["min"] < 10),
                       ("10 a 30 min", (p1["min"] >= 10) & (p1["min"] < 30)),
                       ("depois de 30 min", p1["min"] >= 30)]:
        g = p1[faixa]
        x = m(g)
        print(f"    1o trade {rot:<22}{x['n']:>5}  {x['r']:+.3f}R ({x['s']:+.1f}s)")

    print("\n  C) POR ANO - evita 1 sinal x nao evita (sem custo)")
    a = simular(DF, replace(AUTOR, pular_sinais=1), SEM)
    for ano in range(2022, 2027):
        x = m(t0[pd.to_datetime(t0["tempo_entrada"]).dt.year == ano])
        y = m(a[pd.to_datetime(a["tempo_entrada"]).dt.year == ano])
        print(f"    {ano}   nao evita {x['r']:+.3f}R ({x['s']:+.1f}s)   evita 1 {y['r']:+.3f}R ({y['s']:+.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
