"""
Trend following diario, medido em CARTEIRA.

    .venv/Scripts/python.exe rodar_carteira.py

A pergunta que este script responde nao e "a estrategia funciona no ouro?" -
essa ja sabemos que e a pergunta errada. E: a soma de dezenas de apostas
independentes, dimensionadas por risco, tem esperanca positiva depois de
custos?

E responde tambem a pergunta que importa para voce hoje: quanto disso e
executavel numa conta pequena, onde o lote minimo e uma restricao dura.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.carteira import BacktestCarteira, Especificacao
from strategy.tendencia_diaria import TendenciaDiaria

PASTA = Path(__file__).resolve().parent / "data" / "historico" / "D1"
LARGURA = 88


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


def carregar() -> tuple[dict[str, pd.DataFrame], dict[str, Especificacao]]:
    universo = pd.read_csv(PASTA / "universo.csv")
    dados, specs = {}, {}
    for l in universo.itertuples():
        caminho = PASTA / f"{l.nome}_D1.parquet"
        if not caminho.exists() or not l.usd_por_ponto_lote:
            continue
        dados[l.nome] = pd.read_parquet(caminho)
        # swap vem em "points" do MT5 quando swap_mode == 1; converte para
        # unidades de preco para ficar na mesma moeda do resto da conta.
        fator = l.ponto if l.swap_mode == 1 else 0.0
        specs[l.nome] = Especificacao(
            nome=l.nome, usd_por_ponto_lote=float(l.usd_por_ponto_lote),
            spread=float(l.spread), lote_minimo=float(l.vol_min),
            passo_lote=float(l.vol_min),
            swap_compra=float(l.swap_compra) * fator,
            swap_venda=float(l.swap_venda) * fator)
    return dados, specs


def metricas(res, capital: float) -> dict:
    q = res.quadro
    if q.empty:
        return {}
    p = res.patrimonio["patrimonio"]
    ret = p.pct_change().dropna()
    pico = p.cummax()
    anos = max((p.index[-1] - p.index[0]).days / 365.25, 0.01)
    ganhos = q[q["resultado_usd"] > 0]["resultado_usd"]
    perdas = q[q["resultado_usd"] <= 0]["resultado_usd"]
    return {
        "trades": len(q), "acerto": (q["resultado_usd"] > 0).mean(),
        "final": p.iloc[-1], "retorno": p.iloc[-1] / capital - 1,
        "cagr": (p.iloc[-1] / capital) ** (1 / anos) - 1,
        "dd": float(-((p - pico) / pico).min()),
        "sharpe": float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() else 0.0,
        "fator": float(ganhos.sum() / abs(perdas.sum())) if len(perdas) else float("inf"),
        "anos": anos, "por_ano": len(q) / anos,
        "abaixo_min": q["lote_abaixo_do_minimo"].mean(),
    }


def linha(rot: str, m: dict) -> None:
    if not m:
        print(f"  {rot:<26} (sem trades)"); return
    print(f"  {rot:<26}{m['trades']:>7}{m['acerto']:>8.0%}{m['retorno']:>10.1%}"
          f"{m['cagr']:>9.1%}{m['dd']:>9.1%}{m['fator']:>7.2f}{m['sharpe']:>8.2f}"
          f"{m['abaixo_min']:>10.0%}")


def cabecalho() -> None:
    print(f"  {'configuracao':<26}{'trades':>7}{'acerto':>8}{'retorno':>10}"
          f"{'CAGR':>9}{'drawdown':>9}{'fator':>7}{'sharpe':>8}{'lote min':>10}")
    print("  " + "-" * 86)


def main() -> int:
    if not (PASTA / "universo.csv").exists():
        print("  Rode antes: .venv/Scripts/python.exe analises/coletar_d1.py")
        return 1

    dados, specs = carregar()
    if not dados:
        print("  Nenhum mercado carregado."); return 1

    inicio = min(df["tempo_ativo"].min() for df in dados.values())
    fim = max(df["tempo_ativo"].max() for df in dados.values())
    titulo(f"TREND FOLLOWING DIARIO — {len(dados)} MERCADOS")
    print(f"  Periodo: {inicio:%Y-%m-%d} a {fim:%Y-%m-%d}")
    print(f"  Mercados: {', '.join(sorted(dados))}")

    # ---------------------------------------------------- conta de referencia
    titulo("A) CONTA DE 10.000 USD, RISCO DE 1% POR TRADE")
    cabecalho()
    guardado = {}
    for rot, kw in [
        ("entrada 55 / saida 20", dict(periodo_entrada=55, periodo_saida=20)),
        ("entrada 20 / saida 10", dict(periodo_entrada=20, periodo_saida=10)),
        ("entrada 100 / saida 50", dict(periodo_entrada=100, periodo_saida=50)),
        ("55/20 + filtro de 200d", dict(periodo_entrada=55, periodo_saida=20,
                                        so_a_favor_da_tendencia_longa=200)),
    ]:
        bt = BacktestCarteira(lambda k=kw: TendenciaDiaria(**k), specs,
                              capital_inicial=10_000, risco_por_trade=0.01)
        res = bt.rodar(dados)
        m = metricas(res, 10_000)
        guardado[rot] = (res, m)
        linha(rot, m)

    # ------------------------------------------------------ risco por trade
    titulo("B) QUANTO ARRISCAR POR TRADE (entrada 55 / saida 20)")
    cabecalho()
    for risco in (0.005, 0.01, 0.02, 0.03):
        bt = BacktestCarteira(lambda: TendenciaDiaria(55, 20), specs,
                              capital_inicial=10_000, risco_por_trade=risco)
        m = metricas(bt.rodar(dados), 10_000)
        linha(f"risco de {risco:.1%}", m)

    # --------------------------------------------- a conta que voce tem hoje
    titulo("C) CONTA PEQUENA (USD 400)")
    cabecalho()
    for rot, aceitar in [("aceita lote minimo", True),
                         ("pula se nao couber", False)]:
        bt = BacktestCarteira(lambda: TendenciaDiaria(55, 20), specs,
                              capital_inicial=400, risco_por_trade=0.01,
                              aceitar_lote_minimo=aceitar)
        res = bt.rodar(dados)
        m = metricas(res, 400)
        linha(rot, m)
        if m:
            print(f"  {'':<26}sinais recusados por lote: "
                  f"{res.sinais_recusados_por_lote} de {res.sinais_gerados}")

    # -------------------------------------------------------- por mercado
    res, _ = guardado["entrada 55 / saida 20"]
    q = res.quadro
    if not q.empty:
        titulo("D) DE ONDE VEM O RESULTADO (55/20, conta de 10.000)")
        g = q.groupby("mercado").agg(
            trades=("resultado_usd", "size"), total=("resultado_usd", "sum"),
            acerto=("resultado_usd", lambda s: (s > 0).mean()),
            dias=("dias", "median")).sort_values("total", ascending=False)
        print(f"  {'mercado':<10}{'trades':>8}{'total USD':>12}{'acerto':>9}"
              f"{'dias medianos':>15}")
        print("  " + "-" * 55)
        for i, l in g.iterrows():
            print(f"  {i:<10}{l['trades']:>8.0f}{l['total']:>12.0f}"
                  f"{l['acerto']:>9.0%}{l['dias']:>15.0f}")
        pos = (g["total"] > 0).sum()
        print(f"\n  {pos} de {len(g)} mercados positivos.")
        print("  Numa estrategia de carteira isso e o esperado - o resultado vem")
        print("  da soma, nao de acertar cada um.")

        destino = Path(__file__).resolve().parent / "reports"
        destino.mkdir(exist_ok=True)
        q.to_csv(destino / "trades_carteira.csv", index=False, encoding="utf-8")
        res.patrimonio.to_csv(destino / "patrimonio_carteira.csv", encoding="utf-8")
        print(f"\n  Trades e curva salvos em reports/\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
