"""
Grade no ouro (abertura de NY, canal na 1a vela): carregar a posicao para o
dia seguinte em vez de fechar no fim do dia?

    .venv/Scripts/python.exe -m analises.grade_ouro_carregar

Variantes: fecha no fim do dia / carrega ate sexta / carrega sempre, e uma
versao "deixa correr" (sem alvo, sai por stop ou 0x0). Custo inclui o swap
atual do ouro: comprado paga 0,66 por noite, vendido recebe 0,34, quarta triplo.
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
from analises.grade_tempo_grafico import CANAIS, AUTOR, carregar, fr, m  # noqa: E402
from strategy.grade import Custos, simular                                # noqa: E402

CUSTO = Custos(0.02, 0.001, 0.21, swap_compra=-0.66, swap_venda=0.34, dia_triplo=2)
BASE = replace(AUTOR, tendencia="neutra", **CANAIS["1a vela"])
GESTOES = {"semanal dom-qua": dict(gestao_semanal=True, dias_semana=(0, 1, 2)), "diaria": dict()}
POSICAO = {
    "alvo 1,5: fecha no fim do dia": dict(carregar_posicao="nao"),
    "alvo 1,5: carrega ate sexta": dict(carregar_posicao="semana"),
    "sem alvo, sem surfar: ate sexta": dict(carregar_posicao="semana", take_niveis=0),
    "surfando: fecha no fim do dia": dict(carregar_posicao="nao", take_niveis=0, surfar=True),
    "surfando: carrega ate sexta": dict(carregar_posicao="semana", take_niveis=0, surfar=True),
    "surfando: carrega sempre": dict(carregar_posicao="sempre", take_niveis=0, surfar=True),
}
TFS = ("M15", "M30", "H1")


def rodar(spec):
    tf, g, pos, com_custo, inv = spec
    p = replace(BASE, **GESTOES[g], **POSICAO[pos], controle_inverter=inv)
    return spec, simular(carregar("ouro NY", tf), p, CUSTO if com_custo else Custos(0, 0, 0.0))


def main() -> int:
    specs = [(tf, g, ps, c, inv) for tf in TFS for g in GESTOES for ps in POSICAO
             for c, inv in ((False, False), (False, True), (True, False), (True, True))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))
    for tf in TFS:
        for g in GESTOES:
            print(f"\n  OURO NY {tf}, gestao {g}")
            print(f"  {'posicao':<34}{'trades':>7}{'acerto':>8}{'sem custo':>16}{'ESPELHO':>16}"
                  f"{'com custo':>16}{'ESP c/custo':>16}{'dias max':>9}{'R/ano':>8}")
            print("  " + "-" * 130)
            for ps in POSICAO:
                sem, esp = m(res[(tf, g, ps, False, False)]), m(res[(tf, g, ps, False, True)])
                tc = res[(tf, g, ps, True, False)]
                com, espc = m(tc), m(res[(tf, g, ps, True, True)])
                dur = (pd.to_datetime(tc["tempo_saida"]) - pd.to_datetime(tc["tempo_entrada"])).dt.total_seconds() / 86400
                anos = (pd.to_datetime(tc["tempo_saida"]).max() - pd.to_datetime(tc["tempo_entrada"]).min()).days / 365.25
                print(f"  {ps:<34}{sem['n']:>7}{(tc['resultado'] > 0).mean():>8.0%}{fr(sem):>16}{fr(esp):>16}"
                      f"{fr(com):>16}{fr(espc):>16}{dur.max():>9.1f}{tc['r'].sum() / anos:>+8.1f}")
    print("\n  Por ano, com custo e swap (metodo | espelho):")
    for tf in ("M15", "M30"):
        for ps in ("surfando: carrega ate sexta", "surfando: carrega sempre", "sem alvo, sem surfar: ate sexta"):
            t, e = res[(tf, "semanal dom-qua", ps, True, False)], res[(tf, "semanal dom-qua", ps, True, True)]
            ya, ye = pd.to_datetime(t["tempo_entrada"]).dt.year, pd.to_datetime(e["tempo_entrada"]).dt.year
            print(f"    {tf} semanal, {ps:<32} " + "  ".join(
                f"{a}:{m(g)['r']:+.2f}|{m(e[ye == a])['r']:+.2f}" for a, g in t.groupby(ya)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
