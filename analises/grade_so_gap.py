"""
Grade "so gap" no M1 do HK50.

    .venv/Scripts/python.exe -m analises.grade_so_gap

A) estrategia completa (com e sem parar no primeiro gain);
B) cada peca sozinha: fechamento do gap, continuacao, Grade apos rejeicao;
C) plato dos parametros;
D) fatos do gap, sem operar: quanto fecha, e se depois de romper a linha o
   preco anda |G| pontos alem dela antes de voltar 1 canal.
"""
from __future__ import annotations

import sys
from dataclasses import replace

import numpy as np
import pandas as pd

from analises.grade_canal_autor import ATUAL, BAIXO, DF, SEM, VERSAO, f, m
from strategy.grade_gap import ParametrosGap, simular_gap

P = replace(VERSAO, canal_modo="alvo", parar_no_take=False)
G = ParametrosGap()


def linha(rot: str, p, g) -> None:
    sem = m(simular_gap(DF, p, g, SEM))
    esp = m(simular_gap(DF, replace(p, controle_inverter=True), g, SEM))
    bx, at = m(simular_gap(DF, p, g, BAIXO)), m(simular_gap(DF, p, g, ATUAL))
    print(f"  {rot:<40}{sem['dias']:>6}{sem['n']:>7}{f(sem):>17}{f(esp):>17}{f(bx):>17}{f(at):>17}")


def cab(t: str) -> None:
    print(f"\n  {t}")
    print(f"  {'':<40}{'dias':>6}{'trades':>7}{'sem custo':>17}{'ESPELHO':>17}"
          f"{'spread 1.6':>17}{'spread 4.5':>17}")
    print("  " + "-" * 120)


def fatos() -> None:
    """D) o que o gap faz, sem estrategia nenhuma."""
    linhas, ant = [], None
    for dia, b in DF.groupby(DF["tempo_ativo"].dt.date, sort=True):
        b = b.reset_index(drop=True)
        if ant is None or len(b) < 300:
            ant = b
            continue
        L, o = ant["fechamento"].iloc[-1], b["abertura"].iloc[0]
        G_ = o - L
        if G_ == 0:
            ant = b
            continue
        dg = np.sign(G_)
        mn, mx, fc = b["minima"].to_numpy(), b["maxima"].to_numpy(), b["fechamento"].to_numpy()
        toca = (mn <= L) if dg > 0 else (mx >= L)
        rompe = (fc < L) if dg > 0 else (fc > L)
        info = {"gap": abs(G_), "fechou": bool(toca.any()), "rompeu": bool(rompe.any())}
        if rompe.any():
            i = int(np.argmax(rompe))
            alvo, w = L - dg * abs(G_), 50.0
            stop = L + dg * w
            resto_mn, resto_mx, resto_f = mn[i + 1:], mx[i + 1:], fc[i + 1:]
            bate_alvo = (resto_mn <= alvo) if dg > 0 else (resto_mx >= alvo)
            bate_stop = (resto_f > stop) if dg > 0 else (resto_f < stop)
            ia = np.argmax(bate_alvo) if bate_alvo.any() else 10**9
            is_ = np.argmax(bate_stop) if bate_stop.any() else 10**9
            info["seguiu"] = "alvo" if ia < is_ else "stop" if is_ < ia else "nenhum"
        linhas.append(info)
        ant = b
    d = pd.DataFrame(linhas)
    d["faixa"] = pd.cut(d["gap"], [0, 50, 100, 200, 400, 1e9],
                        labels=["< 50", "50-100", "100-200", "200-400", "> 400"])
    print("\n  D) FATOS DO GAP (M1, 2022-2026) - sem operar")
    print(f"  {'gap (pts)':<12}{'dias':>6}{'fecha no dia':>14}{'rompe a linha':>15}"
          f"{'depois de romper: alvo |G|':>28}{'stop (1 canal)':>16}")
    for k, g in d.groupby("faixa", observed=True):
        r = g[g["rompeu"]]
        n = max(len(r), 1)
        print(f"  {str(k):<12}{len(g):>6}{g['fechou'].mean():>14.0%}{g['rompeu'].mean():>15.0%}"
              f"{(r['seguiu'] == 'alvo').sum() / n:>28.0%}{(r['seguiu'] == 'stop').sum() / n:>16.0%}")


def main() -> int:
    cab("A) ESTRATEGIA COMPLETA (canal de 4 velas, take 1,5 canal na grade cru)")
    linha("so gap, para no 1o gain", replace(P, parar_no_take=True), G)
    linha("so gap, nao para no gain", P, G)
    linha("referencia: Grade normal (sua versao)", None, None) if False else None

    cab("B) CADA PECA SOZINHA (nao para no gain)")
    linha("so fechamento do gap", P, replace(G, operar_continuacao=False, operar_grade=False))
    linha("  sem a entrada agressiva na ZR", P, replace(G, operar_continuacao=False,
                                                       operar_grade=False, entrar_na_zn=False))
    linha("so continuacao (rompeu a linha)", P, replace(G, operar_preenchimento=False, operar_grade=False))
    linha("so Grade depois de tocar e voltar", P, replace(G, operar_preenchimento=False,
                                                           operar_continuacao=False))

    cab("C) PLATO (estrategia completa, nao para no gain)")
    for e in (0.5, 1.5, 2.0):
        linha(f"espaco minimo ate L = {e}R", P, replace(G, espaco_min_r=e))
    for gm in (50, 100, 200):
        linha(f"so gaps >= {gm} pts", P, replace(G, gap_minimo=gm))
    linha("continuacao: alvo meio gap", P, replace(G, alvo_gap=0.5))
    linha("continuacao: stop 2 canais", P, replace(G, stop_canais=2.0))

    t = simular_gap(DF, P, G, SEM)
    print("\n  E) POR PECA E POR ANO (completa, sem custo)")
    for k, g in t.groupby("tipo"):
        x = m(g)
        print(f"    {k:<18}{x['n']:>6}  {x['r']:+.3f}R ({x['s']:+.1f}s)  acerto {(g['resultado'] > 0).mean():.0%}")
    for ano in range(2022, 2027):
        x = m(t[pd.to_datetime(t["tempo_entrada"]).dt.year == ano])
        print(f"    {ano}  {x['n']:>5}  {x['r']:+.3f}R ({x['s']:+.1f}s)")
    fatos()
    return 0


if __name__ == "__main__":
    sys.exit(main())
