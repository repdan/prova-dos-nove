"""
Grade M1: a vantagem bruta sobrevive a algum custo realista? E e estavel por ano?

    .venv/Scripts/python.exe analises/grade_custo_m1.py
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

VARIANTES = {
    "referencia (take 1)": {},
    "sem take": {"take_niveis": 0},
    "2 para 2": {"stop_niveis": 2, "take_niveis": 2},
    "take 2": {"take_niveis": 2},
}
CENARIOS = {
    "sem custo": Custos(0, 0, 0.0),
    "so comissao (0.78)": Custos(0, 0.78, 0.0),
    "spread 1.6, slip 0.25": Custos(0.25, 0.78, 1.6),
    "spread 1.6, slip 0.5": Custos(0.5, 0.78, 1.6),
    "spread 4.5, slip 0.5": Custos(0.5, 0.78, 4.5),
}


def resumo(t: pd.DataFrame) -> str:
    r = t["r"].dropna()
    e = r.std() / np.sqrt(len(r))
    return f"{r.mean():+.3f} R ({r.mean() / e:+.1f}s) {t['resultado'].mean():+5.1f} pts"


def main() -> int:
    df = carregar("M1")
    print(f"\n  {'variante':<16}" + "".join(f"{c:>30}" for c in CENARIOS))
    brutos = {}
    for nome, kw in VARIANTES.items():
        p = replace(REFERENCIA, **kw)
        linha = f"  {nome:<16}"
        for cn, c in CENARIOS.items():
            t = simular(df, p, c)
            if cn == "sem custo":
                brutos[nome] = t
            linha += f"{resumo(t):>30}"
        print(linha)

    print("\n  Bruto (sem custo) por ano - metodo x espelho:")
    for nome, kw in VARIANTES.items():
        p = replace(REFERENCIA, **kw)
        esp = simular(df, replace(p, controle_inverter=True), Custos(0, 0, 0.0))
        m = brutos[nome]
        print(f"\n  {nome}")
        for ano in sorted(pd.to_datetime(m["tempo_entrada"]).dt.year.unique()):
            a = m[pd.to_datetime(m["tempo_entrada"]).dt.year == ano]
            b = esp[pd.to_datetime(esp["tempo_entrada"]).dt.year == ano]
            print(f"    {ano}   metodo {resumo(a)}   espelho {resumo(b)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
