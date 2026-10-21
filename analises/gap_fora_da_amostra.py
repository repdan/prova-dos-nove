"""
"A favor do gap" - hipotese nascida no HK50, testada FORA DA AMOSTRA.

    .venv/Scripts/python.exe -m analises.gap_fora_da_amostra

Regra fixada ANTES de olhar FR40, ES35 e CN50 (nenhum parametro ajustado
depois): na fase de gap, todo sinal que o trade de fechamento tomaria e tomado
no sentido do gap - mesma distancia de risco, alvo = distancia ate a linha
projetada a favor do gap. 1 gain/dia, 2 stops, 0x0 em 1 canal. Canal da 1a
vela relativo a volatilidade (50 pontos nao servem para outro indice).
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

from analises.grade_canal_autor import DF as HK50, VERSAO, f, m
from strategy.grade import Custos
from strategy.grade_gap import ParametrosGap, simular_gap

RAIZ = Path(__file__).resolve().parent.parent
P = replace(VERSAO, parar_no_take=True)                      # canal "velas"
G = ParametrosGap(operar_continuacao=False, operar_grade=False)
A_FAVOR = replace(P, controle_inverter=True)


def custos(meta: dict) -> Custos:
    """Spread real de cada vela, derrapagem de 10% do spread, comissao de 0,1 USD/lote."""
    return Custos(slippage=0.1 * meta["spread_mediano_hist"],
                  comissao_pontos=0.1 / meta["usd_por_ponto_lote"])


def main() -> int:
    meta = json.loads((RAIZ / "data" / "historico" / "OOS" / "meta.json").read_text())
    mercados = {"HK50 (dentro da amostra)": (HK50, Custos(0.5, 0.78, 4.5))}
    for s in ("FR40", "ES35", "CN50"):
        mercados[s] = (pd.read_parquet(RAIZ / "data" / "historico" / "OOS" / f"{s}_M1_dias.parquet"),
                       custos(meta[s]))

    print(f"\n  {'mercado':<26}{'trades':>7}{'A FAVOR s/custo':>18}{'A FAVOR c/custo':>18}"
          f"{'CONTRA s/custo':>18}{'custo/risco':>12}")
    print("  " + "-" * 99)
    anuais = {}
    for nome, (df, c) in mercados.items():
        sem = simular_gap(df, A_FAVOR, G, Custos(0, 0, 0.0))
        com = simular_gap(df, A_FAVOR, G, c)
        contra = simular_gap(df, P, G, Custos(0, 0, 0.0))
        cr = (com["custo"] / com["risco"]).median()
        print(f"  {nome:<26}{len(sem):>7}{f(m(sem)):>18}{f(m(com)):>18}{f(m(contra)):>18}{cr:>11.2f}R")
        anuais[nome] = sem

    print("\n  Por ano, a favor do gap, sem custo:")
    for nome, t in anuais.items():
        anos = pd.to_datetime(t["tempo_entrada"]).dt.year
        print(f"    {nome:<26}" + "  ".join(f"{a}:{m(g)['r']:+.2f}" for a, g in t.groupby(anos)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
