"""
O filtro de volume sobrevive ao walk-forward?

O achado bruto: manter so os trades em que o volume estava BAIXO em relacao ao
proprio historico recente leva o fator de lucro de 0,98 para 1,17. Mas o corte
foi escolhido olhando o resultado - o mesmo erro que fez o periodo 160 parecer
otimo e render -7.755 pontos no teste honesto.

Aqui o limiar e recalculado a cada janela usando SO o passado, e aplicado no
mes seguinte, que o processo nunca viu.

Testa duas leituras de volume:
  anterior - volume do candle ANTES do rompimento
  proprio  - volume do proprio candle que rompeu (tambem conhecido na decisao,
             ja que a entrada acontece no fechamento dele)

    .venv/Scripts/python.exe analises/walk_forward_filtro.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest import metricas as met  # noqa: E402
from backtest.motor import montar_do_config  # noqa: E402
from configuracao import Config  # noqa: E402

LARGURA = 88
MESES_TREINO = 12
CORTES = [0.3, 0.5, 0.7]


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


def preparar(cfg: Config) -> pd.DataFrame:
    motor, feed = montar_do_config(cfg, modo_saida="stop_gain")
    t = motor.rodar(feed).quadro
    p = feed.quadro.sort_values("tempo_ativo").reset_index(drop=True).copy()

    base = p["volume_ticks"].rolling(100).mean().shift(1)
    p["vol_proprio"] = p["volume_ticks"] / base       # volume do candle do rompimento
    p["vol_anterior"] = p["vol_proprio"].shift(1)     # volume do candle antes dele

    t["tempo_entrada"] = pd.to_datetime(t["tempo_entrada"])
    t = t.join(p.set_index("tempo_ativo")[["vol_proprio", "vol_anterior"]],
               on="tempo_entrada")
    return t.dropna(subset=["vol_proprio", "vol_anterior"]).sort_values("tempo_entrada")


def walk_forward(t: pd.DataFrame, coluna: str, corte: float) -> dict:
    """Limiar recalculado a cada mes com dados de ate 12 meses antes."""
    t = t.copy()
    # tz_localize(None) antes de to_period: o periodo mensal nao carrega fuso,
    # e converter direto emite aviso a cada chamada.
    t["mes"] = t["tempo_entrada"].dt.tz_localize(None).dt.to_period("M")
    meses = sorted(t["mes"].unique())

    linhas, mantidos, descartados = [], [], []
    for i in range(MESES_TREINO, len(meses)):
        janela = meses[i - MESES_TREINO:i]
        treino = t[t["mes"].isin(janela)]
        teste = t[t["mes"] == meses[i]]
        if len(treino) < 100 or teste.empty:
            continue

        # O limiar sai SO do passado.
        limiar = treino[coluna].quantile(corte)
        fica = teste[teste[coluna] <= limiar]
        sai = teste[teste[coluna] > limiar]

        mantidos.append(fica)
        descartados.append(sai)
        linhas.append({
            "mes": str(meses[i]), "limiar": limiar,
            "trades_mes": len(teste), "mantidos": len(fica),
            "pontos_filtrado": fica["resultado_pontos"].sum(),
            "pontos_todos": teste["resultado_pontos"].sum(),
        })

    return {
        "por_mes": pd.DataFrame(linhas),
        "mantidos": pd.concat(mantidos) if mantidos else pd.DataFrame(),
        "descartados": pd.concat(descartados) if descartados else pd.DataFrame(),
    }


def main() -> int:
    cfg = Config.carregar()
    t = preparar(cfg)

    titulo("O FILTRO DE VOLUME SOBREVIVE AO WALK-FORWARD?")
    print(f"  Base: {len(t)} trades. Limiar recalculado a cada mes com os")
    print(f"  {MESES_TREINO} meses anteriores, aplicado no mes seguinte.\n")

    print(f"  {'leitura de volume':<20}{'corte':>8}{'trades':>9}{'mantidos':>10}"
          f"{'pontos':>10}{'media':>9}{'acerto':>9}{'fator':>8}{'meses+':>9}")
    print("  " + "-" * 84)

    melhor = None
    for coluna, rot in [("vol_anterior", "candle anterior"),
                        ("vol_proprio", "candle do rompimento")]:
        for corte in CORTES:
            r = walk_forward(t, coluna, corte)
            fica = r["mantidos"]
            if fica.empty:
                continue
            m = met.calcular(fica)
            pm = r["por_mes"]
            meses_pos = (pm["pontos_filtrado"] > 0).mean()
            f = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
            marca = "  <<<" if m.fator_lucro > 1.10 else ""
            print(f"  {rot:<20}{corte:>8.0%}{m.trades:>9}"
                  f"{len(fica)/max(len(fica)+len(r['descartados']),1):>10.0%}"
                  f"{m.resultado_total_pontos:>10.0f}{m.expectativa_por_trade:>9.1f}"
                  f"{m.taxa_acerto:>9.0%}{f:>8}{meses_pos:>9.0%}{marca}")
            if melhor is None or m.resultado_total_pontos > melhor[1]:
                melhor = ((coluna, corte), m.resultado_total_pontos, r)

    # ---- comparacao contra nao filtrar, no MESMO periodo de teste ----
    (coluna, corte), _, r = melhor
    fica, sai = r["mantidos"], r["descartados"]
    todos = pd.concat([fica, sai])

    titulo(f"MELHOR CONFIGURACAO: {coluna}, mantendo os {corte:.0%} menores")
    print(f"  {'':<24}{'trades':>9}{'pontos':>10}{'media':>9}{'acerto':>9}{'fator':>8}")
    print("  " + "-" * 69)
    for rot, g in [("Sem filtro (mesmo periodo)", todos),
                   ("MANTIDOS pelo filtro", fica),
                   ("DESCARTADOS pelo filtro", sai)]:
        if g.empty:
            continue
        m = met.calcular(g)
        f = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
        print(f"  {rot:<24}{m.trades:>9}{m.resultado_total_pontos:>10.0f}"
              f"{m.expectativa_por_trade:>9.1f}{m.taxa_acerto:>9.0%}{f:>8}")

    print("\n  Se os DESCARTADOS forem claramente piores que os mantidos, o filtro")
    print("  esta separando de verdade - e nao apenas encolhendo a amostra.")

    pm = r["por_mes"]
    print(f"\n  Meses de teste: {len(pm)} | com filtro melhor que sem: "
          f"{(pm['pontos_filtrado'] > pm['pontos_todos']).mean():.0%}")
    print(f"  Limiar escolhido pelo treino: mediana {pm['limiar'].median():.2f}, "
          f"variacao {pm['limiar'].min():.2f} a {pm['limiar'].max():.2f}")

    titulo("MES A MES (ultimos 18)")
    print(f"  {'mes':<10}{'limiar':>9}{'trades':>9}{'mantidos':>10}"
          f"{'com filtro':>12}{'sem filtro':>12}{'ganho':>10}")
    print("  " + "-" * 72)
    for l in pm.tail(18).itertuples():
        ganho = l.pontos_filtrado - l.pontos_todos
        print(f"  {l.mes:<10}{l.limiar:>9.2f}{l.trades_mes:>9}{l.mantidos:>10}"
              f"{l.pontos_filtrado:>12.0f}{l.pontos_todos:>12.0f}{ganho:>10.0f}")

    acumulado = pm["pontos_filtrado"].sum() - pm["pontos_todos"].sum()
    print(f"\n  Ganho acumulado do filtro sobre nao filtrar: {acumulado:+.0f} pontos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
