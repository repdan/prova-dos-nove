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
    """Metricas em MULTIPLOS DE RISCO (R), nao em dolares.

    Por que R e nao dolar: dimensionando por % do capital, o tamanho da posicao
    varia centenas de vezes ao longo de um teste longo. Somar dolares faz os
    trades do fim valerem 1.000x os do inicio, e o "fator de lucro" resultante
    descreve o efeito do juro composto, nao a qualidade da estrategia.

    1 R = o que se perde se o stop for atingido. Um trade de +2R ganhou o dobro
    do que arriscou, tenha sido em 1995 ou em 2025.
    """
    q = res.quadro
    if q.empty:
        return {}
    # R de cada trade. risco_planejado e o que se perderia no stop.
    r = q["resultado_usd"] / q["risco_planejado"].replace(0, np.nan)
    r = r.dropna()
    if r.empty:
        return {}

    ganhos, perdas = r[r > 0], r[r <= 0]
    p = res.patrimonio["patrimonio"]
    pico = p.cummax()
    anos = max((p.index[-1] - p.index[0]).days / 365.25, 0.01)

    return {
        "trades": len(r), "acerto": float((r > 0).mean()),
        "r_total": float(r.sum()), "r_medio": float(r.mean()),
        "r_por_ano": float(r.sum() / anos),
        "fator": (float(ganhos.sum() / abs(perdas.sum()))
                  if len(perdas) and perdas.sum() else float("inf")),
        "maior_ganho": float(r.max()), "maior_perda": float(r.min()),
        # Erro padrao da media em R: diz se o resultado se distingue de zero.
        "erro": float(r.std() / np.sqrt(len(r))),
        "dd": float(-((p - pico) / pico).min()),
        "anos": anos,
        "abaixo_min": float(q["lote_abaixo_do_minimo"].mean()),
    }


def linha(rot: str, m: dict) -> None:
    if not m:
        print(f"  {rot:<26} (sem trades)"); return
    # Um resultado so se distingue de zero se a media for maior que ~2 erros.
    sigmas = abs(m["r_medio"]) / m["erro"] if m["erro"] else 0
    selo = "significativo" if sigmas > 2 else ("fraco" if sigmas > 1 else "ruido")
    print(f"  {rot:<26}{m['trades']:>7}{m['acerto']:>8.0%}{m['r_total']:>9.1f}"
          f"{m['r_medio']:>9.3f}{m['erro']:>9.3f}{sigmas:>8.1f}"
          f"{m['fator']:>7.2f}{m['abaixo_min']:>9.0%}  {selo}")


def cabecalho() -> None:
    print(f"  {'configuracao':<26}{'trades':>7}{'acerto':>8}{'R total':>9}"
          f"{'R medio':>9}{'erro':>9}{'sigmas':>8}{'fator':>7}{'lote min':>9}")
    print("  " + "-" * 94)


def main() -> int:
    if not (PASTA / "universo.csv").exists():
        print("  Rode antes: .venv/Scripts/python.exe analises/coletar_d1.py")
        return 1

    dados, specs = carregar()
    if not dados:
        print("  Nenhum mercado carregado."); return 1

    # Antes de 1995 so existem 3 mercados na base. Chamar isso de "carteira
    # diversificada" seria medir outra coisa - o beneficio da estrategia vem
    # justamente de somar muitas apostas independentes.
    CORTE = pd.Timestamp("1995-01-01", tz="UTC")
    dados = {m: df[df["tempo_ativo"] >= CORTE].reset_index(drop=True)
             for m, df in dados.items()}
    dados = {m: df for m, df in dados.items() if len(df) > 500}

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
