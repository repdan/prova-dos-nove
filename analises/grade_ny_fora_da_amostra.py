"""
Grade na abertura de Nova York - confirmacao FORA DA AMOSTRA.

    .venv/Scripts/python.exe -m analises.grade_ny_fora_da_amostra

No ouro, a abertura de NY foi o unico caso em que o metodo ficou acima do
espelho em todos os tempos graficos (M5 a H1), com o melhor liquido em M30 /
canal na 1a vela (+0.018R). Regra fixada ANTES de olhar os indices americanos,
sem ajuste: gestao do autor, tendencia neutra, canal na abertura de NY
(16:30 do servidor), custo pelo spread real de cada vela.

Sucesso = metodo consistentemente acima do espelho e liquido > 0, sobretudo
em M30 / 1a vela.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analises.grade_tempo_grafico import CANAIS, AUTOR, fr, m, reamostrar  # noqa: E402
from strategy.grade import Custos, simular                                  # noqa: E402

TFS = {"M5": 5, "M15": 15, "M30": 30, "H1": 60}
MERCADOS = ["US500", "US100", "US30", "XAUUSD"]
P = replace(AUTOR, tendencia="neutra")
_CACHE: dict = {}


def custo(mercado: str) -> Custos:
    if mercado == "XAUUSD":
        return Custos(0.02, 0.001, 0.21)
    meta = json.loads((RAIZ / "data" / "historico" / mercado / "meta.json").read_text())
    return Custos(slippage=0.1 * meta["spread_mediano_hist"],
                  comissao_pontos=0.1 / meta["usd_por_ponto_lote"])


def carregar(mercado: str, tf: str) -> pd.DataFrame:
    if (mercado, tf) not in _CACHE:
        d = pd.read_parquet(RAIZ / "data" / "historico" / mercado / f"{mercado}_M1_dias.parquet")
        # Mesmo periodo para todos (os indices so tem M1 denso a partir de 2022).
        d = d[d["tempo_ativo"].dt.year >= 2022]
        ts = d["tempo_servidor"]
        d = d[(ts.dt.hour > 16) | ((ts.dt.hour == 16) & (ts.dt.minute >= 30))]
        _CACHE[(mercado, tf)] = reamostrar(d.sort_values("tempo_ativo").reset_index(drop=True), TFS[tf])
    return _CACHE[(mercado, tf)]


def rodar(spec):
    mercado, tf, canal, com_custo, inverter = spec
    p = replace(P, **CANAIS[canal], controle_inverter=inverter)
    return spec, simular(carregar(mercado, tf), p, custo(mercado) if com_custo else Custos(0, 0, 0.0))


def main() -> int:
    specs = [(mk, tf, cn, c, inv) for mk in MERCADOS for tf in TFS for cn in CANAIS
             for c, inv in ((False, False), (False, True), (True, False))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))
    for mk in MERCADOS:
        rot = mk + ("  (onde o padrao foi achado, mesmo periodo 2022-2026)" if mk == "XAUUSD" else "  (fora da amostra)")
        print(f"\n  {rot}")
        print(f"  {'tempo grafico / canal':<22}{'trades':>7}{'sem custo':>16}{'ESPELHO':>16}{'com custo':>16}{'custo':>8}")
        print("  " + "-" * 85)
        for tf in TFS:
            for cn in CANAIS:
                sem, esp = m(res[(mk, tf, cn, False, False)]), m(res[(mk, tf, cn, False, True)])
                com = m(res[(mk, tf, cn, True, False)])
                print(f"  {tf + ' / ' + cn:<22}{sem['n']:>7}{fr(sem):>16}{fr(esp):>16}{fr(com):>16}{com['cr']:>7.2f}R")
    return 0


if __name__ == "__main__":
    sys.exit(main())
