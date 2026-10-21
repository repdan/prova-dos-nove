"""
Grade no ouro M15 com gestao SEMANAL (regra de gestao semanal).

    .venv/Scripts/python.exe -m analises.grade_ouro_semanal

Canal diario como sempre; os limites valem para a semana: 1 gain encerra a
semana, 2 stops tambem. So opera de domingo a quarta no horario de Brasilia,
que na corretora sao os blocos de segunda, terca e quarta (o bloco de segunda
abre no domingo a noite em Brasilia).
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
from analises.grade_tempo_grafico import CANAIS, AUTOR, MERCADOS, carregar, fr, m  # noqa: E402
from strategy.grade import Custos, simular                                          # noqa: E402

TF = "M15"
VERSOES = {
    "semanal, dom-qua (sua regra)": dict(gestao_semanal=True, dias_semana=(0, 1, 2)),
    "semanal, dom-qui": dict(gestao_semanal=True, dias_semana=(0, 1, 2, 3)),
    "semanal, todos os dias": dict(gestao_semanal=True),
    "diaria (referencia)": dict(),
}
ABERTURAS = ["ouro corretora", "ouro Londres", "ouro NY"]


def rodar(spec):
    ab, versao, canal, com_custo, inv = spec
    p = replace(MERCADOS[ab]["p"], **CANAIS[canal], **VERSOES[versao], controle_inverter=inv)
    c = MERCADOS[ab]["custo"] if com_custo else Custos(0, 0, 0.0)
    return spec, simular(carregar(ab, TF), p, c)


def por_semana(t: pd.DataFrame) -> dict:
    s = t.groupby(pd.to_datetime(t["tempo_entrada"]).dt.to_period("W"))["r"].sum()
    return {"semanas": len(s), "sem_pos": (s > 0).mean(), "r_sem": s.mean()}


def main() -> int:
    specs = [(ab, v, cn, c, inv) for ab in ABERTURAS for v in VERSOES for cn in CANAIS
             for c, inv in ((False, False), (False, True), (True, False))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))
    for ab in ABERTURAS:
        print(f"\n  {ab.upper()} - M15, 2019-2026, spread 0,21")
        print(f"  {'versao / canal':<42}{'trades':>7}{'sem custo':>16}{'ESPELHO':>16}{'com custo':>16}"
              f"{'semanas':>9}{'sem. +':>8}{'R/sem':>8}")
        print("  " + "-" * 120)
        for v in VERSOES:
            for cn in CANAIS:
                sem, esp = m(res[(ab, v, cn, False, False)]), m(res[(ab, v, cn, False, True)])
                tc = res[(ab, v, cn, True, False)]
                com, ps = m(tc), por_semana(tc)
                print(f"  {v + ' / ' + cn:<42}{sem['n']:>7}{fr(sem):>16}{fr(esp):>16}{fr(com):>16}"
                      f"{ps['semanas']:>9}{ps['sem_pos']:>8.0%}{ps['r_sem']:>+8.3f}")
    print("\n  Por ano, sua regra (dom-qua), canal 1a vela, com custo:")
    for ab in ABERTURAS:
        t = res[(ab, "semanal, dom-qua (sua regra)", "1a vela", True, False)]
        anos = pd.to_datetime(t["tempo_entrada"]).dt.year
        print(f"    {ab:<16}" + "  ".join(f"{a}:{m(g)['r']:+.2f}" for a, g in t.groupby(anos)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
