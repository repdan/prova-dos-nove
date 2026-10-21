"""
Coleta M1 de qualquer simbolo organizado em "dias" da corretora.

    .venv/Scripts/python.exe analises/coletar_m1_dias.py US500 US100 US30

Mercados quase 24 h: o dia e o bloco entre pausas de mais de 45 minutos
(mesma montagem do ouro e dos indices fora da amostra). Salva em
data/historico/<SIMBOLO>/<SIMBOLO>_M1_dias.parquet e um meta.json.
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

RAIZ = Path(__file__).resolve().parent.parent / "data" / "historico"


def main() -> int:
    simbolos = sys.argv[1:] or ["US500", "US100", "US30"]
    conectar(Config.carregar(mercado="HK50"))
    for s in simbolos:
        mt5.symbol_select(s, True)
        info = mt5.symbol_info(s)
        bruto = coleta.coletar_candles(s, "M1", "2016-01-01")
        dias = montar_dias(bruto, pausa_h=0.75, quantil_tipico=0.9)
        destino = RAIZ / s
        destino.mkdir(parents=True, exist_ok=True)
        dias.to_parquet(destino / f"{s}_M1_dias.parquet", index=False)
        preco = float(dias["fechamento"].iloc[-1])
        meta = {"ponto": info.point, "spread_atual": info.spread * info.point,
                "spread_mediano_hist": float(dias["spread_pontos"].median() * info.point),
                "usd_por_ponto_lote": mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, s, 1.0, preco, preco + 1.0)}
        (destino / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        por_ano = dias.groupby(dias["tempo_ativo"].dt.year)["sessao_id"].nunique().to_dict()
        print(f"  {s}: {len(bruto):,} velas, {dias['sessao_id'].nunique()} dias, "
              f"velas/dia {dias.groupby('sessao_id').size().median():.0f}, {meta}")
        print(f"    dias por ano: {por_ano}")
    desconectar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
