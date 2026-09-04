"""
Procura a assinatura da lateralizacao.

A tentativa anterior falhou porque perguntava a coisa errada: "este DIA vai ser
lateral?". Isso e previsao de 6 horas de mercado a partir da abertura, e nao
tem sinal nenhum (AUC 0,44-0,50).

Aqui a pergunta e outra: "NESTE INSTANTE, o mercado esta lateral?". Nao e
previsao, e leitura de estado - e ela pode ser feita com uma janela rolante
que atravessa a virada de dia. A tese e que lateralizacao e um estado
continuo do mercado, nao uma propriedade do pregao.

Toda feature e medida no candle do sinal, com dados que ja existiam ali.
Nenhuma usa informacao do proprio trade nem do resto do dia.

    .venv/Scripts/python.exe analises/assinatura_lateral.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest import metricas as met  # noqa: E402
from backtest.motor import montar_do_config  # noqa: E402
from configuracao import Config  # noqa: E402

LARGURA = 90


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


# ===================================================== construcao das features

def features_por_candle(p: pd.DataFrame, periodo: int = 20) -> pd.DataFrame:
    """Calcula, para cada candle, o retrato do estado do mercado naquele ponto.

    Regra de ouro: toda janela termina no candle ANTERIOR. Nenhuma feature pode
    enxergar o candle em que a decisao e tomada, senao o resultado seria bom no
    backtest e impossivel ao vivo.
    """
    d = p.sort_values("tempo_ativo").reset_index(drop=True).copy()

    # --- o canal, reconstruido igual ao da estrategia ---
    sup = d["maxima"].rolling(periodo).mean().shift(1)
    inf = d["minima"].rolling(periodo).mean().shift(1)
    meio = (sup + inf) / 2
    d["largura"] = sup - inf

    tr = pd.concat([d["maxima"] - d["minima"],
                    (d["maxima"] - d["fechamento"].shift()).abs(),
                    (d["minima"] - d["fechamento"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    d["atr"] = atr

    # --- 1. COMPRESSAO: canal estreito para o proprio padrao recente ---
    d["largura_rel"] = d["largura"] / d["largura"].rolling(100).mean().shift(1)
    d["largura_por_atr"] = d["largura"] / atr
    # Canal abrindo ou fechando? Tendencia costuma alargar o canal.
    d["largura_variacao"] = d["largura"] / d["largura"].shift(10)

    # --- 2. INCLINACAO: a media anda ou fica parada? ---
    # Normalizada pelo ATR para comparar epocas de volatilidade diferente.
    for n in (5, 10, 20):
        d[f"inclinacao_{n}"] = (meio - meio.shift(n)).abs() / (atr * n) * 100

    # --- 3. EFICIENCIA (Kaufman): quanto do caminho virou deslocamento ---
    fech = d["fechamento"]
    passo = fech.diff().abs()
    for n in (10, 20, 40):
        liquido = (fech - fech.shift(n)).abs()
        d[f"eficiencia_{n}"] = (liquido / passo.rolling(n).sum()).shift(1)

    # --- 4. SERRA: quantas vezes o preco cruzou o meio do canal ---
    acima_meio = (fech > meio).astype(float)
    for n in (10, 20, 40):
        d[f"cruzamentos_{n}"] = acima_meio.diff().abs().rolling(n).sum().shift(1)

    # --- 5. PERSISTENCIA: maior sequencia de candles do mesmo lado ---
    # E a pergunta do operador: "quantidade de candles pra cada lado".
    grupo = (acima_meio != acima_meio.shift()).cumsum()
    sequencia = acima_meio.groupby(grupo).cumcount() + 1
    d["sequencia_atual"] = sequencia.shift(1)
    for n in (20, 40):
        d[f"maior_sequencia_{n}"] = sequencia.rolling(n).max().shift(1)

    # --- 6. MEMORIA: retornos se seguem ou se revertem? ---
    # Autocorrelacao negativa = preco desfaz o que acabou de fazer = lateral.
    ret = fech.pct_change()
    for n in (20, 40):
        d[f"autocorr_{n}"] = (ret.rolling(n)
                              .corr(ret.shift(1)).shift(1))

    # --- 7. VOLATILIDADE relativa ao proprio historico ---
    d["atr_rel"] = atr / atr.rolling(100).mean().shift(1)
    d["volume_rel"] = (d["volume_ticks"]
                       / d["volume_ticks"].rolling(100).mean().shift(1)).shift(1)

    # --- 8. POSICAO do preco dentro do canal ---
    d["pos_no_canal"] = (fech - inf) / d["largura"]

    # --- 9. ADX simplificado: forca direcional ---
    up = d["maxima"].diff()
    down = -d["minima"].diff()
    dm_mais = np.where((up > down) & (up > 0), up, 0.0)
    dm_menos = np.where((down > up) & (down > 0), down, 0.0)
    di_mais = pd.Series(dm_mais).rolling(14).mean() / atr * 100
    di_menos = pd.Series(dm_menos).rolling(14).mean() / atr * 100
    dx = (di_mais - di_menos).abs() / (di_mais + di_menos).replace(0, np.nan) * 100
    d["adx"] = dx.rolling(14).mean().shift(1)

    # tempo_ativo ja veio de p com o fuso preservado; reatribuir por .values
    # descartaria o fuso e quebraria a juncao com os trades.
    return d


# ============================================================ avaliacao

FAMILIAS = {
    "Compressao do canal": ["largura_rel", "largura_por_atr", "largura_variacao"],
    "Inclinacao da media": ["inclinacao_5", "inclinacao_10", "inclinacao_20"],
    "Eficiencia (Kaufman)": ["eficiencia_10", "eficiencia_20", "eficiencia_40"],
    "Serra (cruzamentos)": ["cruzamentos_10", "cruzamentos_20", "cruzamentos_40"],
    "Persistencia de lado": ["sequencia_atual", "maior_sequencia_20", "maior_sequencia_40"],
    "Memoria (autocorrelacao)": ["autocorr_20", "autocorr_40"],
    "Volatilidade e volume": ["atr_rel", "volume_rel"],
    "Forca direcional": ["adx"],
    "Posicao no canal": ["pos_no_canal"],
}


def univariada(t: pd.DataFrame) -> list[tuple[str, float, float]]:
    from sklearn.metrics import roc_auc_score

    titulo("CADA SINAL ISOLADO: SEPARA TRADE BOM DE TRADE RUIM?")
    print(f"  {len(t)} trades | {(t['resultado_pontos'] > 0).mean():.0%} vencedores\n")
    y = (t["resultado_pontos"] > 0).to_numpy()

    resultados = []
    for familia, colunas in FAMILIAS.items():
        print(f"  {familia}")
        print(f"    {'feature':<24}{'AUC':>7}{'q1 media':>11}{'q5 media':>11}"
              f"{'q1 acerto':>11}{'q5 acerto':>11}{'forca':>9}")
        print("    " + "-" * 84)
        for col in colunas:
            x = t[[col, "resultado_pontos"]].dropna()
            if len(x) < 200:
                continue
            yy = (x["resultado_pontos"] > 0).to_numpy()
            auc = roc_auc_score(yy, x[col])
            q = pd.qcut(x[col].rank(method="first"), 5, labels=False)
            g = x.groupby(q)["resultado_pontos"]
            m1, m5 = g.mean().iloc[0], g.mean().iloc[-1]
            a1 = (g.get_group(0) > 0).mean()
            a5 = (g.get_group(4) > 0).mean()
            forca = abs(auc - .5)
            marca = "FORTE" if forca > .06 else ("fraco" if forca > .03 else "-")
            print(f"    {col:<24}{auc:>7.3f}{m1:>11.1f}{m5:>11.1f}"
                  f"{a1:>10.0%}{a5:>11.0%}{marca:>9}")
            resultados.append((col, auc, m5 - m1))
        print()
    return resultados


def combinada(t: pd.DataFrame) -> None:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import TimeSeriesSplit

    titulo("TODAS JUNTAS, COM WALK-FORWARD")
    feats = [c for cols in FAMILIAS.values() for c in cols]
    feats += ["hora_num", "dia_semana"]
    x = t[feats + ["resultado_pontos"]].dropna()
    X = x[feats].to_numpy()
    y = (x["resultado_pontos"] > 0).to_numpy()

    aucs, importancias = [], np.zeros(len(feats))
    for treino, teste in TimeSeriesSplit(n_splits=6).split(X):
        m = GradientBoostingClassifier(random_state=0, n_estimators=200, max_depth=3,
                                       learning_rate=.05, subsample=.8)
        m.fit(X[treino], y[treino])
        aucs.append(roc_auc_score(y[teste], m.predict_proba(X[teste])[:, 1]))
        importancias += m.feature_importances_

    print(f"  Base: {len(x)} trades, {len(feats)} features")
    print(f"  AUC por janela: " + "  ".join(f"{a:.3f}" for a in aucs))
    print(f"  AUC media: {np.mean(aucs):.3f}   (0.50 = moeda)\n")

    ordem = np.argsort(importancias)[::-1]
    print("  Features mais usadas:")
    for i in ordem[:10]:
        print(f"    {feats[i]:<24}{importancias[i]/importancias.sum():>7.1%}")


def teste_do_filtro(t: pd.DataFrame, resultados: list) -> None:
    """A pergunta que decide tudo: o filtro melhora o RESULTADO, nao o AUC?

    AUC alto nao paga conta. O que importa e o que sobra depois de descartar
    trades - e descartar trade tambem descarta os ganhos grandes, que e onde
    esta o lucro de uma estrategia de tendencia.
    """
    titulo("O QUE ACONTECE COM O RESULTADO SE FILTRAR")

    melhores = sorted(resultados, key=lambda r: -abs(r[1] - .5))[:4]
    print(f"  {'filtro':<40}{'trades':>8}{'mantidos':>10}{'total':>10}"
          f"{'media':>9}{'acerto':>9}{'fator':>8}")
    print("  " + "-" * 86)

    base = met.calcular(t)
    fator_base = f"{base.fator_lucro:.2f}"
    print(f"  {'SEM FILTRO (baseline)':<40}{base.trades:>8}{'100%':>10}"
          f"{base.resultado_total_pontos:>10.0f}{base.expectativa_por_trade:>9.1f}"
          f"{base.taxa_acerto:>8.0%}{fator_base:>8}")

    for col, auc, _ in melhores:
        x = t.dropna(subset=[col])
        # Mantem o lado da distribuicao que teve melhor desempenho.
        alto_e_melhor = auc > .5
        for corte in (0.3, 0.5, 0.7):
            limiar = x[col].quantile(1 - corte if alto_e_melhor else corte)
            mant = x[x[col] >= limiar] if alto_e_melhor else x[x[col] <= limiar]
            if len(mant) < 100:
                continue
            m = met.calcular(mant)
            f = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
            marca = "  <<<" if m.fator_lucro > 1.15 else ""
            rot = f"{col} ({'alto' if alto_e_melhor else 'baixo'}, top {corte:.0%})"
            print(f"  {rot:<40}{m.trades:>8}{len(mant)/len(x):>10.0%}"
                  f"{m.resultado_total_pontos:>10.0f}{m.expectativa_por_trade:>9.1f}"
                  f"{m.taxa_acerto:>8.0%}{f:>8}{marca}")

    print("\n  ATENCAO: estes cortes sao ESCOLHIDOS OLHANDO O RESULTADO. Servem")
    print("  para ver se existe sinal, nunca como estrategia. O teste honesto e")
    print("  o walk-forward, e ele vem depois.")


def por_horario_e_dia(t: pd.DataFrame) -> None:
    titulo("HORARIO E DIA DA SEMANA")
    for col, rot, nomes in [("hora", "hora HK", None),
                            ("dia_semana", "dia", {0: "segunda", 1: "terca",
                                                   2: "quarta", 3: "quinta",
                                                   4: "sexta"})]:
        g = t.groupby(col).agg(
            trades=("resultado_pontos", "size"), total=("resultado_pontos", "sum"),
            media=("resultado_pontos", "mean"),
            acerto=("resultado_pontos", lambda s: (s > 0).mean()))
        g = g[g["trades"] >= 25].sort_values("media", ascending=False)
        print(f"\n  {rot:<12}{'trades':>8}{'total':>10}{'media':>9}{'acerto':>9}")
        print("  " + "-" * 48)
        for i, l in g.iterrows():
            nome = nomes.get(i, i) if nomes else i
            extra = "  Bras. " + f"{(int(str(i)[:2])-11)%24:02d}:{str(i)[3:]}" if col == "hora" else ""
            print(f"  {str(nome):<12}{l['trades']:>8.0f}{l['total']:>10.0f}"
                  f"{l['media']:>9.1f}{l['acerto']:>8.0%}{extra}")


def main() -> int:
    cfg = Config.carregar()
    motor, feed = montar_do_config(cfg, modo_saida="stop_gain")
    trades = motor.rodar(feed).quadro

    f = features_por_candle(feed.quadro, cfg.exigir("estrategia.periodo_canal"))
    f = f.set_index("tempo_ativo")

    t = trades.copy()
    t["tempo_entrada"] = pd.to_datetime(t["tempo_entrada"])
    colunas = [c for cols in FAMILIAS.values() for c in cols]
    t = t.join(f[colunas], on="tempo_entrada")
    t["hora"] = t["tempo_entrada"].dt.strftime("%H:%M")
    t["hora_num"] = t["tempo_entrada"].dt.hour * 60 + t["tempo_entrada"].dt.minute
    t["dia_semana"] = t["tempo_entrada"].dt.weekday

    resultados = univariada(t)
    combinada(t)
    teste_do_filtro(t, resultados)
    por_horario_e_dia(t)

    destino = Path(__file__).resolve().parent.parent / "reports" / "trades_com_features.csv"
    t.to_csv(destino, index=False, encoding="utf-8")
    print(f"\n  Trades com todas as features: reports/{destino.name}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
