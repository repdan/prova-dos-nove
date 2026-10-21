"""
Coleta XAUUSD em M1 e M15 organizado em "dias" da corretora, para a grade.

    .venv/Scripts/python.exe analises/coletar_ouro_grade.py

O ouro negocia ~23 h por dia com uma pausa de 1 h (22h-23h UTC). O "dia" e o
bloco entre duas pausas de mais de 45 minutos - mesma montagem usada para os
indices fora da amostra (analises/coletar_m1_indices.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analises.coletar_m1_indices import montar_dias                # noqa: E402
from configuracao import Config                                    # noqa: E402
from data import coleta                                            # noqa: E402
from data.mt5_conexao import conectar, desconectar                 # noqa: E402

DESTINO = Path(__file__).resolve().parent.parent / "data" / "historico" / "XAUUSD"


def main() -> int:
    conectar(Config.carregar(mercado="XAUUSD"))
    mt5.symbol_select("XAUUSD", True)
    info = mt5.symbol_info("XAUUSD")
    for tf in ("M15", "M1"):
        bruto = coleta.coletar_candles("XAUUSD", tf, "2017-01-01")
        dias = montar_dias(bruto, pausa_h=0.75, quantil_tipico=0.9)
        dias.to_parquet(DESTINO / f"XAUUSD_{tf}_dias.parquet", index=False)
        por_ano = dias.groupby(dias["tempo_ativo"].dt.year)["sessao_id"].nunique()
        print(f"  {tf}: {len(bruto):,} velas, {dias['sessao_id'].nunique()} dias, "
              f"velas/dia {dias.groupby('sessao_id').size().median():.0f}")
        print("    dias por ano:", por_ano.to_dict())
    preco = info.ask
    meta = {"ponto": info.point, "spread_atual": info.spread * info.point,
            "usd_por_ponto_lote": mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, "XAUUSD", 1.0, preco, preco + 1.0)}
    (DESTINO / "meta_grade.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("  meta:", meta)
    desconectar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
