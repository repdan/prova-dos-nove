"""
Grade mecanizado no HK50, com custos reais.

    .venv/Scripts/python.exe rodar_grade.py [M5|M1]

Perguntas, nesta ordem:
  A) A versao de referencia tem esperanca positiva
     depois de spread, derrapagem e comissao?
  B) O SINAL tem informacao? Mesmas entradas no sentido oposto - se o espelho
     der o mesmo resultado, o que sobra e geometria de stop/take, nao metodo.
  C) O resultado e um plato ou um pico? Grade de variacoes que o propria referencia
     deixa em aberto.
  D) De onde vem: por tipo de entrada, por motivo de saida, por ano.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.grade import Custos, ParametrosGrade, simular

RAIZ = Path(__file__).resolve().parent
LARGURA = 100

REFERENCIA = ParametrosGrade()   # os padroes do modulo sao a leitura de referencia
CUSTO_REAL = Custos(slippage=0.5, comissao_pontos=0.78)
# Regime de spread atual da corretora (4.5 pts), para nao premiar o passado
# com spread caro nem o presente com spread historico errado.
CUSTO_ATUAL = Custos(slippage=0.5, comissao_pontos=0.78, spread_forcado=4.5)


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA + f"\n  {t}\n" + "=" * LARGURA)


def metricas(t: pd.DataFrame) -> dict:
    if t.empty:
        return {}
    r = t["r"].dropna()
    anos = max((pd.Timestamp(t["tempo_saida"].max()) -
                pd.Timestamp(t["tempo_entrada"].min())).days / 365.25, 0.01)
    erro = r.std() / np.sqrt(len(r)) if len(r) > 1 else np.nan
    return {
        "n": len(r), "acerto": (t["resultado"] > 0).mean(),
        "r_medio": r.mean(), "erro": erro,
        "sig": r.mean() / erro if erro and erro > 0 else 0.0,
        "r_ano": r.sum() / anos,
        "pts_bruto": t["resultado_bruto"].mean(), "pts_liq": t["resultado"].mean(),
        "custo": t["custo"].mean(), "w": t["largura"].median(),
        "risco": t["risco"].median(),
        "dias": t["dia"].nunique(),
    }


def cabecalho() -> None:
    print(f"  {'configuracao':<34}{'trades':>7}{'acerto':>8}{'R medio':>9}"
          f"{'sigmas':>8}{'R/ano':>8}{'pts brut':>9}{'pts liq':>9}{'custo':>7}"
          f"{'w med':>7}")
    print("  " + "-" * 96)


def linha(rot: str, m: dict) -> None:
    if not m:
        print(f"  {rot:<34}  (sem trades)")
        return
    print(f"  {rot:<34}{m['n']:>7}{m['acerto']:>8.0%}{m['r_medio']:>+9.3f}"
          f"{m['sig']:>+8.1f}{m['r_ano']:>+8.1f}{m['pts_bruto']:>+9.1f}"
          f"{m['pts_liq']:>+9.1f}{m['custo']:>7.1f}{m['w']:>7.1f}")


def carregar(tf: str) -> pd.DataFrame:
    caminho = RAIZ / "data" / "historico" / "HK50" / f"HK50_{tf}_pregao.parquet"
    df = pd.read_parquet(caminho)
    # Antes de 2022 a base do HK50 e esparsa (ver Etapa 1); o corte e o mesmo.
    return df[df["tempo_ativo"] >= pd.Timestamp("2022-03-01", tz="Asia/Hong_Kong")]


def main() -> int:
    tf = sys.argv[1] if len(sys.argv) > 1 else "M5"
    df = carregar(tf)
    titulo(f"GRADE NO HK50 {tf} — {df['tempo_ativo'].dt.date.nunique()} pregoes, "
           f"{df['tempo_ativo'].min():%Y-%m-%d} a {df['tempo_ativo'].max():%Y-%m-%d}")

    # ---------------------------------------------------------------- A / B
    titulo("A) VERSAO DE REFERENCIA  +  B) CONTROLE (mesmas entradas, sentido oposto)")
    cabecalho()
    base = {}
    for rot, p, c in [
        ("referencia, spread historico", REFERENCIA, CUSTO_REAL),
        ("referencia, spread atual 4.5", REFERENCIA, CUSTO_ATUAL),
        ("referencia, SEM custo", REFERENCIA, Custos(0, 0, 0.0)),
        ("CONTROLE invertido, spread 4.5", replace(REFERENCIA, controle_inverter=True), CUSTO_ATUAL),
        ("CONTROLE invertido, SEM custo", replace(REFERENCIA, controle_inverter=True), Custos(0, 0, 0.0)),
    ]:
        t = simular(df, p, c)
        base[rot] = t
        linha(rot, metricas(t))

    # ------------------------------------------------------------------- C
    titulo("C) PLATO OU PICO — variacoes que a referencia deixa em aberto (spread 4.5)")
    cabecalho()
    grade = [
        ("take 1 nivel (padrao)", {}),
        ("take 2 niveis", {"take_niveis": 2}),
        ("sem take (0x0 / fim do dia)", {"take_niveis": 0}),
        ("stop no toque", {"stop_modo": "toque"}),
        ("sem 0x0", {"usar_0x0": False}),
        ("nao para no take", {"parar_no_take": False}),
        ("canal: so 1a vela", {"velas_maximas": 1, "largura_minima": 0}),
        ("canal: ate 6 velas, larg >= 3", {"velas_maximas": 6, "largura_minima": 3}),
        ("sem vela gigante", {"usar_vela_gigante": False}),
        ("tendencia neutra (sem gap)", {"tendencia": "neutra"}),
        ("so continuacao", {"entrada_50": False, "entrada_reversao": False}),
        ("so 50%", {"entrada_continuacao": False, "entrada_reversao": False}),
        ("so reversao", {"entrada_continuacao": False, "entrada_50": False}),
        ("1 para 1: take 1 / stop 1", {"stop_niveis": 1, "take_niveis": 1}),
        ("2 para 2: take 2 / stop 2", {"stop_niveis": 2, "take_niveis": 2}),
        ("1 stop por dia", {"max_stops_dia": 1}),
        ("stops ilimitados", {"max_stops_dia": 99}),
    ]
    controles = []
    for rot, kw in grade:
        p = replace(REFERENCIA, **kw)
        linha(rot, metricas(simular(df, p, CUSTO_ATUAL)))
        sem = metricas(simular(df, p, Custos(0, 0, 0.0)))
        inv = metricas(simular(df, replace(p, controle_inverter=True), Custos(0, 0, 0.0)))
        controles.append((rot, sem, inv))

    titulo("C2) A MESMA GRADE SEM CUSTO: metodo x espelho (sentido oposto)")
    print(f"  {'configuracao':<34}{'acerto':>8}{'R medio':>9}{'sigmas':>8}"
          f"{'|':>4}{'acerto':>8}{'R medio':>9}{'sigmas':>8}")
    print(f"  {'':<34}{'--- metodo ---':>25}{'':>4}{'--- espelho ---':>25}")
    print("  " + "-" * 92)
    for rot, sem, inv in controles:
        if sem and inv:
            print(f"  {rot:<34}{sem['acerto']:>8.0%}{sem['r_medio']:>+9.3f}"
                  f"{sem['sig']:>+8.1f}{'|':>4}{inv['acerto']:>8.0%}"
                  f"{inv['r_medio']:>+9.3f}{inv['sig']:>+8.1f}")

    # ------------------------------------------------------------------- D
    t = base["referencia, spread atual 4.5"]
    if not t.empty:
        titulo("D) DE ONDE VEM (versao de referencia, spread 4.5)")
        print("  por tipo de entrada:")
        cabecalho()
        for k, g in t.groupby("tipo"):
            linha(f"  {k}", metricas(g))
        print("\n  por motivo de saida:")
        cabecalho()
        for k, g in t.groupby("motivo"):
            linha(f"  {k}", metricas(g))
        print("\n  por ano:")
        cabecalho()
        for k, g in t.groupby(pd.to_datetime(t["tempo_entrada"]).dt.year):
            linha(f"  {k}", metricas(g))
        print("\n  por posicao do trade no dia (1o, 2o, 3o...):")
        cabecalho()
        ordem = t.groupby("dia").cumcount() + 1
        for k, g in t.groupby(ordem.clip(upper=4)):
            linha(f"  {k}{'+' if k == 4 else ''}o do dia", metricas(g))

        destino = RAIZ / "reports"
        destino.mkdir(exist_ok=True)
        t.to_csv(destino / f"grade_trades_{tf}.csv", index=False, encoding="utf-8")
        print(f"\n  Trades salvos em reports/grade_trades_{tf}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
