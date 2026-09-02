"""
Quatro hipoteses do operador, testadas contra os dados.

  A) Depois de fechar o gap e romper o fechamento anterior, o preco estende
     ate 1x ou 2x o tamanho do gap.
  B) A volatilidade das 09:30 HK (22:30 de Brasilia) produz candles grandes
     contra a direcao que depois nao se confirmam.
  C) O tamanho do primeiro candle do dia dita o volume total do pregao.
  D) Segunda-feira e um dos melhores dias e o volume cai ate sexta.

Regra da casa nestas analises: toda taxa vem acompanhada de uma comparacao.
"Acontece em 60% das vezes" nao significa nada sozinho - a pergunta e sempre
60% contra o que.

    .venv/Scripts/python.exe analises/padroes_autor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from configuracao import Config  # noqa: E402

LARGURA = 78
NOMES_DIA = {0: "segunda", 1: "terca", 2: "quarta", 3: "quinta", 4: "sexta"}


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


def carregar() -> pd.DataFrame:
    cfg = Config.carregar()
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    df = pd.read_parquet(pasta / "HK50_M15_pregao.parquet").sort_values("tempo_ativo")
    df["dia"] = df["tempo_ativo"].dt.date
    df["hhmm"] = df["tempo_ativo"].dt.strftime("%H:%M")
    return df.reset_index(drop=True)


# =============================================================== hipotese A

def extensao_apos_fechar_gap(df: pd.DataFrame) -> None:
    titulo("A) DEPOIS DE FECHAR O GAP, O PRECO ESTENDE 1x OU 2x O GAP?")

    dias = df.groupby("dia").agg(
        abertura=("abertura", "first"), fechamento=("fechamento", "last"),
        maxima=("maxima", "max"), minima=("minima", "min"))
    dias["fecha_anterior"] = dias["fechamento"].shift()
    dias["gap"] = dias["abertura"] - dias["fecha_anterior"]
    dias["amplitude"] = dias["maxima"] - dias["minima"]
    dias = dias.dropna(subset=["gap"])
    dias = dias[dias["gap"].abs() >= 25]     # gap pequeno demais nao tem "tamanho"

    por_dia = {d: g.reset_index(drop=True) for d, g in df.groupby("dia")}
    niveis = [0.5, 1.0, 1.5, 2.0]
    linhas = []

    for dia, l in dias.iterrows():
        g = por_dia[dia]
        alvo_fechar = l["fecha_anterior"]
        sobe = l["gap"] < 0     # gap de queda: fechar o gap e SUBIR ate ontem

        toque = (g["maxima"] >= alvo_fechar) if sobe else (g["minima"] <= alvo_fechar)
        if not toque.any():
            continue
        i = int(toque.idxmax())

        # Depois de tocar o fechamento de ontem, ate onde foi? Medido em
        # multiplos do proprio gap, na mesma direcao do movimento de fechamento.
        resto = g.iloc[i:]
        if sobe:
            extremo_favor = resto["maxima"].max() - alvo_fechar
            extremo_contra = alvo_fechar - resto["minima"].min()
        else:
            extremo_favor = alvo_fechar - resto["minima"].min()
            extremo_contra = resto["maxima"].max() - alvo_fechar

        tamanho = abs(l["gap"])
        linhas.append({
            "dia": dia, "gap": l["gap"], "tamanho": tamanho,
            "candle_do_toque": i,
            "candles_restantes": len(resto) - 1,
            "extensao_mult": extremo_favor / tamanho,
            "contra_mult": extremo_contra / tamanho,
            "amplitude_mult": l["amplitude"] / tamanho,
        })

    e = pd.DataFrame(linhas)
    print(f"  {len(e)} pregoes com gap >= 25 pontos que voltaram a tocar o")
    print(f"  fechamento anterior (de {len(dias)} com gap relevante).\n")

    print("  Ate onde o preco foi DEPOIS de tocar o fechamento de ontem?")
    print(f"    {'nivel':<28}{'alcancou':>11}{'na direcao oposta':>21}")
    print("    " + "-" * 60)
    for n in niveis:
        a_favor = (e["extensao_mult"] >= n).mean()
        oposto = (e["contra_mult"] >= n).mean()
        print(f"    {n:.1f}x o gap ({n*100:>3.0f}%){'':<10}{a_favor:>10.1%}{oposto:>21.1%}")

    print("\n  >>> A coluna da direita e o teste de honestidade: e o mesmo nivel")
    print("      medido para o lado CONTRARIO. Se os dois numeros forem parecidos,")
    print("      o preco so esta oscilando, e nao 'buscando' um alvo.")

    print(f"\n  Extensao mediana alcancada: {e['extensao_mult'].median():.2f}x o gap")
    print(f"  Excursao mediana contraria:  {e['contra_mult'].median():.2f}x o gap")
    print(f"  Amplitude do dia / tamanho do gap (mediana): {e['amplitude_mult'].median():.2f}x")

    print("\n  Quando o toque acontece (candle do pregao, 0 = a propria abertura):")
    for rot, q in [("p25", .25), ("mediana", .50), ("p75", .75)]:
        c = e["candle_do_toque"].quantile(q)
        print(f"    {rot:<10}candle {c:>4.0f}  ({c*15:>4.0f} min de pregao)")

    cedo = e[e["candle_do_toque"] <= 4]
    tarde = e[e["candle_do_toque"] > 8]
    print("\n  A extensao depende de sobrar tempo de pregao?")
    print(f"    tocou na 1a hora  ({len(cedo):>3} dias): "
          f"alcanca 1x em {(cedo['extensao_mult'] >= 1).mean():.0%}, "
          f"2x em {(cedo['extensao_mult'] >= 2).mean():.0%}")
    print(f"    tocou apos 2h     ({len(tarde):>3} dias): "
          f"alcanca 1x em {(tarde['extensao_mult'] >= 1).mean():.0%}, "
          f"2x em {(tarde['extensao_mult'] >= 2).mean():.0%}")


# =============================================================== hipotese B

def volatilidade_por_horario(df: pd.DataFrame) -> None:
    titulo("B) OS CANDLES DAS 09:30 HK (22:30 BRASILIA) SAO ARMADILHA?")

    d = df.copy()
    d["corpo"] = (d["fechamento"] - d["abertura"]).abs()
    d["amplitude"] = d["maxima"] - d["minima"]
    d["pavio_alto"] = d["maxima"] - d[["abertura", "fechamento"]].max(axis=1)
    d["pavio_baixo"] = d[["abertura", "fechamento"]].min(axis=1) - d["minima"]
    d["pavio_total"] = d["pavio_alto"] + d["pavio_baixo"]
    # Candle "armadilha": pavio muito maior que corpo. O preco foi longe e
    # voltou dentro do proprio candle - exatamente o que estoura um stop na
    # mesa sem que o movimento se confirme.
    d["armadilha"] = d["pavio_total"] > 2 * d["corpo"]

    p = d.groupby("hhmm").agg(
        amplitude=("amplitude", "median"),
        corpo=("corpo", "median"),
        pavio=("pavio_total", "median"),
        armadilha=("armadilha", "mean"),
        p95_amplitude=("amplitude", lambda s: s.quantile(.95)),
        n=("amplitude", "size")).reset_index()
    p = p[p["n"] > 200]

    pico = p["amplitude"].max()
    print(f"  {'HK':<7}{'Bras.':<8}{'amplitude':>11}{'corpo':>8}{'pavio':>8}"
          f"{'p95':>8}{'% armadilha':>13}")
    print("  " + "-" * 64)
    for l in p.itertuples():
        h, m = int(l.hhmm[:2]), int(l.hhmm[3:])
        bras = f"{(h-11)%24:02d}:{m:02d}"
        marca = "  <<<" if l.amplitude > pico * 0.85 else ""
        print(f"  {l.hhmm:<7}{bras:<8}{l.amplitude:>11.0f}{l.corpo:>8.0f}"
              f"{l.pavio:>8.0f}{l.p95_amplitude:>8.0f}{l.armadilha:>12.0%}{marca}")

    abertura = p[p["hhmm"].isin(["09:15", "09:30", "09:45"])]
    resto = p[~p["hhmm"].isin(["09:15", "09:30", "09:45"])]
    print(f"\n  Primeiros 45 min contra o resto do pregao:")
    print(f"    amplitude mediana .... {abertura['amplitude'].median():>5.0f} "
          f"contra {resto['amplitude'].median():>5.0f}  "
          f"({abertura['amplitude'].median()/resto['amplitude'].median():.1f}x)")
    print(f"    amplitude p95 ........ {abertura['p95_amplitude'].median():>5.0f} "
          f"contra {resto['p95_amplitude'].median():>5.0f}  "
          f"({abertura['p95_amplitude'].median()/resto['p95_amplitude'].median():.1f}x)")
    print(f"    pavio mediano ........ {abertura['pavio'].median():>5.0f} "
          f"contra {resto['pavio'].median():>5.0f}")


def excursao_contraria(df: pd.DataFrame) -> None:
    """Quanto o preco anda CONTRA um sinal antes de andar a favor?

    E o numero que decide se um stop na mesa sobrevive. Se a excursao contraria
    tipica de um sinal das 09:30 for maior que a de um sinal das 14:00, entao
    um stop de tamanho fixo e apertado demais na abertura - que e exatamente a
    experiencia relatada.
    """
    titulo("B2) QUANTO O PRECO ANDA CONTRA O SINAL ANTES DE ANDAR A FAVOR?")

    caminho = Path(__file__).resolve().parent.parent / "reports" / "sinais_por_ordem.csv"
    if not caminho.exists():
        print("  (rode analises/primeiro_sinal.py antes)")
        return
    sinais = pd.read_csv(caminho)

    maximas = df["maxima"].to_numpy()
    minimas = df["minima"].to_numpy()
    registros = []
    for r in sinais.itertuples():
        fim = min(r.indice + 8, len(df) - 1)       # 2 horas seguintes
        janela_max = maximas[r.indice + 1: fim + 1]
        janela_min = minimas[r.indice + 1: fim + 1]
        if len(janela_max) == 0:
            continue
        if r.direcao == 1:
            contra = r.preco - janela_min.min()
            favor = janela_max.max() - r.preco
        else:
            contra = janela_max.max() - r.preco
            favor = r.preco - janela_min.min()
        registros.append({"hora": r.hora, "contra": contra, "favor": favor})

    x = pd.DataFrame(registros)
    p = x.groupby("hora").agg(contra=("contra", "median"), favor=("favor", "median"),
                              contra_p90=("contra", lambda s: s.quantile(.90)),
                              n=("contra", "size")).reset_index()
    p = p[p["n"] >= 40]

    print(f"  {'HK':<7}{'Bras.':<8}{'sinais':>8}{'contra':>9}{'a favor':>10}"
          f"{'contra p90':>13}{'razao':>8}")
    print("  " + "-" * 58)
    for l in p.itertuples():
        h, m = int(l.hora[:2]), int(l.hora[3:])
        bras = f"{(h-11)%24:02d}:{m:02d}"
        razao = l.favor / l.contra if l.contra else float("nan")
        marca = "  <<<" if razao > 1.15 else ""
        print(f"  {l.hora:<7}{bras:<8}{l.n:>8}{l.contra:>9.0f}{l.favor:>10.0f}"
              f"{l.contra_p90:>13.0f}{razao:>8.2f}{marca}")
    print("\n  'contra' = excursao contraria mediana nas 2h seguintes ao sinal.")
    print("  Um stop menor que esse numero e estourado na metade das vezes")
    print("  ANTES de o movimento ter chance de acontecer.")


# =============================================================== hipotese C

def primeiro_candle_dita_o_dia(df: pd.DataFrame) -> None:
    titulo("C) O PRIMEIRO CANDLE DITA O VOLUME DO PREGAO?")

    primeiro = df.groupby("dia").first()
    dia = df.groupby("dia").agg(volume_dia=("volume_ticks", "sum"),
                                maxima=("maxima", "max"), minima=("minima", "min"),
                                candles=("abertura", "size"))
    dia = dia[dia["candles"] >= 20]              # so pregoes completos

    x = pd.DataFrame({
        "corpo": (primeiro["fechamento"] - primeiro["abertura"]).abs(),
        "amplitude_1o": primeiro["maxima"] - primeiro["minima"],
        "volume_1o": primeiro["volume_ticks"],
        "volume_dia": dia["volume_dia"],
        "amplitude_dia": dia["maxima"] - dia["minima"],
    }).dropna()

    print(f"  Base: {len(x)} pregoes completos.\n")
    print("  Correlacao de Spearman (ordena em vez de assumir linha reta):")
    print(f"    {'preditor':<32}{'volume do dia':>16}{'amplitude do dia':>19}")
    print("    " + "-" * 66)
    for rot, col in [("corpo do 1o candle (sem pavio)", "corpo"),
                     ("amplitude do 1o candle (com pavio)", "amplitude_1o"),
                     ("volume do 1o candle", "volume_1o")]:
        cv = x[col].corr(x["volume_dia"], method="spearman")
        ca = x[col].corr(x["amplitude_dia"], method="spearman")
        print(f"    {rot:<32}{cv:>16.2f}{ca:>19.2f}")

    print("\n  Por quintil do CORPO do primeiro candle (sem pavio):")
    x["quintil"] = pd.qcut(x["corpo"], 5, labels=["1 menor", "2", "3", "4", "5 maior"])
    q = x.groupby("quintil", observed=True).agg(
        corpo=("corpo", "median"), volume=("volume_dia", "median"),
        amplitude=("amplitude_dia", "median"), n=("corpo", "size"))
    print(f"    {'quintil':<10}{'corpo':>9}{'volume do dia':>16}{'amplitude':>13}")
    for i, l in q.iterrows():
        print(f"    {str(i):<10}{l['corpo']:>9.0f}{l['volume']:>16.0f}{l['amplitude']:>13.0f}")

    razao_v = q["volume"].iloc[-1] / q["volume"].iloc[0]
    razao_a = q["amplitude"].iloc[-1] / q["amplitude"].iloc[0]
    print(f"\n    >>> do menor para o maior quintil: volume {razao_v:.2f}x, "
          f"amplitude {razao_a:.2f}x")

    print("\n  Mesma tabela pela AMPLITUDE do 1o candle (com pavio):")
    x["quintil_amp"] = pd.qcut(x["amplitude_1o"], 5, labels=["1 menor", "2", "3", "4", "5 maior"])
    q2 = x.groupby("quintil_amp", observed=True).agg(
        amp1=("amplitude_1o", "median"), volume=("volume_dia", "median"),
        amplitude=("amplitude_dia", "median"))
    print(f"    {'quintil':<10}{'ampl. 1o':>11}{'volume do dia':>16}{'amplitude':>13}")
    for i, l in q2.iterrows():
        print(f"    {str(i):<10}{l['amp1']:>11.0f}{l['volume']:>16.0f}{l['amplitude']:>13.0f}")
    print(f"\n    >>> do menor para o maior quintil: "
          f"volume {q2['volume'].iloc[-1]/q2['volume'].iloc[0]:.2f}x, "
          f"amplitude {q2['amplitude'].iloc[-1]/q2['amplitude'].iloc[0]:.2f}x")


# =============================================================== hipotese D

def volume_por_dia_da_semana(df: pd.DataFrame) -> None:
    titulo("D) SEGUNDA E O MELHOR DIA? O VOLUME CAI ATE SEXTA?")

    dia = df.groupby("dia").agg(volume=("volume_ticks", "sum"),
                                maxima=("maxima", "max"), minima=("minima", "min"),
                                abertura=("abertura", "first"),
                                fechamento=("fechamento", "last"),
                                candles=("abertura", "size"))
    dia = dia[dia["candles"] >= 20]
    dia["amplitude"] = dia["maxima"] - dia["minima"]
    dia["deslocamento"] = (dia["fechamento"] - dia["abertura"]).abs()
    # Direcionalidade: quanto do movimento do dia virou deslocamento liquido.
    # Alto = dia de tendencia. Baixo = dia que balancou e nao foi a lugar nenhum,
    # que e onde uma estrategia de rompimento apanha.
    dia["direcionalidade"] = dia["deslocamento"] / dia["amplitude"]
    dia["dow"] = pd.to_datetime(pd.Series(dia.index)).dt.dayofweek.values

    p = dia.groupby("dow").agg(
        pregoes=("volume", "size"), volume=("volume", "median"),
        amplitude=("amplitude", "median"), desloc=("deslocamento", "median"),
        direcional=("direcionalidade", "median"))

    base = p["volume"].max()
    print(f"  {'dia':<10}{'pregoes':>9}{'volume':>10}{'vs pico':>10}"
          f"{'amplitude':>12}{'desloc.':>10}{'direcional':>12}")
    print("  " + "-" * 73)
    for k, l in p.iterrows():
        barra = "#" * int(l["volume"] / base * 16)
        print(f"  {NOMES_DIA[k]:<10}{l['pregoes']:>9.0f}{l['volume']:>10.0f}"
              f"{l['volume']/base:>9.0%} {barra:<17}{l['amplitude']:>7.0f}"
              f"{l['desloc']:>10.0f}{l['direcional']:>10.0%}")

    print(f"\n  Volume: maior na {NOMES_DIA[p['volume'].idxmax()]}, "
          f"menor na {NOMES_DIA[p['volume'].idxmin()]} "
          f"(diferenca de {p['volume'].max()/p['volume'].min() - 1:.0%})")
    print(f"  Direcionalidade: maior na {NOMES_DIA[p['direcional'].idxmax()]}, "
          f"menor na {NOMES_DIA[p['direcional'].idxmin()]}")
    print("\n  'direcional' = |fechamento - abertura| / amplitude do dia.")
    print("  Perto de 100% o dia andou em linha reta; perto de 0% ele balancou")
    print("  e voltou - o regime em que rompimento de canal apanha.")


def main() -> int:
    df = carregar()
    extensao_apos_fechar_gap(df)
    volatilidade_por_horario(df)
    excursao_contraria(df)
    primeiro_candle_dita_o_dia(df)
    volume_por_dia_da_semana(df)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
