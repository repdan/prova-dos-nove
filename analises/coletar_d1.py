"""
Coleta o universo de mercados em D1.

Em diario nao existe sessao - existe dia. Por isso este coletor e direto e nao
passa pelo pipeline intradiario: forcar o filtro de pregao aqui seria fazer o
codigo fingir que resolve um problema que nao existe.

Usa copy_rates_from_pos em vez de copy_rates_range: le o cache do terminal sem
disparar download profundo simbolo a simbolo, que levava minutos por ativo.

    .venv/Scripts/python.exe analises/coletar_d1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configuracao import Config                                    # noqa: E402
from data.mt5_conexao import conectar, desconectar                 # noqa: E402

UNIVERSO = [
    "XAUUSD", "XAGUSD", "XPTUSD", "UKOIL", "NGAS",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "EURGBP", "AUDJPY", "GBPJPY", "EURAUD", "CADJPY", "CHFJPY", "EURCHF",
    "GER40", "US100", "US30", "US500", "UK100", "FRA40", "JP225", "AUS200",
    "HK50", "ESP35", "BTCUSD", "ETHUSD",
]
MINIMO_CANDLES = 400


def main() -> int:
    cfg = Config.carregar()
    conectar(cfg)
    destino = Path(__file__).resolve().parent.parent / "data" / "historico" / "D1"
    destino.mkdir(parents=True, exist_ok=True)

    linhas = []
    for nome in UNIVERSO:
        if not mt5.symbol_select(nome, True):
            print(f"  {nome:<9} nao existe"); continue
        r = mt5.copy_rates_from_pos(nome, mt5.TIMEFRAME_D1, 0, 20_000)
        if r is None or len(r) < MINIMO_CANDLES:
            print(f"  {nome:<9} historico insuficiente "
                  f"({0 if r is None else len(r)} candles)"); continue

        i = mt5.symbol_info(nome)
        d = pd.DataFrame(r)
        d["tempo_ativo"] = pd.to_datetime(d["time"], unit="s", utc=True)
        d = d.rename(columns={"open": "abertura", "high": "maxima",
                              "low": "minima", "close": "fechamento",
                              "tick_volume": "volume_ticks", "spread": "spread_pontos"})
        d["tempo_utc"] = d["tempo_ativo"]
        d["tempo_servidor"] = d["tempo_ativo"]
        d["volume_real"] = 0
        d["sessao_id"] = 0

        antes = len(d)
        # Dia com volume zero nao e pregao - e barra de preenchimento.
        d = d[d["volume_ticks"] > 0].reset_index(drop=True)
        if len(d) < MINIMO_CANDLES:
            print(f"  {nome:<9} sobrou pouco apos limpar volume zero"); continue

        a, b, f = (d["maxima"].to_numpy(), d["minima"].to_numpy(),
                   d["fechamento"].to_numpy())
        tr = np.maximum(a - b, np.maximum(np.abs(a - np.roll(f, 1)),
                                          np.abs(b - np.roll(f, 1))))[1:]
        atr = float(np.median(tr))
        spread = float(np.median(d["spread_pontos"])) * i.point
        lucro1 = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, nome, 1.0,
                                       float(f[-1]), float(f[-1]) + 1.0)

        d.to_parquet(destino / f"{nome}_D1.parquet", index=False)
        anos = (d["tempo_ativo"].iloc[-1] - d["tempo_ativo"].iloc[0]).days / 365.25
        linhas.append({
            "nome": nome, "candles": len(d), "removidos": antes - len(d),
            "inicio": int(d["tempo_ativo"].iloc[0].year), "anos": anos,
            "atr": atr, "spread": spread,
            "giro_rel": 2 * spread / atr if atr else np.nan,
            "usd_por_ponto_lote": lucro1 or 0.0, "ponto": i.point,
            "vol_min": i.volume_min, "swap_compra": i.swap_long,
            "swap_venda": i.swap_short, "swap_mode": i.swap_mode,
        })
        print(f"  {nome:<9} ok  {len(d):>6} candles, {anos:.1f} anos")

    t = pd.DataFrame(linhas).sort_values("giro_rel")
    t.to_csv(destino / "universo.csv", index=False, encoding="utf-8")

    print(f"\n  {len(t)} mercados salvos\n")
    print(f"  {'simbolo':<9}{'candles':>9}{'desde':>7}{'anos':>7}{'ATR D1':>12}"
          f"{'spread':>10}{'giro/ATR':>11}{'USD/pt/lote':>13}")
    print("  " + "-" * 80)
    for l in t.itertuples():
        marca = "  <<<" if l.giro_rel < 0.05 else ""
        print(f"  {l.nome:<9}{l.candles:>9,}{l.inicio:>7}{l.anos:>7.1f}"
              f"{l.atr:>12.4f}{l.spread:>10.4f}{l.giro_rel:>10.1%}"
              f"{l.usd_por_ponto_lote:>13.2f}{marca}".replace(",", "."))
    print(f"\n  Giro mediano do universo: {t['giro_rel'].median():.1%} de um candle D1")
    print( "  Para comparar, em M15: HK50 22%, ouro 6%, EURUSD 25%")
    desconectar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
