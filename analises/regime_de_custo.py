"""
O custo de operar o HK50 mudou ao longo do periodo estudado?

Motivo da pergunta: o backtest cobra o spread REAL de cada candle. Se o spread
do ativo mudou de patamar no meio da base, medir os 4,5 anos como um bloco so
mistura dois mundos diferentes e produz um numero que nao descreve nenhum dos
dois.

    .venv/Scripts/python.exe analises/regime_de_custo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest import metricas as met  # noqa: E402
from backtest.motor import montar_do_config  # noqa: E402
from configuracao import Config  # noqa: E402


def main() -> int:
    cfg = Config.carregar()
    motor, feed = montar_do_config(cfg, modo_saida="stop_gain")
    t = motor.rodar(feed).quadro
    p = feed.quadro.copy()

    p["ano"] = p["tempo_ativo"].dt.year
    sp = p.groupby("ano")["spread_pontos"].agg(["median", "mean"]) / 100
    t["ano"] = pd.to_datetime(t["tempo_entrada"]).dt.year

    print("\n  O spread do HK50 e o desempenho da estrategia, ano a ano\n")
    print(f"  {'ano':<7}{'spread mediano':>16}{'spread medio':>14}{'trades':>8}"
          f"{'liquido':>10}{'bruto':>9}{'custo/trade':>13}{'fator':>8}")
    print("  " + "-" * 84)
    for ano in sorted(sp.index):
        g = t[t["ano"] == ano]
        if g.empty:
            continue
        m = met.calcular(g)
        fator = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
        marca = "  <<<" if m.fator_lucro > 1.1 else ""
        print(f"  {ano:<7}{sp.loc[ano, 'median']:>16.2f}{sp.loc[ano, 'mean']:>14.2f}"
              f"{m.trades:>8}{m.resultado_total_pontos:>10.0f}"
              f"{m.resultado_bruto_pontos:>9.0f}"
              f"{m.custo_total_pontos / max(m.trades, 1):>13.1f}{fator:>8}{marca}")

    print("\n  ATENCAO ao interpretar: escolher o periodo recente PORQUE ele")
    print("  parece melhor e a mesma armadilha da otimizacao de parametro. O")
    print("  numero so vira conclusao depois de walk-forward dentro do regime")
    print("  novo, e depois de confirmar com a corretora que a mudanca de")
    print("  spread e do mercado e nao da conta.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
