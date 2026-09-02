"""
Analise da abertura do HK50: gaps, fechamento de gap e relacao com o dia anterior.

Roda sobre os dados ja coletados, sem precisar do MT5 aberto:
    .venv/Scripts/python.exe analises/abertura_gap.py

Uma distincao que muda a leitura de tudo: este CFD NAO para de negociar as
16:30. Ele tem sessao estendida ate as 03:00 de Hong Kong. Entao o "gap" que
aparece para quem opera so o pregao regular tem duas partes bem diferentes:

  - o pedaco que o preco andou DURANTE o after-hours (negociavel, observavel)
  - o pedaco que apareceu na parada real de 03:00 as 09:15 (esse sim e gap)

Confundir os dois faz parecer que o mercado "salta" quando na verdade ele
caminhou a noite inteira. As duas medidas sao reportadas separadamente.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from configuracao import Config  # noqa: E402

LARGURA = 78
CANDLES_ULTIMA_HORA = 4          # 4 candles M15 = 1 hora final do pregao


def titulo(texto: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {texto}")
    print("=" * LARGURA)


def carregar() -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = Config.carregar()
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    pregao = pd.read_parquet(pasta / "HK50_M15_pregao.parquet")
    bruto = pd.read_parquet(pasta / "HK50_M15_bruto.parquet")
    return pregao, bruto


def montar_dias(pregao: pd.DataFrame, bruto: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por pregao, com tudo que descreve a abertura daquele dia."""
    pregao = pregao.sort_values("tempo_ativo").copy()
    pregao["dia"] = pregao["tempo_ativo"].dt.date

    dias = pregao.groupby("dia").agg(
        abertura=("abertura", "first"),
        fechamento=("fechamento", "last"),
        maxima=("maxima", "max"),
        minima=("minima", "min"),
        volume=("volume_ticks", "sum"),
        candles=("abertura", "size"),
    )

    # Momento final do dia anterior: quanto o preco andou na ultima hora.
    ultimos = (pregao.groupby("dia")["fechamento"]
               .apply(lambda s: s.iloc[-1] - s.iloc[-min(len(s), CANDLES_ULTIMA_HORA + 1)]))
    dias["momento_ultima_hora"] = ultimos

    # Amplitude do dia, usada para normalizar o tamanho do gap.
    dias["amplitude"] = dias["maxima"] - dias["minima"]
    dias["direcao_dia"] = np.sign(dias["fechamento"] - dias["abertura"])

    # --- referencias do dia anterior ---
    dias["fecha_anterior"] = dias["fechamento"].shift()
    dias["abre_anterior"] = dias["abertura"].shift()
    dias["momento_anterior"] = dias["momento_ultima_hora"].shift()
    dias["direcao_anterior"] = dias["direcao_dia"].shift()
    dias["amplitude_anterior"] = dias["amplitude"].shift()

    # --- ultimo preco negociado antes da abertura (inclui after-hours) ---
    bruto = bruto.sort_values("tempo_ativo")
    tempos_abertura = pregao.groupby("dia")["tempo_ativo"].min()
    # .reset_index() em vez de .values: converter para numpy descartaria o fuso
    # da coluna de tempo, e o merge_asof recusaria a juncao.
    esquerda = tempos_abertura.rename("tempo_ativo").reset_index().sort_values("tempo_ativo")
    ref = pd.merge_asof(
        esquerda,
        bruto[["tempo_ativo", "fechamento"]].rename(columns={"fechamento": "ultimo_negociado"}),
        on="tempo_ativo", direction="backward", allow_exact_matches=False,
    ).set_index("dia")
    dias["ultimo_negociado"] = ref["ultimo_negociado"]

    # --- os dois gaps ---
    # Gap de sessao: o que salta aos olhos de quem so opera o pregao regular.
    dias["gap"] = dias["abertura"] - dias["fecha_anterior"]
    # Gap verdadeiro: o que apareceu na parada real, sem negociacao possivel.
    dias["gap_real"] = dias["abertura"] - dias["ultimo_negociado"]
    # O resto andou no after-hours, com o mercado aberto.
    dias["andou_after_hours"] = dias["gap"] - dias["gap_real"]

    return dias.dropna(subset=["fecha_anterior"]).copy()


def marcar_fechamento_de_gap(dias: pd.DataFrame, pregao: pd.DataFrame) -> pd.DataFrame:
    """Para cada dia: o preco voltou ao fechamento de ontem? Quando?"""
    pregao = pregao.copy()
    pregao["dia"] = pregao["tempo_ativo"].dt.date
    por_dia = {d: g.reset_index(drop=True) for d, g in pregao.groupby("dia")}

    fechou, candles_ate, minutos_ate = [], [], []
    for dia, linha in dias.iterrows():
        g = por_dia[dia]
        alvo = linha["fecha_anterior"]
        if linha["gap"] > 0:
            atingiu = g["minima"] <= alvo      # gap de alta fecha caindo ate ontem
        elif linha["gap"] < 0:
            atingiu = g["maxima"] >= alvo
        else:
            atingiu = pd.Series([True] * len(g))

        if atingiu.any():
            i = int(atingiu.idxmax())
            fechou.append(True)
            candles_ate.append(i)
            minutos_ate.append(i * 15)
        else:
            fechou.append(False)
            candles_ate.append(np.nan)
            minutos_ate.append(np.nan)

    dias["gap_fechou"] = fechou
    dias["candles_ate_fechar"] = candles_ate
    dias["minutos_ate_fechar"] = minutos_ate
    return dias


def secao_frequencia(d: pd.DataFrame) -> None:
    titulo("1. COM QUE FREQUENCIA O HK50 ABRE EM GAP?")
    n = len(d)
    print(f"  Base: {n} pregoes ({d.index.min()} a {d.index.max()})\n")

    print("  GAP DE SESSAO (abertura de hoje x fechamento de 16:30 de ontem)")
    for rotulo, limite in [("qualquer gap (!= 0)", 0),
                           ("maior que 10 pontos", 10),
                           ("maior que 25 pontos", 25),
                           ("maior que 50 pontos", 50),
                           ("maior que 100 pontos", 100)]:
        qtd = int((d["gap"].abs() > limite).sum())
        print(f"    {rotulo:<24} {qtd:>5} dias = {qtd/n:>6.1%}")

    print("\n  GAP REAL (abertura x ultimo preco negociado, incluindo after-hours)")
    for rotulo, limite in [("qualquer gap (!= 0)", 0),
                           ("maior que 10 pontos", 10),
                           ("maior que 25 pontos", 25),
                           ("maior que 50 pontos", 50)]:
        qtd = int((d["gap_real"].abs() > limite).sum())
        print(f"    {rotulo:<24} {qtd:>5} dias = {qtd/n:>6.1%}")

    print("\n  TAMANHO (pontos de indice, valor absoluto)")
    print(f"    {'':<12}{'gap de sessao':>16}{'gap real':>14}{'andou no after-h':>20}")
    for rot, q in [("mediana", .50), ("p75", .75), ("p90", .90), ("p99", .99)]:
        print(f"    {rot:<12}{d['gap'].abs().quantile(q):>16.0f}"
              f"{d['gap_real'].abs().quantile(q):>14.0f}"
              f"{d['andou_after_hours'].abs().quantile(q):>20.0f}")

    parte = (d["gap_real"].abs() / d["gap"].abs().replace(0, np.nan)).median()
    print(f"\n  >>> Na mediana, apenas {parte:.0%} do gap de sessao e gap de verdade.")
    print("      O resto o preco caminhou durante o after-hours, com mercado aberto.")


def secao_fechamento(d: pd.DataFrame) -> None:
    titulo("2. O GAP SE FECHA DURANTE O PREGAO?")
    com_gap = d[d["gap"].abs() > 0]
    taxa = com_gap["gap_fechou"].mean()
    print(f"  Considerando os {len(com_gap)} dias com gap:")
    print(f"    fecharam o gap no mesmo pregao ... {com_gap['gap_fechou'].sum():>5} = {taxa:.1%}\n")

    print("  Taxa de fechamento POR TAMANHO DO GAP:")
    faixas = [(0, 10), (10, 25), (25, 50), (50, 100), (100, 200), (200, 10_000)]
    print(f"    {'faixa (pontos)':<20}{'dias':>7}{'fechou':>10}{'mediana p/ fechar':>22}")
    for a, b in faixas:
        m = com_gap[(com_gap["gap"].abs() >= a) & (com_gap["gap"].abs() < b)]
        if m.empty:
            continue
        med = m.loc[m["gap_fechou"], "minutos_ate_fechar"].median()
        med_txt = f"{med:.0f} min" if pd.notna(med) else "-"
        rot = f"{a} a {b}" if b < 10_000 else f"acima de {a}"
        print(f"    {rot:<20}{len(m):>7}{m['gap_fechou'].mean():>9.0%}{med_txt:>22}")

    fechados = com_gap[com_gap["gap_fechou"]]
    print("\n  QUANDO fecha (dos que fecharam):")
    for rot, lim in [("nos primeiros 15 min", 15), ("na primeira hora", 60),
                     ("nas 2 primeiras horas", 120), ("ate o almoco (2h45)", 165)]:
        qtd = int((fechados["minutos_ate_fechar"] <= lim).sum())
        print(f"    {rot:<24} {qtd:>5} = {qtd/len(fechados):>6.1%} dos fechados"
              f"  ({qtd/len(com_gap):>5.1%} do total)")


def secao_direcao(d: pd.DataFrame) -> None:
    titulo("3. A ABERTURA SEGUE A TENDENCIA DO FECHAMENTO ANTERIOR?")
    m = d[(d["gap"].abs() > 10) & (d["momento_anterior"].abs() > 0)].copy()
    m["gap_segue_ultima_hora"] = np.sign(m["gap"]) == np.sign(m["momento_anterior"])
    m["gap_segue_dia"] = np.sign(m["gap"]) == np.sign(m["direcao_anterior"])

    print(f"  Base: {len(m)} dias com gap relevante (> 10 pontos)\n")
    print(f"    gap na direcao da ULTIMA HORA de ontem ... "
          f"{m['gap_segue_ultima_hora'].mean():>6.1%}")
    print(f"    gap na direcao do DIA de ontem ........... "
          f"{m['gap_segue_dia'].mean():>6.1%}")
    print("\n    (50% seria moeda jogada para o alto - e o ponto de comparacao)")


def secao_hipotese(d: pd.DataFrame) -> None:
    titulo("4. AS TRES SITUACOES QUE VOCE DESCREVEU")
    m = d[(d["gap"].abs() > 10)].copy()

    # Como classificar o fechamento de ontem, usando so dado de ontem:
    # compara a direcao do dia inteiro com a direcao da ultima hora, e mede a
    # forca da ultima hora em relacao a amplitude tipica daquele dia.
    forca = (m["momento_anterior"].abs() / m["amplitude_anterior"]).fillna(0)
    mesma_direcao = np.sign(m["momento_anterior"]) == np.sign(m["direcao_anterior"])

    m["cenario"] = np.select(
        [mesma_direcao & (forca >= 0.15),
         forca < 0.15,
         ~mesma_direcao & (forca >= 0.15)],
        ["tendencia permaneceu", "tendencia perdeu forca", "tendencia reverteu"],
        default="indefinido")

    m["gap_a_favor_do_dia"] = np.sign(m["gap"]) == np.sign(m["direcao_anterior"])
    m["gap_a_favor_da_ultima_hora"] = np.sign(m["gap"]) == np.sign(m["momento_anterior"])
    m["fechou_rapido"] = m["minutos_ate_fechar"] <= 60

    print("  Classificacao feita so com dado de ONTEM (sem espiar o dia seguinte):\n")
    print(f"    {'cenario':<26}{'dias':>6}{'gap a favor':>13}{'fechou gap':>12}{'fechou <1h':>12}")
    print("    " + "-" * 69)
    for c in ["tendencia permaneceu", "tendencia perdeu forca", "tendencia reverteu"]:
        g = m[m["cenario"] == c]
        if g.empty:
            continue
        favor = g["gap_a_favor_da_ultima_hora"].mean()
        print(f"    {c:<26}{len(g):>6}{favor:>12.0%}"
              f"{g['gap_fechou'].mean():>12.0%}{g['fechou_rapido'].mean():>12.0%}")

    print("\n  Tempo mediano ate fechar o gap, por cenario:")
    for c in ["tendencia permaneceu", "tendencia perdeu forca", "tendencia reverteu"]:
        g = m[(m["cenario"] == c) & m["gap_fechou"]]
        if not g.empty:
            print(f"    {c:<26} {g['minutos_ate_fechar'].median():>5.0f} min")


def secao_extra(d: pd.DataFrame) -> None:
    titulo("5. ANALISE ADICIONAL - O QUE OS DADOS MOSTRAM ALEM DA PERGUNTA")

    com_gap = d[d["gap"].abs() > 25].copy()
    com_gap["continuou"] = (np.sign(com_gap["gap"]) ==
                            np.sign(com_gap["fechamento"] - com_gap["abertura"]))

    print("  (a) Gap fechado nao significa gap revertido.")
    print("      Dos dias com gap > 25 pontos, o dia FECHOU na direcao do gap em"
          f" {com_gap['continuou'].mean():.0%} das vezes.")
    print("      Ou seja: o preco costuma voltar para tocar o fechamento de ontem")
    print("      e ainda assim terminar o dia do lado do gap.\n")

    grandes = d[d["gap"].abs() > d["gap"].abs().quantile(0.90)]
    print("  (b) Gap grande e dia grande.")
    print(f"      Amplitude mediana num dia comum ......... {d['amplitude'].median():>5.0f} pontos")
    print(f"      Amplitude mediana nos 10% maiores gaps .. {grandes['amplitude'].median():>5.0f} pontos")
    print(f"      Volume mediano num dia comum ............ {d['volume'].median():>7.0f}")
    print(f"      Volume mediano nos 10% maiores gaps ..... {grandes['volume'].median():>7.0f}\n")

    d = d.copy()
    d["dia_semana"] = pd.to_datetime(pd.Series(d.index)).dt.dayofweek.values
    nomes = {0: "segunda", 1: "terca", 2: "quarta", 3: "quinta", 4: "sexta"}
    print("  (c) Segunda-feira carrega o fim de semana inteiro.")
    print(f"      {'dia':<10}{'gap mediano':>14}{'fecha o gap':>14}{'amplitude':>12}")
    for k, nome in nomes.items():
        g = d[d["dia_semana"] == k]
        if g.empty:
            continue
        print(f"      {nome:<10}{g['gap'].abs().median():>14.0f}"
              f"{g['gap_fechou'].mean():>13.0%}{g['amplitude'].median():>12.0f}")


def main() -> int:
    pregao, bruto = carregar()
    dias = montar_dias(pregao, bruto)
    dias = marcar_fechamento_de_gap(dias, pregao)

    secao_frequencia(dias)
    secao_fechamento(dias)
    secao_direcao(dias)
    secao_hipotese(dias)
    secao_extra(dias)

    destino = Path(__file__).resolve().parent.parent / "reports" / "abertura_gap.csv"
    destino.parent.mkdir(exist_ok=True)
    dias.to_csv(destino, encoding="utf-8")
    print(f"\n  Tabela dia a dia salva em: reports/{destino.name}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
