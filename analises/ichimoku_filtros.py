"""
Filtros de entrada para o Ichimoku classico M15 - segue analises/ichimoku_filtros_protocolo.md.

    .venv/Scripts/python.exe -m analises.ichimoku_filtros

Descoberta 2022-2024 (ouro, USDJPY) -> aprovacao automatica pelos criterios do
protocolo -> combinacoes de ate dois aprovados -> confirmacao so dos aprovados
em 2025-2026 (ouro, USDJPY) e nos pares novos.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analises import ichimoku_referencia as ic                           # noqa: E402
from analises.grade_tempo_grafico import reamostrar                # noqa: E402
from strategy.grade import Custos                                  # noqa: E402
from strategy.ichimoku import ParametrosIchimoku, nuvem, simular_ichimoku  # noqa: E402

P = ParametrosIchimoku()
FILTROS = ["F1 tendencia H1", "F2 tenkan x kijun", "F3 chikou", "F4 horario 10-20",
           "F5 volatilidade", "F6 cor da nuvem"]
# Relogio do servidor - relogio da estrategia (ouro: tempo_ativo = servidor - 1 h).
OFFSET_H = {"ouro": 1.0, "USDJPY": 0.0, "EURUSD": 0.0, "GBPUSD": 0.0, "AUDUSD": 0.0, "USDCAD": 0.0}
NOVOS = {"EURUSD": 2024, "GBPUSD": 2022, "AUDUSD": 2022, "USDCAD": 2022}   # EURUSD: M1 real so de 2024
_CACHE: dict = {}


# --------------------------------------------------------------------- dados
def carregar(mk: str):
    if mk in _CACHE:
        return _CACHE[mk]
    if mk in ("ouro", "USDJPY"):
        cfg = ic.MERCADOS[mk]
        d, custo, ponto = ic.carregar(mk, "M15"), cfg["custo"], cfg["ponto"]
    else:
        arq = RAIZ / "data" / "historico" / mk / f"{mk}_M1_bruto.parquet"
        if not arq.exists():
            import MetaTrader5 as mt5  # noqa: F401
            from configuracao import Config
            from data import coleta
            from data.mt5_conexao import conectar
            conectar(Config.carregar(mercado="XAUUSD"))
            coleta.coletar_candles(mk, "M1", f"{NOVOS[mk] - 1}-11-01").to_parquet(arq, index=False)
        m1 = pd.read_parquet(arq)
        m1 = m1[m1["tempo_servidor"] >= f"{NOVOS[mk] - 1}-11-01"].sort_values("tempo_servidor")
        m1["tempo_ativo"] = m1["tempo_servidor"]
        m1["sessao_id"] = m1["tempo_servidor"].dt.normalize().factorize()[0]
        d = reamostrar(m1.reset_index(drop=True), 15)
        d["dia"] = d["tempo_ativo"].dt.date
        meta = json.loads((RAIZ / "data" / "historico" / mk / "meta.json").read_text())
        custo = Custos(0.1 * meta["spread_mediano_hist"], 0.1 / meta["usd_por_ponto_lote"])
        ponto = meta["ponto"]
    d = d.reset_index(drop=True)
    _CACHE[mk] = (d, custo, ponto, filtros(d, mk))
    return _CACHE[mk]


def filtros(d: pd.DataFrame, mk: str) -> dict:
    """{nome: (permitir_compra, permitir_venda)}, so com dados ate cada vela."""
    h, l, c = d["maxima"], d["minima"], d["fechamento"]
    meio = lambda n: (h.rolling(n).max() + l.rolling(n).min()) / 2   # noqa: E731
    tenkan, kijun = meio(9), meio(26)
    out = {}
    # F1: ultimo H1 FECHADO acima / abaixo da nuvem do H1.
    m15 = d.assign(sessao_id=pd.factorize(d["dia"])[0])
    h1 = reamostrar(m15, 60)
    sup1, inf1 = nuvem(h1, P)
    h1 = h1.assign(fim=h1["tempo_ativo"] + pd.Timedelta(minutes=60),
                   acima=h1["fechamento"].to_numpy() > sup1, abaixo=h1["fechamento"].to_numpy() < inf1)
    fecha15 = pd.DataFrame({"fim": d["tempo_ativo"] + pd.Timedelta(minutes=15), "i": np.arange(len(d))})
    m = pd.merge_asof(fecha15.sort_values("fim"), h1[["fim", "acima", "abaixo"]].sort_values("fim"),
                      on="fim", direction="backward").sort_values("i")
    out[FILTROS[0]] = (m["acima"].fillna(False).to_numpy(bool), m["abaixo"].fillna(False).to_numpy(bool))
    out[FILTROS[1]] = ((tenkan > kijun).to_numpy(), (tenkan < kijun).to_numpy())
    out[FILTROS[2]] = ((c > c.shift(26)).to_numpy(), (c < c.shift(26)).to_numpy())
    hora = (d["tempo_ativo"] + pd.Timedelta(hours=OFFSET_H[mk])).dt.hour
    ok = ((hora >= 10) & (hora < 20)).to_numpy()
    out[FILTROS[3]] = (ok, ok)
    tr = np.maximum(h - l, np.maximum((h - c.shift()).abs(), (l - c.shift()).abs()))
    atr = tr.rolling(14).mean()
    ok = (atr > atr.rolling(20 * 96, min_periods=96).median()).to_numpy()
    out[FILTROS[4]] = (ok, ok)
    a_raw, b_raw = (tenkan + kijun) / 2, meio(52)
    out[FILTROS[5]] = ((a_raw > b_raw).to_numpy(), (a_raw < b_raw).to_numpy())
    return out


# ------------------------------------------------------------------ simulacao
def rodar(spec):
    mk, combo = spec
    d, custo, ponto, fl = carregar(mk)
    pc = pv = None
    for f in combo:
        c_, v_ = fl[f]
        pc = c_ if pc is None else (pc & c_)
        pv = v_ if pv is None else (pv & v_)
    return spec, simular_ichimoku(d, P, custo, ponto, permitir_compra=pc, permitir_venda=pv)


def resumo(t: pd.DataFrame, anos: tuple[int, int]) -> dict:
    ano = pd.to_datetime(t["tempo_entrada"]).dt.year
    t = t[(ano >= anos[0]) & (ano <= anos[1])]
    if t.empty:
        return {"n": 0, "r": np.nan, "ano": np.nan, "grandes": 0}
    span = max((pd.to_datetime(t["tempo_saida"]).max() - pd.to_datetime(t["tempo_entrada"]).min()).days / 365.25, 0.1)
    return {"n": len(t), "r": t["r"].mean(), "ano": t["r"].sum() / span, "grandes": int((t["r"] >= 5).sum())}


def tabela(titulo, linhas):
    print(f"\n  {titulo}")
    print(f"  {'filtro':<42}{'mercado':<9}{'trades':>7}{'R/trade':>9}{'R/ano':>8}{'trades >=5R':>13}")
    print("  " + "-" * 88)
    for rot, mk, x, base in linhas:
        g = f"{x['grandes']}/{base['grandes']}" if base else str(x["grandes"])
        print(f"  {rot:<42}{mk:<9}{x['n']:>7}{x['r']:>+9.3f}{x['ano']:>+8.1f}{g:>13}")


def main() -> int:
    descoberta = ["ouro", "USDJPY"]
    combos = [()] + [(f,) for f in FILTROS]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(ex.map(rodar, [(mk, c) for mk in descoberta for c in combos], chunksize=1))

    linhas, aprovados = [], []
    for c in combos:
        ok = True
        for mk in descoberta:
            base, x = resumo(res[(mk, ())], (2022, 2024)), resumo(res[(mk, c)], (2022, 2024))
            linhas.append((" + ".join(c) or "sem filtro", mk, x, base if c else None))
            if c and not (x["ano"] > base["ano"] and x["r"] > base["r"]):
                ok = False
        if c and ok:
            aprovados.append(c[0])
    tabela("DESCOBERTA 2022-2024, com custo (trades >=5R: com filtro / sem filtro)", linhas)
    print(f"\n  Aprovados pelo protocolo: {aprovados or 'nenhum'}")
    if not aprovados:
        return 0

    candidatos = [(f,) for f in aprovados] + list(itertools.combinations(aprovados, 2))
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res.update(dict(ex.map(rodar, [(mk, c) for mk in descoberta for c in candidatos
                                         if (mk, c) not in res], chunksize=1)))
    linhas = []
    for c in candidatos:
        if len(c) == 2:
            for mk in descoberta:
                linhas.append((" + ".join(c), mk, resumo(res[(mk, c)], (2022, 2024)),
                               resumo(res[(mk, ())], (2022, 2024))))
    if linhas:
        tabela("COMBINACOES DE DOIS APROVADOS, descoberta 2022-2024", linhas)

    novos = list(NOVOS)
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res.update(dict(ex.map(rodar, [(mk, c) for mk in novos for c in [()] + candidatos], chunksize=1)))
    linhas, veredito = [], {}
    for c in candidatos:
        bons = 0
        for mk in descoberta:
            base, x = resumo(res[(mk, ())], (2025, 2026)), resumo(res[(mk, c)], (2025, 2026))
            linhas.append((" + ".join(c), mk + "*", x, base))
            bons += x["ano"] > base["ano"]
        novos_bons = 0
        for mk in novos:
            base, x = resumo(res[(mk, ())], (NOVOS[mk], 2026)), resumo(res[(mk, c)], (NOVOS[mk], 2026))
            linhas.append((" + ".join(c), mk, x, base))
            novos_bons += x["ano"] > base["ano"]
        veredito[" + ".join(c)] = (bons == 2 and novos_bons >= 3, bons, novos_bons)
    for mk in novos:
        linhas.append(("(sem filtro)", mk, resumo(res[(mk, ())], (NOVOS[mk], 2026)), None))
    tabela("CONFIRMACAO (* = ouro/USDJPY 2025-2026; pares novos desde o inicio da serie)", linhas)
    print("\n  Veredito (precisa melhorar o total nos 2 ativos em 2025-26 e em >= 3 dos 4 pares):")
    for k, (ok, b, n) in veredito.items():
        print(f"    {k:<42} {'CONFIRMADO' if ok else 'nao confirmado'}  (2025-26: {b}/2, pares novos: {n}/4)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
