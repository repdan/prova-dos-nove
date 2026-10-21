"""
Grade no M1 com a gestao proposta pelo autor:
  1 gain por dia, no maximo 2 stops por dia, take a 1,5R, 0x0 sempre.

    .venv/Scripts/python.exe analises/grade_regras_autor.py

O gatilho do 0x0 nao foi especificado; testa 0,5R / 0,75R / 1R / 1 nivel.
Toda linha traz o espelho (mesmas entradas no sentido oposto) como regua.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rodar_grade import REFERENCIA, carregar                      # noqa: E402
from strategy.grade import Custos, simular                   # noqa: E402

AUTOR = replace(REFERENCIA, parar_no_take=True, max_stops_dia=2, take_r=1.5,
                usar_0x0=True, gatilho_0x0_r=1.0)
SEM = Custos(0, 0, 0.0)
BAIXO = Custos(0.25, 0.78, 1.6)    # melhor spread que a corretora ja teve (2025)
ATUAL = Custos(0.5, 0.78, 4.5)     # spread de hoje


def m(t: pd.DataFrame) -> dict:
    r = t["r"].dropna()
    e = r.std() / np.sqrt(len(r))
    dia = t.groupby("dia")["r"].sum()
    return {"n": len(r), "ac": (t["resultado"] > 0).mean(), "r": r.mean(),
            "s": r.mean() / e, "pts": t["resultado"].mean(),
            "dias_pos": (dia > 0).mean(), "r_dia": dia.mean(), "t_dia": len(r) / len(dia)}


def fmt(x: dict) -> str:
    return f"{x['r']:+.3f}R {x['s']:+5.1f}s"


def linha(rot: str, p) -> None:
    sem, esp = m(simular(DF, p, SEM)), m(simular(DF, replace(p, controle_inverter=True), SEM))
    bx, at = m(simular(DF, p, BAIXO)), m(simular(DF, p, ATUAL))
    print(f"  {rot:<30}{sem['n']:>6}{sem['t_dia']:>6.2f}{sem['ac']:>6.0%}"
          f"{fmt(sem):>17}{fmt(esp):>17}{fmt(bx):>17}{fmt(at):>17}"
          f"{at['dias_pos']:>8.0%}")


def cab(t: str) -> None:
    print(f"\n  {t}")
    print(f"  {'':<30}{'trades':>6}{'/dia':>6}{'acerto':>6}{'sem custo':>17}"
          f"{'ESPELHO s/custo':>17}{'spread 1.6':>17}{'spread 4.5':>17}{'dias +':>8}")
    print("  " + "-" * 123)


DF = carregar("M1")


def main() -> int:
    cab("A) SUA VERSAO - gatilho do 0x0")
    for rot, g in [("0x0 em 0,5R", 0.5), ("0x0 em 0,75R", 0.75),
                   ("0x0 em 1R", 1.0), ("0x0 em 1 nivel (referencia)", None)]:
        linha(rot, replace(AUTOR, gatilho_0x0_r=g))

    cab("B) SEGUIDOR DE TENDENCIA - sem reversao (0x0 em 1R)")
    linha("so a favor (continuacao + 50%)", replace(AUTOR, entrada_reversao=False))
    linha("so continuacao", replace(AUTOR, entrada_reversao=False, entrada_50=False))
    linha("so 50%", replace(AUTOR, entrada_reversao=False, entrada_continuacao=False))

    cab("C) PLATO - alvo em R (0x0 em 1R; alvo 1R sem 0x0)")
    for k in (1.0, 1.25, 1.5, 2.0, 3.0):
        p = replace(AUTOR, take_r=k)
        if k <= 1.0:
            p = replace(p, usar_0x0=False)
        linha(f"take {k}R", p)

    cab("D) PLATO - stops por dia (take 1,5R, 0x0 em 1R)")
    for s in (1, 2, 3, 99):
        linha(f"max {s} stops" if s < 99 else "sem limite", replace(AUTOR, max_stops_dia=s))

    print("\n  E) POR ANO - sua versao (0x0 em 1R), sem custo, metodo x espelho")
    t = simular(DF, AUTOR, SEM)
    e = simular(DF, replace(AUTOR, controle_inverter=True), SEM)
    for ano in range(2022, 2027):
        a = t[pd.to_datetime(t["tempo_entrada"]).dt.year == ano]
        b = e[pd.to_datetime(e["tempo_entrada"]).dt.year == ano]
        print(f"    {ano}  metodo {fmt(m(a))} {m(a)['pts']:+5.1f} pts   espelho {fmt(m(b))}")

    t = simular(DF, AUTOR, ATUAL)
    print("\n  F) SUA VERSAO, spread 4.5: saidas")
    for k, g in t.groupby("motivo"):
        print(f"    {k:<12}{len(g):>6}  {g['r'].mean():+.2f}R  {g['resultado'].mean():+.1f} pts")
    print(f"    risco mediano {t['risco'].median():.0f} pts, custo {t['custo'].mean():.1f} pts "
          f"= {(t['custo'] / t['risco']).median():.2f}R por trade")
    return 0


if __name__ == "__main__":
    sys.exit(main())
