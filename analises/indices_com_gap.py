"""
Quais indices da corretora tem PREGAO (pausa diaria longa e, portanto, gap de
abertura), como o HK50? Candidatos para testar fora da amostra uma hipotese
nascida no HK50.

    .venv/Scripts/python.exe analises/indices_com_gap.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configuracao import Config                                    # noqa: E402
from data.mt5_conexao import conectar, desconectar                 # noqa: E402


def main() -> int:
    conectar(Config.carregar(mercado="HK50"))
    simbolos = [s for s in mt5.symbols_get()
                if "ind" in s.path.lower() or "cash" in s.path.lower()]
    print(f"  {len(simbolos)} simbolos de indice\n")
    print(f"  {'simbolo':<12}{'caminho':<34}{'pausa diaria (h)':>17}{'gap mediano':>13}{'spread':>8}{'M1 desde':>12}")
    for s in simbolos:
        mt5.symbol_select(s.name, True)
        r = mt5.copy_rates_from_pos(s.name, mt5.TIMEFRAME_M1, 0, 30_000)
        if r is None or len(r) < 1000:
            continue
        d = pd.DataFrame(r)
        t = pd.to_datetime(d["time"], unit="s")
        buraco = t.diff().dt.total_seconds() / 3600
        # pausa diaria tipica: maior buraco de cada dia util, mediana
        por_dia = buraco.groupby(t.dt.date).max()
        pausa = por_dia[por_dia < 40].median()
        gaps = (d["open"] - d["close"].shift()).abs()[buraco > 0.5]
        antigo = mt5.copy_rates_from_pos(s.name, mt5.TIMEFRAME_M1, 0, 2_000_000)
        desde = pd.to_datetime(antigo["time"][0], unit="s").date() if antigo is not None else "?"
        print(f"  {s.name:<12}{s.path[:33]:<34}{pausa:>17.1f}{gaps.median():>13.1f}"
              f"{s.spread * s.point:>8.2f}{str(desde):>12}")
    desconectar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
