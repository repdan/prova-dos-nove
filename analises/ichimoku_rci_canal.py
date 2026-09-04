"""
Tres perguntas de uma vez:

  1. O filtro de volume esta mesmo fugindo da lateralidade, ou esta cortando
     trade ruim por outro motivo?
  2. RCI e Ichimoku acrescentam alguma coisa?
  3. O canal do primeiro candle (maxima e minima, com pavio) serve de segunda
     condicao para o rompimento?

Todos medidos do mesmo jeito que a varredura anterior: no candle do sinal, com
janelas que terminam no candle anterior, e avaliados por AUC, quintis e efeito
sobre o resultado.

    .venv/Scripts/python.exe analises/ichimoku_rci_canal.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest import metricas as met  # noqa: E402
from backtest.contexto_diario import direcionalidade_por_dia  # noqa: E402
from backtest.motor import montar_do_config  # noqa: E402
from configuracao import Config  # noqa: E402

LARGURA = 88
CORTE_LATERAL = 0.25


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


# ================================================== 1. o filtro foge do lateral?

def filtro_x_lateralidade(t: pd.DataFrame, dir_dia: pd.DataFrame) -> None:
    titulo("1. O FILTRO DE VOLUME ESTA FUGINDO DA LATERALIDADE?")

    t = t.copy()
    t["dia"] = pd.to_datetime(t["tempo_entrada"]).dt.date
    t = t.join(dir_dia, on="dia").dropna(subset=["posterior_direcionalidade"])
    t["regime"] = pd.cut(t["posterior_direcionalidade"], [0, .25, .50, .75, 1.01],
                         labels=["lateral", "fraco", "medio", "tendencia"])

    # Filtro simples e fixo, so para a leitura: mantem a metade de menor volume.
    limiar = t["vol_anterior"].median()
    t["mantido"] = t["vol_anterior"] <= limiar

    print(f"  Corte: volume relativo do candle anterior <= {limiar:.2f}\n")
    print(f"  {'regime do dia':<14}{'trades':>8}{'mantidos':>10}{'% mantido':>12}"
          f"{'media mantidos':>17}{'media descartados':>19}")
    print("  " + "-" * 80)

    for reg in ["lateral", "fraco", "medio", "tendencia"]:
        g = t[t["regime"] == reg]
        if g.empty:
            continue
        m, d = g[g["mantido"]], g[~g["mantido"]]
        print(f"  {reg:<14}{len(g):>8}{len(m):>10}{len(m)/len(g):>11.0%}"
              f"{m['resultado_pontos'].mean():>17.1f}"
              f"{d['resultado_pontos'].mean() if len(d) else 0:>19.1f}")

    taxa_lateral = (t[t["mantido"]]["regime"] == "lateral").mean()
    taxa_original = (t["regime"] == "lateral").mean()
    print(f"\n  Proporcao de trades em dia lateral:")
    print(f"    antes do filtro ... {taxa_original:.1%}")
    print(f"    depois do filtro .. {taxa_lateral:.1%}")

    if abs(taxa_lateral - taxa_original) < 0.02:
        print("\n  >>> O filtro NAO evita dia lateral - ele mantem a mesma proporcao.")
        print("      Ele melhora o resultado DENTRO de cada regime, o que e outra")
        print("      coisa: nao esta escolhendo o dia, esta escolhendo o trade.")
    else:
        print(f"\n  >>> O filtro desloca a composicao em "
              f"{taxa_lateral - taxa_original:+.1%} de dias laterais.")


# ============================================== 2. e 3. novos indicadores

def novas_features(p: pd.DataFrame) -> pd.DataFrame:
    d = p.sort_values("tempo_ativo").reset_index(drop=True).copy()
    fech = d["fechamento"]

    # ---------- RCI (Rank Correlation Index) ----------
    # Correlacao de postos entre preco e tempo. +100 = preco subiu em ordem
    # perfeita; -100 = caiu em ordem perfeita; perto de 0 = sem ordem = lateral.
    # E a formulacao classica japonesa da "forca de tendencia".
    def rci(janela: int) -> pd.Series:
        def calcular(v):
            n = len(v)
            postos_preco = pd.Series(v).rank().to_numpy()
            postos_tempo = np.arange(n, 0, -1)          # o mais recente = posto 1
            d2 = ((postos_tempo - postos_preco) ** 2).sum()
            return (1 - 6 * d2 / (n ** 3 - n)) * 100
        return fech.rolling(janela).apply(calcular, raw=True).shift(1)

    for n in (9, 26, 52):
        d[f"rci_{n}"] = rci(n)
    d["rci_9_abs"] = d["rci_9"].abs()      # forca, sem direcao
    d["rci_26_abs"] = d["rci_26"].abs()

    # ---------- Ichimoku ----------
    # Periodos classicos 9/26/52. O que interessa aqui nao e o sinal de compra
    # do indicador, e o que ele diz sobre REGIME: nuvem grossa = tendencia
    # estabelecida; preco dentro da nuvem = indefinicao.
    def meio(n):
        return (d["maxima"].rolling(n).max() + d["minima"].rolling(n).min()) / 2

    tenkan = meio(9)
    kijun = meio(26)
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = meio(52).shift(26)

    nuvem_topo = pd.concat([span_a, span_b], axis=1).max(axis=1)
    nuvem_base = pd.concat([span_a, span_b], axis=1).min(axis=1)
    espessura = (nuvem_topo - nuvem_base).abs()

    atr = (d["maxima"] - d["minima"]).rolling(14).mean()
    d["nuvem_espessura"] = (espessura / atr).shift(1)
    d["preco_na_nuvem"] = (((fech <= nuvem_topo) & (fech >= nuvem_base))
                           .astype(float).shift(1))
    d["dist_nuvem"] = ((fech - (nuvem_topo + nuvem_base) / 2).abs() / atr).shift(1)
    d["tenkan_kijun"] = ((tenkan - kijun).abs() / atr).shift(1)

    # ---------- canal do primeiro candle do dia ----------
    # Maxima e minima do primeiro candle, carregadas o dia inteiro.
    d["dia"] = d["tempo_ativo"].dt.date
    g = d.groupby("dia")
    d["c1_topo"] = g["maxima"].transform("first")
    d["c1_base"] = g["minima"].transform("first")
    d["c1_altura"] = d["c1_topo"] - d["c1_base"]
    # Onde o preco esta em relacao a esse canal: >1 acima, <0 abaixo.
    d["c1_posicao"] = (fech - d["c1_base"]) / d["c1_altura"].replace(0, np.nan)
    d["c1_rompido"] = ((d["c1_posicao"] > 1) | (d["c1_posicao"] < 0)).astype(float)
    d["c1_distancia"] = (d["c1_posicao"] - 0.5).abs()
    return d


NOVAS = {
    "RCI (forca de tendencia)": ["rci_9_abs", "rci_26_abs"],
    "Ichimoku (regime)": ["nuvem_espessura", "preco_na_nuvem", "dist_nuvem",
                          "tenkan_kijun"],
    "Canal do primeiro candle": ["c1_posicao", "c1_distancia", "c1_altura"],
}


def avaliar(t: pd.DataFrame) -> None:
    from sklearn.metrics import roc_auc_score

    titulo("2. e 3. RCI, ICHIMOKU E O CANAL DO PRIMEIRO CANDLE")
    print(f"  Referencia: volume relativo tem AUC 0,425 (distancia 0,075 de 0,50)\n")

    for familia, colunas in NOVAS.items():
        print(f"  {familia}")
        print(f"    {'indicador':<22}{'AUC':>8}{'distancia':>11}"
              f"{'q1 media':>11}{'q5 media':>11}{'q1 acerto':>11}{'q5 acerto':>11}")
        print("    " + "-" * 83)
        for col in colunas:
            x = t[[col, "resultado_pontos"]].dropna()
            if len(x) < 200 or x[col].nunique() < 3:
                print(f"    {col:<22}{'(sem variacao suficiente)':>60}")
                continue
            y = (x["resultado_pontos"] > 0).to_numpy()
            auc = roc_auc_score(y, x[col])
            q = pd.qcut(x[col].rank(method="first"), 5, labels=False)
            g = x.groupby(q)["resultado_pontos"]
            marca = "  <<<" if abs(auc - .5) > .05 else ""
            print(f"    {col:<22}{auc:>8.3f}{abs(auc-.5):>11.3f}"
                  f"{g.mean().iloc[0]:>11.1f}{g.mean().iloc[-1]:>11.1f}"
                  f"{(g.get_group(0) > 0).mean():>10.0%}"
                  f"{(g.get_group(4) > 0).mean():>11.0%}{marca}")
        print()


def condicao_dupla(t: pd.DataFrame) -> None:
    """A ideia do operador: exigir rompimento do canal de medias E do canal do
    primeiro candle ao mesmo tempo."""
    titulo("3b. EXIGIR OS DOIS ROMPIMENTOS AO MESMO TEMPO")

    x = t.dropna(subset=["c1_posicao"]).copy()
    # O sinal ja rompeu o canal de medias. A pergunta e se o preco tambem
    # estava fora do canal do primeiro candle, e do mesmo lado.
    comprado = x["direcao"] == "comprado"
    x["confirma"] = np.where(comprado, x["c1_posicao"] > 1, x["c1_posicao"] < 0)

    print(f"  {'grupo':<40}{'trades':>9}{'total':>10}{'media':>9}{'acerto':>9}{'fator':>8}")
    print("  " + "-" * 85)
    for rot, g in [("TODOS (sem a condicao extra)", x),
                   ("Confirmados pelo 1o candle", x[x["confirma"]]),
                   ("NAO confirmados", x[~x["confirma"]])]:
        if g.empty:
            continue
        m = met.calcular(g)
        f = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
        marca = "  <<<" if m.fator_lucro > 1.10 else ""
        print(f"  {rot:<40}{m.trades:>9}{m.resultado_total_pontos:>10.0f}"
              f"{m.expectativa_por_trade:>9.1f}{m.taxa_acerto:>9.0%}{f:>8}{marca}")

    # E somando ao filtro de volume?
    limiar = x["vol_anterior"].median()
    print()
    for rot, g in [("Volume baixo, sozinho", x[x["vol_anterior"] <= limiar]),
                   ("Volume baixo + confirmado pelo 1o candle",
                    x[(x["vol_anterior"] <= limiar) & x["confirma"]])]:
        if g.empty:
            continue
        m = met.calcular(g)
        f = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
        marca = "  <<<" if m.fator_lucro > 1.10 else ""
        print(f"  {rot:<40}{m.trades:>9}{m.resultado_total_pontos:>10.0f}"
              f"{m.expectativa_por_trade:>9.1f}{m.taxa_acerto:>9.0%}{f:>8}{marca}")


def main() -> int:
    cfg = Config.carregar()
    motor, feed = montar_do_config(cfg, modo_saida="stop_gain")
    trades = motor.rodar(feed).quadro
    p = feed.quadro

    f = novas_features(p)
    base_vol = p["volume_ticks"].rolling(100).mean().shift(1)
    f["vol_anterior"] = (p.sort_values("tempo_ativo")["volume_ticks"].values
                         / base_vol.values)
    f["vol_anterior"] = f["vol_anterior"].shift(1)

    colunas = [c for cols in NOVAS.values() for c in cols] + ["vol_anterior"]
    t = trades.copy()
    t["tempo_entrada"] = pd.to_datetime(t["tempo_entrada"])
    t = t.join(f.set_index("tempo_ativo")[colunas], on="tempo_entrada")

    dir_dia = direcionalidade_por_dia(p)
    filtro_x_lateralidade(t, dir_dia)
    avaliar(t)
    condicao_dupla(t)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
