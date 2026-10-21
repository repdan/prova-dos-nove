"""
Grade no ouro (XAUUSD), M15 e M1, sem as regras de gap do HK50.

    .venv/Scripts/python.exe -m analises.grade_ouro M15
    .venv/Scripts/python.exe -m analises.grade_ouro M1

Abertura: o ouro nao tem pregao com gap; o canal e marcado nas primeiras velas
depois de tres "aberturas" possiveis (horario do servidor, EET):
  corretora 01:00  inicio do dia da corretora, apos a pausa diaria (Asia)
  londres   10:00  abertura de Londres (08:00 em Londres)
  ny        16:30  abertura da bolsa de Nova York (09:30 ET; desalinha ~3
                   semanas por ano, quando os horarios de verao nao coincidem)
Tendencia inicial neutra (a primeira saida da caixa define) ou pelo dia anterior.
Custo: spread historico de cada vela, e o spread medido ao vivo (0,21 USD).
Dados a partir de 2019 (2017-18 sao esparsos nesta corretora).
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
from strategy.grade import Custos, ParametrosGrade, simular   # noqa: E402

ABERTURAS = {"corretora": None, "londres": (10, 0), "ny": (16, 30)}
CUSTOS = {"sem": Custos(0, 0, 0.0),
          "hist": Custos(slippage=0.02, comissao_pontos=0.001),
          "0.21": Custos(slippage=0.02, comissao_pontos=0.001, spread_forcado=0.21)}

REFERENCIA = ParametrosGrade(tendencia="neutra", sem_entrada_antes_do_fim_min=30)
AUTOR = replace(REFERENCIA, max_stops_dia=2, take_niveis=1.5)
PRIMEIRA = dict(velas_minimas=1, velas_maximas=1, largura_minima=0.0, usar_vela_gigante=False)
QUATRO = dict(canal_modo="alvo", canal_alvo_pct=0.25)

_CACHE: dict = {}


def carregar(tf: str, abertura: str) -> pd.DataFrame:
    chave = (tf, abertura)
    if chave not in _CACHE:
        d = pd.read_parquet(RAIZ / "data" / "historico" / "XAUUSD" / f"XAUUSD_{tf}_dias.parquet")
        d = d[d["tempo_ativo"].dt.year >= 2019]
        h = ABERTURAS[abertura]
        if h is not None:
            ts = d["tempo_servidor"]
            d = d[(ts.dt.hour > h[0]) | ((ts.dt.hour == h[0]) & (ts.dt.minute >= h[1]))]
        _CACHE[chave] = d.reset_index(drop=True)
    return _CACHE[chave]


def rodar(spec: tuple) -> tuple:
    tf, abertura, p, custo, inverter = spec
    if inverter:
        p = replace(p, controle_inverter=True)
    t = simular(carregar(tf, abertura), p, CUSTOS[custo])
    return spec, t


def m(t: pd.DataFrame) -> dict:
    if t is None or t.empty:
        return {"n": 0, "r": np.nan, "s": np.nan, "dias": 0, "w": np.nan, "cr": np.nan}
    r = t["r"].dropna()
    e = r.std() / np.sqrt(len(r))
    return {"n": len(r), "r": r.mean(), "s": r.mean() / e, "dias": t["dia"].nunique(),
            "w": t["largura"].median(), "cr": (t["custo"] / t["risco"]).median()}


def fr(x: dict) -> str:
    return f"{x['r']:+.3f}R {x['s']:+5.1f}s"


def calibracao(tf: str) -> None:
    print(f"\n  CALIBRACAO {tf}: tamanho do canal de abertura (mediana por ano)")
    print(f"  {'abertura':<11}{'ano':>6}{'preco':>8}{'1a vela USD':>13}{'%':>7}"
          f"{'4 velas USD':>13}{'%':>7}")
    for ab in ABERTURAS:
        d = carregar(tf, ab)
        g = d.groupby(d["tempo_ativo"].dt.date)
        x = pd.DataFrame({"ano": g["tempo_ativo"].first().dt.year,
                          "preco": g["abertura"].first(),
                          "v1": g.apply(lambda b: b["maxima"].iloc[0] - b["minima"].iloc[0]),
                          "v4": g.apply(lambda b: b["maxima"].iloc[:4].max() - b["minima"].iloc[:4].min())})
        for ano, y in x.groupby("ano"):
            print(f"  {ab:<11}{ano:>6}{y['preco'].median():>8.0f}{y['v1'].median():>13.2f}"
                  f"{100 * (y['v1'] / y['preco']).median():>6.2f}%{y['v4'].median():>13.2f}"
                  f"{100 * (y['v4'] / y['preco']).median():>6.2f}%")


def main() -> int:
    tf = sys.argv[1] if len(sys.argv) > 1 else "M15"
    calibracao(tf)

    linhas = []   # (secao, rotulo, abertura, params)
    for ab in ABERTURAS:
        linhas.append(("A", f"{ab}: canal na 1a vela", ab, replace(AUTOR, **PRIMEIRA)))
        linhas.append(("A", f"{ab}: canal nas 4 (0,25%)", ab, replace(AUTOR, **QUATRO)))
    for ab in ABERTURAS:
        for pct in (0.10, 0.15, 0.35, 0.50):
            linhas.append(("B", f"{ab}: 4 velas, {pct:.2f}%", ab,
                           replace(AUTOR, **{**QUATRO, "canal_alvo_pct": pct})))
    for ab in ABERTURAS:
        linhas.append(("C", f"{ab}: tendencia do dia anterior", ab,
                       replace(AUTOR, **QUATRO, tendencia="dia_anterior")))
    for ab in ABERTURAS:
        linhas.append(("D", f"{ab}: gestao de referencia (alvo 1, 3 stops)", ab, replace(REFERENCIA, **QUATRO)))
        linhas.append(("D", f"{ab}: sua gestao, evita a 1a ordem", ab,
                       replace(AUTOR, **QUATRO, pular_sinais=1)))

    specs = []
    for _, _, ab, p in linhas:
        specs += [(tf, ab, p, "sem", False), (tf, ab, p, "sem", True),
                  (tf, ab, p, "hist", False), (tf, ab, p, "0.21", False)]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))

    titulos = {"A": "A) CANAL NA 1a VELA x NAS 4 PRIMEIRAS (sua gestao: alvo 1,5 canal, 2 stops, 1 gain)",
               "B": "B) PLATO DO CANAL DE 4 VELAS (% do preco)",
               "C": "C) TENDENCIA INICIAL PELO DIA ANTERIOR (canal 4 velas 0,25%)",
               "D": "D) GESTAO E PRIMEIRA ORDEM (canal 4 velas 0,25%)"}
    secao = None
    for sec, rot, ab, p in linhas:
        if sec != secao:
            secao = sec
            print(f"\n  {titulos[sec]}")
            print(f"  {'':<42}{'dias':>6}{'trades':>7}{'w USD':>7}{'sem custo':>16}{'ESPELHO':>16}"
                  f"{'spread hist':>16}{'spread 0.21':>16}{'custo':>7}")
            print("  " + "-" * 133)
        sem = m(res[(tf, ab, p, "sem", False)])
        esp = m(res[(tf, ab, p, "sem", True)])
        hist = m(res[(tf, ab, p, "hist", False)])
        atual = m(res[(tf, ab, p, "0.21", False)])
        print(f"  {rot:<42}{sem['dias']:>6}{sem['n']:>7}{sem['w']:>7.2f}{fr(sem):>16}{fr(esp):>16}"
              f"{fr(hist):>16}{fr(atual):>16}{atual['cr']:>6.2f}R")

    print("\n  E) POR ANO, sem custo (sua gestao, canal 4 velas 0,25%)")
    for ab in ABERTURAS:
        p = replace(AUTOR, **QUATRO)
        t, e = res[(tf, ab, p, "sem", False)], res[(tf, ab, p, "sem", True)]
        anos = pd.to_datetime(t["tempo_entrada"]).dt.year
        anos_e = pd.to_datetime(e["tempo_entrada"]).dt.year
        print(f"    {ab:<10} metodo  " + "  ".join(f"{a}:{m(g)['r']:+.2f}" for a, g in t.groupby(anos)))
        print(f"    {'':<10} espelho " + "  ".join(f"{a}:{m(g)['r']:+.2f}" for a, g in e.groupby(anos_e)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

