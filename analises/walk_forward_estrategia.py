"""
Walk-forward da estrategia COMPLETA, com o filtro de volume dentro do motor.

Diferenca crucial em relacao a analise anterior: la o filtro era aplicado sobre
a lista de trades ja produzida. Aqui ele vive dentro da estrategia, e por isso
muda o encadeamento - recusar um sinal deixa a vaga de posicao livre, e sinais
que antes eram descartados por ocupacao passam a executar.

Sao populacoes de trade diferentes, e so esta versao descreve o que aconteceria
de verdade. O ganho medido aqui e menor que o da analise externa, e este e o
numero honesto.

    .venv/Scripts/python.exe analises/walk_forward_estrategia.py
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

LARGURA = 86
LIMIARES = [0.50, 0.60, 0.70, 0.80, 0.88, 1.00, 1.20]
MESES_TREINO = 12


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


def rodar(cfg: Config, limiar: float | None, inicio=None, fim=None):
    cfg.definir("estrategia.filtro_volume_ativo", limiar is not None)
    if limiar is not None:
        cfg.definir("estrategia.filtro_volume_limiar", limiar)
    motor, feed = montar_do_config(cfg, modo_saida="stop_gain",
                                   inicio=inicio, fim=fim)
    return motor.rodar(feed).quadro


def varredura(cfg: Config) -> None:
    titulo("LIMIAR DO FILTRO, MEDIDO SOBRE TODA A BASE")
    print("  (in-sample: serve para ver o formato da curva, nao para escolher)\n")
    print(f"  {'limiar':<10}{'trades':>9}{'pontos':>10}{'media':>9}"
          f"{'acerto':>9}{'fator':>8}{'sharpe':>9}")
    print("  " + "-" * 64)

    q = rodar(cfg, None)
    m = met.calcular(q)
    print(f"  {'sem filtro':<10}{m.trades:>9}{m.resultado_total_pontos:>10.0f}"
          f"{m.expectativa_por_trade:>9.1f}{m.taxa_acerto:>9.0%}"
          f"{m.fator_lucro:>8.2f}{m.sharpe_anualizado:>9.2f}")

    for limiar in LIMIARES:
        q = rodar(cfg, limiar)
        if q.empty:
            continue
        m = met.calcular(q)
        marca = "  <<<" if m.fator_lucro > 1.08 else ""
        print(f"  {limiar:<10.2f}{m.trades:>9}{m.resultado_total_pontos:>10.0f}"
              f"{m.expectativa_por_trade:>9.1f}{m.taxa_acerto:>9.0%}"
              f"{m.fator_lucro:>8.2f}{m.sharpe_anualizado:>9.2f}{marca}")

    print("\n  Curva suave e larga = efeito real. Serrote = ruido sendo ajustado.")


def walk_forward(cfg: Config) -> None:
    """Escolhe o limiar com 12 meses de passado e aplica no mes seguinte."""
    titulo("WALK-FORWARD: LIMIAR ESCOLHIDO SO COM O PASSADO")

    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    tempos = pd.read_parquet(pasta / "HK50_M15_pregao.parquet")["tempo_ativo"]
    marcos = pd.date_range(tempos.min().normalize(), tempos.max().normalize(),
                           freq="MS", tz=tempos.dt.tz)

    # Roda cada limiar uma vez sobre a base inteira e recorta depois: rodar o
    # motor uma vez por limiar por mes seria 300 execucoes desnecessarias.
    por_limiar = {}
    for limiar in LIMIARES:
        q = rodar(cfg, limiar)
        q["tempo_entrada"] = pd.to_datetime(q["tempo_entrada"])
        por_limiar[limiar] = q.sort_values("tempo_entrada")
    sem = rodar(cfg, None)
    sem["tempo_entrada"] = pd.to_datetime(sem["tempo_entrada"])

    linhas = []
    for i in range(MESES_TREINO, len(marcos) - 1):
        ini_tr, fim_tr, fim_te = marcos[i - MESES_TREINO], marcos[i], marcos[i + 1]

        melhor, melhor_pts = None, -np.inf
        for limiar, q in por_limiar.items():
            treino = q[(q["tempo_entrada"] >= ini_tr) & (q["tempo_entrada"] < fim_tr)]
            if len(treino) < 30:
                continue
            pts = treino["resultado_pontos"].sum()
            if pts > melhor_pts:
                melhor, melhor_pts = limiar, pts
        if melhor is None:
            continue

        q = por_limiar[melhor]
        teste = q[(q["tempo_entrada"] >= fim_tr) & (q["tempo_entrada"] < fim_te)]
        base = sem[(sem["tempo_entrada"] >= fim_tr) & (sem["tempo_entrada"] < fim_te)]
        linhas.append({
            "mes": f"{fim_tr:%Y-%m}", "limiar": melhor,
            "trades": len(teste),
            "com_filtro": teste["resultado_pontos"].sum(),
            "sem_filtro": base["resultado_pontos"].sum(),
        })

    pm = pd.DataFrame(linhas)
    com, sem_f = pm["com_filtro"].sum(), pm["sem_filtro"].sum()

    print(f"  Meses testados ..................... {len(pm)}")
    print(f"  Total COM filtro adaptativo ........ {com:>9.0f} pontos")
    print(f"  Total SEM filtro ................... {sem_f:>9.0f} pontos")
    print(f"  Diferenca .......................... {com - sem_f:>+9.0f} pontos")
    print(f"  Meses em que o filtro foi melhor ... {(pm['com_filtro'] > pm['sem_filtro']).mean():.0%}")

    contagem = pm["limiar"].value_counts().sort_index()
    print(f"\n  Limiar escolhido pelo treino:")
    for lim, n in contagem.items():
        print(f"    {lim:.2f}: {'#' * n} ({n})")
    print(f"  Limiares distintos: {len(contagem)} de {len(LIMIARES)}")

    # E o limiar FIXO, sem escolher nada? Costuma ser mais robusto que
    # reescolher todo mes, justamente por nao perseguir o ultimo resultado.
    print(f"\n  Comparacao com limiar FIXO no mesmo periodo de teste:")
    inicio_teste = pd.Timestamp(pm['mes'].iloc[0] + "-01", tz=tempos.dt.tz)
    print(f"    {'limiar':<12}{'trades':>9}{'pontos':>10}{'media':>9}{'fator':>8}")
    for limiar in LIMIARES:
        q = por_limiar[limiar]
        g = q[q["tempo_entrada"] >= inicio_teste]
        if g.empty:
            continue
        m = met.calcular(g)
        marca = "  <<<" if m.fator_lucro > 1.08 else ""
        print(f"    {limiar:<12.2f}{m.trades:>9}{m.resultado_total_pontos:>10.0f}"
              f"{m.expectativa_por_trade:>9.1f}{m.fator_lucro:>8.2f}{marca}")
    g = sem[sem["tempo_entrada"] >= inicio_teste]
    m = met.calcular(g)
    print(f"    {'sem filtro':<12}{m.trades:>9}{m.resultado_total_pontos:>10.0f}"
          f"{m.expectativa_por_trade:>9.1f}{m.fator_lucro:>8.2f}")


def main() -> int:
    cfg = Config.carregar()
    varredura(cfg)
    walk_forward(cfg)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
