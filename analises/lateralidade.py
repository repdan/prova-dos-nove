"""
Duas investigacoes que preparam a Etapa 4.

  PARTE 1 - Os sinais descartados por ja haver posicao aberta eram melhores ou
            piores que os executados? A resposta muda conforme o regime?

  PARTE 2 - A lateralidade do dia e previsivel a tempo de nao operar nela?
            Testa varios candidatos, comecando pelo volume.

Sobre normalizacao: volume bruto nao serve como preditor num historico de 4
anos - ele cresce e encolhe com o tempo, entao "volume alto" em 2022 e outra
coisa em 2026. Todo preditor de volume e amplitude aqui e relativo a mediana
dos ultimos 20 pregoes do proprio ativo.

    .venv/Scripts/python.exe analises/lateralidade.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.contexto_diario import direcionalidade_por_dia  # noqa: E402
from backtest.motor import montar_do_config  # noqa: E402
from configuracao import Config  # noqa: E402

LARGURA = 80
JANELA = 20        # pregoes usados como referencia para normalizar
CORTE_LATERAL = 0.25


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


# ============================================================ PARTE 1

def sinais_perdidos(cfg: Config) -> None:
    titulo("PARTE 1 - OS SINAIS DESCARTADOS ERAM MELHORES OU PIORES?")

    # Sequencial: uma posicao por vez, como no backtest de verdade.
    motor_seq, feed = montar_do_config(cfg, modo_saida="stop_gain")
    executados = motor_seq.rodar(feed).quadro

    # Simultaneo: toda entrada vira trade, sem a regra de ocupacao.
    motor_todos, feed2 = montar_do_config(cfg, modo_saida="stop_gain")
    motor_todos.permitir_simultaneas = True
    todos = motor_todos.rodar(feed2).quadro

    chaves = set(pd.to_datetime(executados["tempo_entrada"]))
    todos["foi_executado"] = pd.to_datetime(todos["tempo_entrada"]).isin(chaves)

    pregao = pd.read_parquet(
        cfg.caminho_absoluto("coleta.pasta_saida") / "HK50_M15_pregao.parquet")
    dir_dia = direcionalidade_por_dia(pregao)
    todos["dia"] = pd.to_datetime(todos["tempo_entrada"]).dt.date
    todos = todos.join(dir_dia, on="dia").dropna(subset=["posterior_direcionalidade"])
    todos["lateral"] = todos["posterior_direcionalidade"] < CORTE_LATERAL

    print(f"  Populacao completa de sinais que viraram trade: {len(todos)}")
    print(f"    executados pela regra de uma posicao ... {int(todos['foi_executado'].sum())}")
    print(f"    descartados ............................ {int((~todos['foi_executado']).sum())}\n")

    def bloco(rot: str, m: pd.Series) -> None:
        g = todos[m]
        if g.empty:
            return
        r = g["resultado_pontos"]
        print(f"  {rot:<34}{len(g):>7}{r.sum():>10.0f}{r.mean():>9.1f}"
              f"{(r > 0).mean():>9.0%}")

    print(f"  {'grupo':<34}{'trades':>7}{'total':>10}{'media':>9}{'acerto':>9}")
    print("  " + "-" * 69)
    bloco("EXECUTADOS", todos["foi_executado"])
    bloco("DESCARTADOS", ~todos["foi_executado"])
    print()
    bloco("  executados / dia lateral", todos["foi_executado"] & todos["lateral"])
    bloco("  descartados / dia lateral", ~todos["foi_executado"] & todos["lateral"])
    print()
    bloco("  executados / dia direcional", todos["foi_executado"] & ~todos["lateral"])
    bloco("  descartados / dia direcional", ~todos["foi_executado"] & ~todos["lateral"])

    print("\n  Leitura: se os descartados forem PIORES, a regra de uma posicao")
    print("  ja esta filtrando sozinha e nao ha o que recuperar. Se forem")
    print("  melhores, ha dinheiro parado na mesa.")

    return todos


# ============================================================ PARTE 2

def montar_features(cfg: Config) -> pd.DataFrame:
    """Uma linha por pregao, com preditores e o alvo (direcionalidade)."""
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    p = pd.read_parquet(pasta / "HK50_M15_pregao.parquet").sort_values("tempo_ativo")
    p["dia"] = p["tempo_ativo"].dt.date

    d = p.groupby("dia").agg(
        abertura=("abertura", "first"), fechamento=("fechamento", "last"),
        maxima=("maxima", "max"), minima=("minima", "min"),
        volume=("volume_ticks", "sum"), candles=("abertura", "size"))
    d = d[d["candles"] >= 20]
    d["amplitude"] = d["maxima"] - d["minima"]
    d["direcionalidade"] = (d["fechamento"] - d["abertura"]).abs() / d["amplitude"]
    d["lateral"] = d["direcionalidade"] < CORTE_LATERAL

    # --- primeiro candle e primeira hora ---
    g = p.groupby("dia")
    d["vol_1o"] = g["volume_ticks"].first()
    d["amp_1o"] = g["maxima"].first() - g["minima"].first()
    d["vol_1h"] = g["volume_ticks"].apply(lambda s: s.iloc[:4].sum())
    d["amp_1h"] = (g["maxima"].apply(lambda s: s.iloc[:4].max())
                   - g["minima"].apply(lambda s: s.iloc[:4].min()))

    # Razao de eficiencia de Kaufman na primeira hora: quanto do caminho
    # percorrido virou deslocamento liquido. E a mesma ideia da direcionalidade
    # do dia, so que medida cedo - o candidato mais direto a preditor.
    def eficiencia(s: pd.Series) -> float:
        v = s.iloc[:4].to_numpy()
        if len(v) < 2:
            return np.nan
        caminho = np.abs(np.diff(v)).sum()
        return abs(v[-1] - v[0]) / caminho if caminho else np.nan
    d["eficiencia_1h"] = g["fechamento"].apply(eficiencia)

    # Quantas vezes o preco atravessou a media do proprio dia na primeira hora.
    # Muitas travessias = preco serrando, sem direcao.
    def cruzamentos(s: pd.Series) -> int:
        v = s.iloc[:4].to_numpy()
        if len(v) < 2:
            return 0
        acima = v > v.mean()
        return int((acima[1:] != acima[:-1]).sum())
    d["cruzamentos_1h"] = g["fechamento"].apply(cruzamentos)

    # --- referencias do dia anterior ---
    d["fecha_anterior"] = d["fechamento"].shift()
    d["gap"] = d["abertura"] - d["fecha_anterior"]
    d["gap_abs"] = d["gap"].abs()
    d["direcionalidade_ontem"] = d["direcionalidade"].shift()
    d["amplitude_ontem"] = d["amplitude"].shift()

    # --- normalizacao: tudo relativo a mediana movel dos ultimos 20 pregoes ---
    # shift(1) e obrigatorio: a mediana precisa terminar ONTEM, senao o proprio
    # dia entra na sua referencia e o preditor enxerga o presente.
    for col in ["vol_1o", "vol_1h", "amp_1o", "amp_1h", "gap_abs", "volume", "amplitude"]:
        base = d[col].shift(1).rolling(JANELA).median()
        d[f"{col}_rel"] = d[col] / base

    return d.dropna(subset=["direcionalidade", "vol_1o_rel", "eficiencia_1h"])


def avaliar(d: pd.DataFrame) -> None:
    from sklearn.metrics import roc_auc_score

    titulo("PARTE 2 - DA PARA PREVER O DIA LATERAL?")
    print(f"  Base: {len(d)} pregoes | {d['lateral'].mean():.0%} sao laterais "
          f"(direcionalidade < {CORTE_LATERAL:.0%})\n")

    grupos = [
        ("DISPONIVEL AS 09:30 (a tempo do primeiro sinal)", [
            ("volume do 1o candle (relativo)", "vol_1o_rel"),
            ("amplitude do 1o candle (relativa)", "amp_1o_rel"),
            ("tamanho do gap (relativo)", "gap_abs_rel"),
            ("direcionalidade de ontem", "direcionalidade_ontem"),
        ]),
        ("DISPONIVEL AS 10:15 (depois da primeira hora)", [
            ("volume da 1a hora (relativo)", "vol_1h_rel"),
            ("amplitude da 1a hora (relativa)", "amp_1h_rel"),
            ("eficiencia da 1a hora (Kaufman)", "eficiencia_1h"),
            ("cruzamentos na 1a hora", "cruzamentos_1h"),
        ]),
    ]

    for rot_grupo, feats in grupos:
        print(f"  {rot_grupo}")
        print(f"    {'preditor':<36}{'spearman':>11}{'AUC':>8}{'forca':>10}")
        print("    " + "-" * 63)
        for rot, col in feats:
            x = d[[col, "direcionalidade", "lateral"]].dropna()
            if len(x) < 100:
                continue
            rho = x[col].corr(x["direcionalidade"], method="spearman")
            auc = roc_auc_score(x["lateral"], -x[col])   # AUC de prever lateral
            # AUC 0.5 = moeda. Distancia de 0.5 e o que interessa.
            forca = abs(auc - .5)
            marca = "forte" if forca > .10 else ("fraco" if forca > .04 else "nulo")
            print(f"    {rot:<36}{rho:>11.2f}{auc:>8.2f}{marca:>10}")
        print()

    # Quintis do preditor favorito do operador, para ver o formato da relacao.
    titulo("O VOLUME SOZINHO: COMO A LATERALIDADE SE DISTRIBUI")
    for rot, col in [("volume do 1o candle (relativo)", "vol_1o_rel"),
                     ("volume da 1a hora (relativo)", "vol_1h_rel"),
                     ("eficiencia da 1a hora", "eficiencia_1h")]:
        x = d[[col, "direcionalidade", "lateral"]].dropna().copy()
        # Quintis pelo POSTO, nao pelo valor: a eficiencia satura em 1.0 em
        # muitos dias (primeira hora inteira numa direcao so) e as bordas dos
        # quintis colapsariam. rank(method="first") desempata e garante cinco
        # grupos do mesmo tamanho sempre.
        x["q"] = pd.qcut(x[col].rank(method="first"), 5,
                         labels=["1 menor", "2", "3", "4", "5 maior"])
        g = x.groupby("q", observed=True).agg(
            valor=(col, "median"), direcional=("direcionalidade", "median"),
            lateral=("lateral", "mean"), n=("lateral", "size"))
        print(f"\n  {rot}")
        print(f"    {'quintil':<10}{'valor':>9}{'direcionalidade':>18}{'% lateral':>12}")
        for i, l in g.iterrows():
            print(f"    {str(i):<10}{l['valor']:>9.2f}{l['direcional']:>17.0%}"
                  f"{l['lateral']:>12.0%}")


def combinado(d: pd.DataFrame) -> None:
    """O que se ganha juntando os preditores em vez de usar um so."""
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import TimeSeriesSplit

    titulo("E SE COMBINAR TODOS? (previa do que a Etapa 4 pode alcancar)")

    cedo = ["vol_1o_rel", "amp_1o_rel", "gap_abs_rel", "direcionalidade_ontem"]
    tarde = cedo + ["vol_1h_rel", "amp_1h_rel", "eficiencia_1h", "cruzamentos_1h"]

    for rot, feats in [("so o que existe as 09:30", cedo),
                       ("incluindo a primeira hora", tarde)]:
        x = d[feats + ["lateral"]].dropna()
        X, y = x[feats].to_numpy(), x["lateral"].to_numpy()

        # Validacao por janelas no tempo: nunca treina com dado posterior ao
        # teste. E a mesma disciplina que a Etapa 4 vai exigir.
        aucs = []
        for treino, teste in TimeSeriesSplit(n_splits=5).split(X):
            modelo = GradientBoostingClassifier(random_state=0, n_estimators=120,
                                                max_depth=3)
            modelo.fit(X[treino], y[treino])
            aucs.append(roc_auc_score(y[teste], modelo.predict_proba(X[teste])[:, 1]))

        print(f"  {rot:<32} AUC por janela: "
              + "  ".join(f"{a:.2f}" for a in aucs)
              + f"   media {np.mean(aucs):.2f}")

    print("\n  AUC 0.50 = moeda. 0.60 ja e util como filtro. 0.70+ seria muito bom")
    print("  para previsao de regime de mercado - desconfie se aparecer.")


def main() -> int:
    cfg = Config.carregar()
    sinais_perdidos(cfg)
    d = montar_features(cfg)
    avaliar(d)
    combinado(d)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
