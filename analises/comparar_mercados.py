"""
A mesma estrategia, os mesmos custos, quatro mercados.

Se o rompimento de canal tem edge real, ele aparece em mais de um. Se so
aparece onde foi calibrado, era ajuste.

    .venv/Scripts/python.exe analises/comparar_mercados.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import metricas as met          # noqa: E402
from backtest.motor import montar_do_config   # noqa: E402
from configuracao import Config               # noqa: E402

MERCADOS = ["XAUUSD", "EURUSD", "GER40", "HK50"]
PERIODOS = [10, 20, 30, 40, 60, 100]


def rodar(cfg, caminho, periodo):
    motor, feed = montar_do_config(cfg, caminho_pregao=caminho,
                                   modo_saida="stop_gain", periodo_canal=periodo)
    q = motor.rodar(feed).quadro
    return (met.calcular(q), len(feed.quadro)) if not q.empty else (None, 0)


def main() -> int:
    resumo = []
    for mercado in MERCADOS:
        cfg = Config.carregar(mercado=mercado)
        pasta = cfg.caminho_absoluto("coleta.pasta_saida")
        simbolo = cfg.exigir("mt5.simbolo")

        for tf in ("H1", "M15"):
            caminho = pasta / f"{simbolo}_{tf}_pregao.parquet"
            if not caminho.exists():
                continue
            print(f"\n  {'='*74}\n  {mercado} — {tf}\n  {'='*74}")
            print(f"  {'periodo':>8}{'candles':>9}{'trades':>8}{'acerto':>8}"
                  f"{'BRUTO':>10}{'custo':>9}{'liquido':>10}{'fator':>7}{'sharpe':>8}")
            print("  " + "-" * 74)
            melhor = None
            for p_ in PERIODOS:
                m, n = rodar(cfg, caminho, p_)
                if m is None or m.trades < 50:
                    continue
                marca = ("  <<<" if m.resultado_bruto_pontos > 0 and m.fator_lucro > 1.0
                         else ("  bruto+" if m.resultado_bruto_pontos > 0 else ""))
                print(f"  {p_:>8}{n if p_==PERIODOS[0] else '':>9}{m.trades:>8}"
                      f"{m.taxa_acerto:>8.0%}{m.resultado_bruto_pontos:>10.1f}"
                      f"{-m.custo_total_pontos:>9.1f}{m.resultado_total_pontos:>10.1f}"
                      f"{m.fator_lucro:>7.2f}{m.sharpe_anualizado:>8.2f}{marca}")
                if melhor is None or m.fator_lucro > melhor[1].fator_lucro:
                    melhor = (p_, m)
            if melhor:
                p_, m = melhor
                resumo.append({
                    "mercado": mercado, "tf": tf, "periodo": p_, "trades": m.trades,
                    "bruto_pos": m.resultado_bruto_pontos > 0,
                    "fator": m.fator_lucro, "sharpe": m.sharpe_anualizado,
                    # Quantos periodos, dos 6, deram bruto positivo. E o teste
                    # de consistencia: um edge real nao depende de acertar o
                    # parametro, aparece numa faixa.
                })

    print(f"\n\n  {'='*74}\n  RESUMO — melhor periodo de cada combinacao\n  {'='*74}")
    print(f"  {'mercado':<10}{'tf':<6}{'periodo':>8}{'trades':>8}"
          f"{'bruto+':>9}{'fator':>8}{'sharpe':>9}")
    print("  " + "-" * 60)
    for r in sorted(resumo, key=lambda x: -x["fator"]):
        print(f"  {r['mercado']:<10}{r['tf']:<6}{r['periodo']:>8}{r['trades']:>8}"
              f"{('sim' if r['bruto_pos'] else 'nao'):>9}{r['fator']:>8.2f}"
              f"{r['sharpe']:>9.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
