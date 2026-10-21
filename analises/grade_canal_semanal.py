"""
Grade no ouro: canal montado na abertura da SEMANA e carregado ate sexta
(regra de gestao semanal), contra o canal diario.

    .venv/Scripts/python.exe -m analises.grade_canal_semanal

Canal semanal: primeiras velas da semana; a grade e o estado (NR, ZR,
tendencia) valem ate sexta. Gestao semanal: 1 gain ou 2 stops encerram a
semana. Posicao fechada no fim de cada dia, ou carregada dentro da semana.
Aberturas: corretora (segunda 01:00 do servidor) e Nova York (16:30).
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analises.grade_tempo_grafico import CANAIS, AUTOR, carregar, fr, m  # noqa: E402
from strategy.grade import Custos, simular                                # noqa: E402

CUSTO = Custos(0.02, 0.001, 0.21, swap_compra=-0.66, swap_venda=0.34, dia_triplo=2)
BASE = replace(AUTOR, tendencia="neutra", **CANAIS["1a vela"])
ABERTURAS = {"corretora": "ouro corretora", "NY": "ouro NY"}
TFS = ("M15", "M30", "H1")
VERSOES = {
    "canal DIARIO, gestao semanal dom-qua": ("dia", dict(gestao_semanal=True, dias_semana=(0, 1, 2))),
    "canal SEMANAL, fecha cada dia, seg-sex": ("semana", dict(fechar_fim_de_cada_sessao=True)),
    "canal SEMANAL, fecha cada dia, dom-qua": ("semana", dict(fechar_fim_de_cada_sessao=True,
                                                               dias_semana=(0, 1, 2))),
    "canal SEMANAL, carrega na semana": ("semana", dict()),
}


def rodar(spec):
    ab, tf, v, com_custo, inv = spec
    periodo, kw = VERSOES[v]
    p = replace(BASE, **kw, controle_inverter=inv)
    return spec, simular(carregar(ABERTURAS[ab], tf), p, CUSTO if com_custo else Custos(0, 0, 0.0),
                         periodo=periodo)


def main() -> int:
    specs = [(ab, tf, v, c, inv) for ab in ABERTURAS for tf in TFS for v in VERSOES
             for c, inv in ((False, False), (False, True), (True, False), (True, True))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))
    for ab in ABERTURAS:
        for tf in TFS:
            print(f"\n  OURO, abertura {ab}, {tf}")
            print(f"  {'versao':<42}{'trades':>7}{'acerto':>8}{'sem custo':>16}{'ESPELHO':>16}"
                  f"{'com custo':>16}{'ESP c/custo':>16}{'R/ano':>8}")
            print("  " + "-" * 129)
            for v in VERSOES:
                sem, esp = m(res[(ab, tf, v, False, False)]), m(res[(ab, tf, v, False, True)])
                tc = res[(ab, tf, v, True, False)]
                com, espc = m(tc), m(res[(ab, tf, v, True, True)])
                anos = (pd.to_datetime(tc["tempo_saida"]).max() - pd.to_datetime(tc["tempo_entrada"]).min()).days / 365.25
                print(f"  {v:<42}{sem['n']:>7}{(tc['resultado'] > 0).mean():>8.0%}{fr(sem):>16}{fr(esp):>16}"
                      f"{fr(com):>16}{fr(espc):>16}{tc['r'].sum() / anos:>+8.1f}")
    print("\n  Por ano, com custo (metodo | espelho), canal SEMANAL fechando cada dia, seg-sex:")
    for ab in ABERTURAS:
        for tf in TFS:
            v = "canal SEMANAL, fecha cada dia, seg-sex"
            t, e = res[(ab, tf, v, True, False)], res[(ab, tf, v, True, True)]
            ya, ye = pd.to_datetime(t["tempo_entrada"]).dt.year, pd.to_datetime(e["tempo_entrada"]).dt.year
            print(f"    {ab:<10}{tf:<5}" + "  ".join(f"{a}:{m(g)['r']:+.2f}|{m(e[ye == a])['r']:+.2f}"
                                               for a, g in t.groupby(ya)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
