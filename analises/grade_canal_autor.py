"""
Grade M1 - o canal como o autor marcava, e os sinais de lateralidade.

    .venv/Scripts/python.exe analises/grade_canal_autor.py

A) Canal "de 45, 50 pontos" tirado das 4 primeiras velas (pavio e corpo),
   faixa 40-60, contra o canal atual (1a vela). Com e sem o primeiro preco do
   dia como borda, e com "nao opera" quando nao da para formar 40-60.
   Plato: alvos de 30 a 90 pontos.
B) Previsores de lateralidade, medidos contra o que o dia FEZ depois:
   - tamanho da 1a vela e das 4 primeiras;
   - gap concordando ou nao com a direcao do dia anterior.
   "Lateral" = eficiencia baixa: |fechamento - abertura| / (maxima - minima).
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

VERSAO = replace(REFERENCIA, parar_no_take=True, max_stops_dia=2, take_niveis=1.5, usar_0x0=True)
SEM, BAIXO, ATUAL = Custos(0, 0, 0.0), Custos(0.25, 0.78, 1.6), Custos(0.5, 0.78, 4.5)
DF = carregar("M1")


def m(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"n": 0, "r": np.nan, "s": np.nan, "dias": 0, "w": np.nan}
    r = t["r"].dropna()
    e = r.std() / np.sqrt(len(r))
    return {"n": len(r), "r": r.mean(), "s": r.mean() / e, "dias": t["dia"].nunique(),
            "w": t["largura"].median()}


def f(x: dict) -> str:
    return f"{x['r']:+.3f}R {x['s']:+5.1f}s"


def linha(rot: str, p) -> None:
    sem, esp = m(simular(DF, p, SEM)), m(simular(DF, replace(p, controle_inverter=True), SEM))
    bx, at = m(simular(DF, p, BAIXO)), m(simular(DF, p, ATUAL))
    print(f"  {rot:<40}{sem['dias']:>6}{sem['n']:>7}{sem['w']:>6.0f}{f(sem):>17}"
          f"{f(esp):>17}{f(bx):>17}{f(at):>17}")


def cab(t: str) -> None:
    print(f"\n  {t}")
    print(f"  {'':<40}{'dias':>6}{'trades':>7}{'w':>6}{'sem custo':>17}{'ESPELHO':>17}"
          f"{'spread 1.6':>17}{'spread 4.5':>17}")
    print("  " + "-" * 126)


def dias_info() -> pd.DataFrame:
    """Uma linha por pregao: o que se sabia na abertura e o que o dia fez."""
    linhas, ant = [], None
    for dia, b in DF.groupby(DF["tempo_ativo"].dt.date, sort=True):
        b = b.reset_index(drop=True)
        if len(b) < 300:
            ant = b
            continue
        o, c = b["abertura"].iloc[0], b["fechamento"].iloc[-1]
        hi, lo = b["maxima"].max(), b["minima"].min()
        info = {"dia": dia, "ano": dia.year,
                "vela1": b["maxima"].iloc[0] - b["minima"].iloc[0],
                "velas4": b["maxima"].iloc[:4].max() - b["minima"].iloc[:4].min(),
                "amplitude": hi - lo,
                "eficiencia": abs(c - o) / (hi - lo) if hi > lo else 0.0}
        if ant is not None:
            gap = np.sign(o - ant["fechamento"].iloc[-1])
            dir_ant = np.sign(ant["fechamento"].iloc[-1] - ant["abertura"].iloc[0])
            info["concorda"] = bool(gap == dir_ant and gap != 0)
        linhas.append(info)
        ant = b
    return pd.DataFrame(linhas)


def main() -> int:
    alvo = replace(VERSAO, canal_modo="alvo")
    cab("A) CANAL - sua versao de gestao (1 gain, 2 stops, take 1,5 canal, 0x0 1 canal)")
    linha("atual: 1a vela", VERSAO)
    linha("4 velas, alvo 50 (40-60), mais proximo", alvo)
    linha("4 velas, alvo 50 (40-60), nao opera fora", replace(alvo, canal_fora_da_faixa="nao_opera"))
    linha("  + primeiro preco como borda", replace(alvo, canal_primeiro_preco=True))
    linha("  + primeiro preco, nao opera fora", replace(alvo, canal_primeiro_preco=True,
                                                      canal_fora_da_faixa="nao_opera"))

    cab("A2) PLATO - alvo do canal (faixa = alvo +-10, nao opera fora)")
    for a in (30, 40, 50, 60, 70, 90):
        linha(f"alvo {a} ({a - 10}-{a + 10})", replace(alvo, canal_alvo=a, canal_faixa=(a - 10, a + 10),
                                                         canal_fora_da_faixa="nao_opera"))

    # ------------------------------------------------------------------ B
    d = dias_info()
    t = simular(DF, alvo, SEM)
    r_dia = t.groupby("dia")["r"].sum()
    d["r_dia"] = d["dia"].map(r_dia).fillna(0.0)
    d["operou"] = d["dia"].isin(r_dia.index)

    print("\n  B) PREVISORES DE LATERALIDADE (M1, 2022-2026)")
    print("\n  Tamanho da 1a vela por ano (mediana, pontos) - 'a 1a vela ficou pequena'?")
    print("  " + d.groupby("ano")[["vela1", "velas4", "amplitude"]].median().round(0).to_string().replace("\n", "\n  "))

    def tabela(col: str, rot: str) -> None:
        print(f"\n  {rot}")
        print(f"  {'grupo':<22}{'dias':>6}{'eficiencia':>12}{'amplitude':>11}"
              f"{'R/dia s/custo':>15}")
        for k, g in d.groupby(col, observed=True):
            print(f"  {str(k):<22}{len(g):>6}{g['eficiencia'].mean():>12.2f}"
                  f"{g['amplitude'].median():>11.0f}{g['r_dia'].mean():>+15.3f}")

    # Quintis DENTRO de cada ano: o patamar de pontos mudou com o tempo.
    d["q_vela1"] = d.groupby("ano")["vela1"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=["1 menor", "2", "3", "4", "5 maior"]))
    tabela("q_vela1", "Tamanho da 1a vela (quintil dentro do ano)")
    d["faixa4"] = pd.cut(d["velas4"], [0, 40, 60, 1e9], labels=["4 velas < 40", "40-60", "> 60"])
    tabela("faixa4", "Amplitude das 4 primeiras velas")
    tabela("concorda", "Gap concorda com a direcao do dia anterior")

    c = d.dropna(subset=["concorda"])
    print(f"\n  Correlacao (Spearman) com a eficiencia do dia: "
          f"1a vela {d['vela1'].corr(d['eficiencia'], method='spearman'):+.2f}, "
          f"4 velas {d['velas4'].corr(d['eficiencia'], method='spearman'):+.2f}, "
          f"amplitude do dia x 1a vela {d['vela1'].corr(d['amplitude'], method='spearman'):+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
