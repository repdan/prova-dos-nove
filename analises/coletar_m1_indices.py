"""
Coleta M1 de indices com pregao (gap de abertura) para testes FORA DA AMOSTRA
de hipoteses nascidas no HK50: FR40, ES35, CN50.

    .venv/Scripts/python.exe analises/coletar_m1_indices.py

Nao passa pelo pipeline de pregao do HK50 (horarios de HK): o "dia" aqui e o
bloco de negociacao entre duas pausas longas (> 3 h), no horario do servidor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configuracao import Config                                    # noqa: E402
from data import coleta                                            # noqa: E402
from data.mt5_conexao import conectar, desconectar                 # noqa: E402

SIMBOLOS = ["FR40", "ES35", "CN50"]
PAUSA_H = 3.0
DESTINO = Path(__file__).resolve().parent.parent / "data" / "historico" / "OOS"


def montar_dias(bruto: pd.DataFrame, pausa_h: float = PAUSA_H,
                quantil_tipico: float = 0.5) -> pd.DataFrame:
    """quantil_tipico: o tamanho de dia "normal". Mediana serve quando o
    historico e denso; com anos esparsos (ouro 2017-18, milhares de blocos de
    1 vela) a mediana desaba e e preciso um quantil alto."""
    d = bruto.sort_values("tempo_servidor").reset_index(drop=True)
    pausa = d["tempo_servidor"].diff().dt.total_seconds() / 3600
    d["sessao_id"] = (pausa.fillna(99) > pausa_h).cumsum()
    # O "dia" e a data em que o bloco comeca.
    inicio = d.groupby("sessao_id")["tempo_servidor"].transform("min")
    d["dia_bloco"] = inicio.dt.date
    tam = d.groupby("sessao_id")["fechamento"].transform("size")
    # Blocos curtos (feriado, dado esparso) saem: menos de 60% do tamanho tipico.
    tipico = d.groupby("sessao_id").size().quantile(quantil_tipico)
    d = d[tam >= 0.6 * tipico].copy()
    # tempo_ativo: relogio continuo onde cada bloco cai num unico dia de calendario
    # (os simuladores agrupam por data). Desloca o bloco para comecar 00:00 do dia.
    desloc = d["tempo_servidor"] - pd.to_datetime(d["dia_bloco"])
    d["tempo_ativo"] = pd.to_datetime(d["dia_bloco"]) + (desloc - desloc.groupby(d["sessao_id"]).transform("min"))
    return d.reset_index(drop=True)


def main() -> int:
    conectar(Config.carregar(mercado="HK50"))
    DESTINO.mkdir(parents=True, exist_ok=True)
    meta = {}
    for s in SIMBOLOS:
        mt5.symbol_select(s, True)
        info = mt5.symbol_info(s)
        bruto = coleta.coletar_candles(s, "M1", "2016-01-01")
        dias = montar_dias(bruto)
        preco = float(dias["fechamento"].iloc[-1])
        usd = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, s, 1.0, preco, preco + 1.0) or 0.0
        meta[s] = {"ponto": info.point, "usd_por_ponto_lote": usd, "spread_atual": info.spread * info.point,
                   "spread_mediano_hist": float(dias["spread_pontos"].median() * info.point)}
        dias.to_parquet(DESTINO / f"{s}_M1_dias.parquet", index=False)
        por_ano = dias.groupby(dias["tempo_ativo"].dt.year)["sessao_id"].nunique()
        print(f"  {s}: {len(bruto):,} velas, {dias['sessao_id'].nunique()} pregoes, "
              f"velas/pregao {dias.groupby('sessao_id').size().median():.0f}, meta {meta[s]}")
        print("    pregoes por ano:", por_ano.to_dict())
    (DESTINO / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    desconectar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
