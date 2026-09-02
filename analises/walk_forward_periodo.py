"""
O periodo do canal sobrevive ao walk-forward?

Otimizar sobre a base inteira e escolher o numero que melhor se ajustou ao
passado. O teste honesto e outro: escolher o parametro usando SO o passado, e
medir no mes seguinte, que o processo nunca viu. Depois deslizar a janela e
repetir.

Se o melhor periodo mudar a cada janela, nao existe "melhor periodo" - existe
ruido, e o numero bonito da otimizacao global e uma miragem.

    .venv/Scripts/python.exe analises/walk_forward_periodo.py
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

PERIODOS = [10, 15, 20, 30, 40, 60, 80, 120, 160]
MESES_TREINO = 12
LARGURA = 84


def rodar(cfg: Config, periodo: int, inicio, fim) -> pd.DataFrame:
    motor, feed = montar_do_config(cfg, modo_saida="stop_gain",
                                   periodo_canal=periodo,
                                   inicio=str(inicio), fim=str(fim))
    return motor.rodar(feed).quadro


def main() -> int:
    cfg = Config.carregar()
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    dias = pd.read_parquet(pasta / "HK50_M15_pregao.parquet")["tempo_ativo"]
    primeiro, ultimo = dias.min().normalize(), dias.max().normalize()

    # Janelas mensais deslizantes: treina em MESES_TREINO, testa no mes seguinte.
    marcos = pd.date_range(primeiro, ultimo, freq="MS", tz=dias.dt.tz)
    print("=" * LARGURA)
    print("  WALK-FORWARD DO PERIODO DO CANAL")
    print("=" * LARGURA)
    print(f"  Treino de {MESES_TREINO} meses, teste no mes seguinte, janela desliza 1 mes.")
    print(f"  Base de {primeiro:%Y-%m} a {ultimo:%Y-%m}\n")
    print(f"  {'mes de teste':<14}{'periodo escolhido':>19}{'trades':>8}"
          f"{'pontos no teste':>17}{'acumulado':>12}")
    print("  " + "-" * 68)

    escolhidos, resultados = [], []
    acumulado = 0.0
    for i in range(MESES_TREINO, len(marcos) - 1):
        ini_tr, fim_tr = marcos[i - MESES_TREINO], marcos[i]
        fim_te = marcos[i + 1]

        # --- escolhe o periodo usando SO o passado ---
        melhor, melhor_pontos = None, -np.inf
        for p in PERIODOS:
            q = rodar(cfg, p, ini_tr, fim_tr)
            pontos = q["resultado_pontos"].sum() if not q.empty else -np.inf
            if pontos > melhor_pontos:
                melhor, melhor_pontos = p, pontos

        # --- aplica no mes seguinte, nunca visto ---
        q = rodar(cfg, melhor, fim_tr, fim_te)
        pontos = float(q["resultado_pontos"].sum()) if not q.empty else 0.0
        acumulado += pontos
        escolhidos.append(melhor)
        resultados.append(pontos)

        print(f"  {fim_tr:%Y-%m}{'':<8}{melhor:>19}{len(q):>8}"
              f"{pontos:>17.0f}{acumulado:>12.0f}")

    r = np.array(resultados)
    print("\n" + "=" * LARGURA)
    print("  RESULTADO DO PROCESSO DE OTIMIZACAO")
    print("=" * LARGURA)
    print(f"  Meses testados ................... {len(r)}")
    print(f"  Meses positivos .................. {(r > 0).sum()} ({(r > 0).mean():.0%})")
    print(f"  Total acumulado .................. {r.sum():.0f} pontos")
    print(f"  Media por mes .................... {r.mean():.0f} pontos")
    print(f"  Melhor mes / pior mes ............ {r.max():.0f} / {r.min():.0f}")

    contagem = pd.Series(escolhidos).value_counts().sort_index()
    print(f"\n  Periodo escolhido pelo treino, quantas vezes cada um:")
    for p, n in contagem.items():
        print(f"    periodo {p:>4}: {'#' * n} ({n})")
    print(f"\n  Periodos distintos escolhidos: {len(contagem)} de {len(PERIODOS)}")
    if len(contagem) > 3:
        print("  >>> O parametro nao estabiliza. Isso e ruido sendo otimizado,")
        print("      nao um periodo otimo sendo descoberto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
