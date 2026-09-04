"""
As tres politicas de inversao, comparadas.

  regra  - deixa a regra de dentro-para-fora decidir (inverte em 69% das saidas)
  sempre - inverte em toda saida, mesmo quando o preco nao passou pelo canal
  nunca  - nunca inverte no mesmo candle; espera voltar para dentro e romper

Cada uma roda sob varios cenarios de custo, porque o spread do HK50 mudou de
patamar durante a base e o resultado muda de sinal conforme o custo assumido.
Uma tabela so, com um custo so, esconderia isso.

    .venv/Scripts/python.exe analises/comparar_inversao.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest import metricas as met  # noqa: E402
from backtest.contexto_diario import direcionalidade_por_dia  # noqa: E402
from backtest.motor import montar_do_config  # noqa: E402
from configuracao import Config  # noqa: E402

LARGURA = 92
POLITICAS = ["regra", "sempre", "nunca"]
CENARIOS = [
    ("spread historico real", None),
    ("spread 4.5 (medido hoje)", 4.5),
    ("spread 6.5 (media dos regimes)", 6.5),
]


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


def rodar(cfg: Config, politica: str, spread, **kw):
    cfg.definir("custos.spread_forcado", spread)
    motor, feed = montar_do_config(cfg, modo_saida="stop_gain", **kw)
    motor.politica_inversao = politica
    resultado = motor.rodar(feed)
    return resultado, resultado.quadro


def cabecalho() -> None:
    print(f"  {'politica':<10}{'trades':>8}{'acerto':>8}{'fator':>7}{'liquido':>10}"
          f"{'exp/trade':>11}{'ganho med':>11}{'perda med':>11}{'drawdown':>10}{'sharpe':>8}")
    print("  " + "-" * 86)


def linha(politica: str, m: met.Metricas) -> None:
    fator = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
    marca = "  <<<" if m.fator_lucro > 1.05 else ""
    print(f"  {politica:<10}{m.trades:>8}{m.taxa_acerto:>8.0%}{fator:>7}"
          f"{m.resultado_total_pontos:>10.0f}{m.expectativa_por_trade:>11.1f}"
          f"{m.ganho_medio:>11.1f}{m.perda_media:>11.1f}"
          f"{m.drawdown_maximo_pontos:>10.0f}{m.sharpe_anualizado:>8.2f}{marca}")


def main() -> int:
    cfg = Config.carregar()

    titulo("COMPARATIVO DAS TRES POLITICAS DE INVERSAO")
    guardados = {}
    for rot_cen, spread in CENARIOS:
        print(f"\n  [{rot_cen}]")
        cabecalho()
        for pol in POLITICAS:
            resultado, q = rodar(cfg, pol, spread)
            m = met.calcular(q)
            linha(pol, m)
            if spread is None:
                guardados[pol] = (resultado, q)

    # ------------------------------------------------- o que cada uma muda
    titulo("O QUE MUDA NA PRATICA")
    for pol in POLITICAS:
        r, q = guardados[pol]
        extra = ""
        if pol == "sempre":
            extra = f" | inversoes forcadas: {r.inversoes_forcadas}"
        if pol == "nunca":
            extra = f" | inversoes bloqueadas: {r.inversoes_bloqueadas}"
        print(f"  {pol:<8} {len(q):>5} trades | "
              f"duracao mediana {q['candles_no_trade'].median():>4.0f} candles | "
              f"noites {q['noites_carregadas'].mean():>4.2f}/trade{extra}")

    # ------------------------------------------------------ por regime
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    dir_dia = direcionalidade_por_dia(pd.read_parquet(pasta / "HK50_M15_pregao.parquet"))

    titulo("DESEMPENHO POR REGIME DO DIA")
    print(f"  {'politica':<10}{'regime':<22}{'trades':>8}{'total':>10}"
          f"{'media':>9}{'acerto':>9}")
    print("  " + "-" * 68)
    for pol in POLITICAS:
        _, q = guardados[pol]
        t = q.copy()
        t["dia"] = pd.to_datetime(t["tempo_entrada"]).dt.date
        t = t.join(dir_dia, on="dia").dropna(subset=["posterior_direcionalidade"])
        t["regime"] = pd.cut(t["posterior_direcionalidade"], [0, .25, .50, .75, 1.01],
                             labels=["lateral (0-25%)", "25-50%", "50-75%",
                                     "tendencia (75-100%)"])
        g = t.groupby("regime", observed=True).agg(
            n=("resultado_pontos", "size"), total=("resultado_pontos", "sum"),
            media=("resultado_pontos", "mean"),
            acerto=("resultado_pontos", lambda s: (s > 0).mean()))
        for i, l in g.iterrows():
            print(f"  {pol:<10}{str(i):<22}{l['n']:>8.0f}{l['total']:>10.0f}"
                  f"{l['media']:>9.1f}{l['acerto']:>8.0%}")
        print()

    # ------------------------------------------------------- ano a ano
    titulo("ANO A ANO (spread historico real)")
    print(f"  {'ano':<7}" + "".join(f"{p:>22}" for p in POLITICAS))
    print("  " + "-" * 73)
    anos = sorted({pd.to_datetime(d).year
                   for _, q in guardados.values()
                   for d in q["tempo_entrada"]})
    for ano in anos:
        celulas = []
        for pol in POLITICAS:
            _, q = guardados[pol]
            g = q[pd.to_datetime(q["tempo_entrada"]).dt.year == ano]
            if g.empty:
                celulas.append(f"{'-':>22}")
                continue
            m = met.calcular(g)
            fator = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
            celulas.append(f"{m.resultado_total_pontos:>13.0f} (f {fator})")
        print(f"  {ano:<7}" + "".join(celulas))

    destino = Path(__file__).resolve().parent.parent / "reports"
    for pol in POLITICAS:
        guardados[pol][1].to_csv(destino / f"trades_inversao_{pol}.csv",
                                 index=False, encoding="utf-8")
    print(f"\n  Trades de cada politica salvos em reports/trades_inversao_*.csv\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
