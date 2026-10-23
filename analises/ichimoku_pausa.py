"""
Pausa depois de um trade grande no Ichimoku classico M15 - segue analises/ichimoku_pausa_protocolo.md.

    .venv/Scripts/python.exe -m analises.ichimoku_pausa

1) Premissa: R medio do 1o, 2o e 3o trade depois de um trade de >= 3 R / >= 5 R.
2) Regra no motor: depois de um trade >= X R, ignora os proximos N sinais.
   Descoberta 2022-2024 (ouro, USDJPY) -> confirmacao 2025-2026 e pares novos.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analises.ichimoku_filtros import NOVOS, P, carregar, resumo   # noqa: E402
from strategy.ichimoku import simular_ichimoku                       # noqa: E402

VARIANTES = [(x, n) for x in (3.0, 5.0) for n in (1, 2, 3)]
DESCOBERTA = ["ouro", "USDJPY"]
TODOS = DESCOBERTA + list(NOVOS)
INICIO = {"ouro": 2022, "USDJPY": 2022, **NOVOS}


def rodar(spec):
    mk, var = spec
    d, custo, ponto, _ = carregar(mk)
    p = P if var is None else replace(P, pausa_apos_r=var[0], pausa_sinais=var[1])
    return spec, simular_ichimoku(d, p, custo, ponto)


def no_periodo(t: pd.DataFrame, anos) -> pd.DataFrame:
    ano = pd.to_datetime(t["tempo_entrada"]).dt.year
    return t[(ano >= anos[0]) & (ano <= anos[1])].reset_index(drop=True)


def premissa(t: pd.DataFrame, rot: str) -> None:
    r = t["r"].to_numpy()
    print(f"    {rot:<26} todos: {len(r):>5} trades, {r.mean():+.3f} R/trade")
    for x in (3.0, 5.0):
        grandes = np.flatnonzero(r[:-1] >= x)
        partes = []
        for k in (1, 2, 3):
            idx = grandes + k
            v = r[idx[idx < len(r)]]
            ep = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan
            partes.append(f"{k}o: {v.mean():+.3f} (+-{2 * ep:.2f}, n={len(v)})")
        print(f"    {'':<26} depois de >= {x:.0f} R   " + "   ".join(partes))


def main() -> int:
    specs = [(mk, v) for mk in TODOS for v in [None] + VARIANTES]
    with ProcessPoolExecutor(max_workers=min(4, os.cpu_count())) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))

    print("\n  1) PREMISSA: R medio dos trades seguintes a um trade grande (sem regra, com custo)")
    print("     entre parenteses: +-2 erros-padrao; se o intervalo inclui a media de todos, nao ha diferenca")
    for mk in DESCOBERTA:
        premissa(no_periodo(res[(mk, None)], (2022, 2024)), f"{mk} 2022-2024")
    for mk in DESCOBERTA:
        premissa(no_periodo(res[(mk, None)], (2025, 2026)), f"{mk} 2025-2026")
    for mk in NOVOS:
        premissa(no_periodo(res[(mk, None)], (INICIO[mk], 2026)), f"{mk} {INICIO[mk]}-2026")

    print("\n  2) REGRA - DESCOBERTA 2022-2024, com custo")
    print(f"    {'variante':<26}{'mercado':<9}{'trades':>7}{'R/trade':>9}{'R/ano':>8}{'>=5R':>6}")
    aprovadas = []
    for v in [None] + VARIANTES:
        ok = True
        for mk in DESCOBERTA:
            b, x = resumo(res[(mk, None)], (2022, 2024)), resumo(res[(mk, v)], (2022, 2024))
            rot = "sem pausa" if v is None else f"apos >= {v[0]:.0f} R, pula {v[1]}"
            print(f"    {rot:<26}{mk:<9}{x['n']:>7}{x['r']:>+9.3f}{x['ano']:>+8.1f}{x['grandes']:>6}")
            if v is not None and not (x["ano"] > b["ano"] and x["r"] > b["r"]):
                ok = False
        if v is not None and ok:
            aprovadas.append(v)
    print(f"\n    Aprovadas pelo protocolo: {aprovadas or 'nenhuma'}")

    # A confirmacao so vale para as aprovadas; o resto aparece apenas como informacao.
    print("\n  3) CONFIRMACAO (2025-26 em ouro/USDJPY; pares novos desde o inicio) - R/ano com custo")
    print(f"    {'variante':<26}" + "".join(f"{mk:>9}" for mk in TODOS) + "   veredito")
    linha = lambda v, anos_de: [resumo(res[(mk, v)], anos_de(mk))["ano"] for mk in TODOS]   # noqa: E731
    anos_conf = lambda mk: (2025, 2026) if mk in DESCOBERTA else (INICIO[mk], 2026)        # noqa: E731
    base = linha(None, anos_conf)
    print(f"    {'sem pausa':<26}" + "".join(f"{y:>+9.1f}" for y in base))
    for v in VARIANTES:
        y = linha(v, anos_conf)
        melhor = [a > b for a, b in zip(y, base)]
        conf = all(melhor[:2]) and sum(melhor[2:]) >= 3
        ver = ("CONFIRMADA" if conf else "nao confirmada") if v in aprovadas else "(nao aprovada)"
        print(f"    {f'apos >= {v[0]:.0f} R, pula {v[1]}':<26}" + "".join(f"{a:>+9.1f}" for a in y)
              + f"   {ver} ({sum(melhor[:2])}/2, {sum(melhor[2:])}/4)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
