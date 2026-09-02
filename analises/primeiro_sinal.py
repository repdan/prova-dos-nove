"""
Duas perguntas praticas sobre a abertura:

  1. A direcao da abertura e previsivel a partir de algo observavel ANTES dela?
     (testado contra varias referencias, nao so o fechamento das 16:30)

  2. Vale ignorar o primeiro rompimento do dia e esperar o segundo?

A medida usada para "deu certo" e o deslocamento a favor do sinal nos candles
seguintes. Nao e o resultado de um trade - isso so a engine da Etapa 3 dara.
E um proxy honesto e serve para comparar grupos entre si, que e o que importa
aqui: se pular o primeiro sinal ajuda, os grupos tem que diferir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from configuracao import Config  # noqa: E402
from strategy.base import Candle, Sinal  # noqa: E402
from strategy.canal_rompimento import CanalRompimento  # noqa: E402

LARGURA = 78


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


def carregar():
    cfg = Config.carregar()
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    return (cfg,
            pd.read_parquet(pasta / "HK50_M15_pregao.parquet"),
            pd.read_parquet(pasta / "HK50_M15_bruto.parquet"))


# ------------------------------------------------------------------ pergunta 1

def direcao_da_abertura(pregao: pd.DataFrame, bruto: pd.DataFrame) -> None:
    titulo("A DIRECAO DA ABERTURA E PREVISIVEL?")

    pregao = pregao.sort_values("tempo_ativo").copy()
    pregao["dia"] = pregao["tempo_ativo"].dt.date
    bruto = bruto.sort_values("tempo_ativo").copy()

    dias = pregao.groupby("dia").agg(
        abertura=("abertura", "first"), fechamento=("fechamento", "last"),
        tempo_abertura=("tempo_ativo", "min"))
    dias["fecha_anterior"] = dias["fechamento"].shift()
    dias["direcao_dia_anterior"] = np.sign(dias["fechamento"].shift() - dias["abertura"].shift())

    # Momento da ultima hora do pregao anterior.
    ult = pregao.groupby("dia")["fechamento"].apply(
        lambda s: s.iloc[-1] - s.iloc[-min(len(s), 5)])
    dias["momento_16h_anterior"] = ult.shift()

    # Momento do AFTER-HOURS: o preco andou a noite toda, com mercado aberto.
    # Se existe previsibilidade em algum lugar, o candidato mais forte e aqui.
    ah_inicio, ah_fim, ah_ult = [], [], []
    for dia, linha in dias.iterrows():
        janela = bruto[(bruto["tempo_ativo"] < linha["tempo_abertura"])].tail(40)
        if len(janela) < 10:
            ah_inicio.append(np.nan); ah_fim.append(np.nan); ah_ult.append(np.nan); continue
        ah_inicio.append(janela["fechamento"].iloc[0])
        ah_fim.append(janela["fechamento"].iloc[-1])
        ah_ult.append(janela["fechamento"].iloc[-1] - janela["fechamento"].iloc[-9])
    dias["after_hours_total"] = np.array(ah_fim) - np.array(ah_inicio)
    dias["after_hours_ultimas_2h"] = ah_ult
    dias["ultimo_negociado"] = ah_fim

    dias["gap"] = dias["abertura"] - dias["fecha_anterior"]
    dias["gap_real"] = dias["abertura"] - dias["ultimo_negociado"]
    dias["direcao_do_dia"] = np.sign(dias["fechamento"] - dias["abertura"])

    d = dias.dropna(subset=["gap", "after_hours_total"])
    d = d[d["gap"].abs() > 10]

    print(f"  Base: {len(d)} pregoes com gap relevante.\n")
    print("  Acerto ao prever a direcao do GAP DE SESSAO usando:")
    for rot, col in [("direcao do dia anterior", "direcao_dia_anterior"),
                     ("ultima hora do pregao anterior", "momento_16h_anterior"),
                     ("after-hours inteiro", "after_hours_total"),
                     ("ultimas 2h do after-hours", "after_hours_ultimas_2h")]:
        acerto = (np.sign(d["gap"]) == np.sign(d[col])).mean()
        marca = "  <-- informativo" if abs(acerto - .5) > .05 else ""
        print(f"    {rot:<34} {acerto:>6.1%}{marca}")

    print("\n  Acerto ao prever a direcao do GAP REAL (o trecho sem negociacao):")
    for rot, col in [("direcao do dia anterior", "direcao_dia_anterior"),
                     ("ultima hora do pregao anterior", "momento_16h_anterior"),
                     ("after-hours inteiro", "after_hours_total"),
                     ("ultimas 2h do after-hours", "after_hours_ultimas_2h")]:
        acerto = (np.sign(d["gap_real"]) == np.sign(d[col])).mean()
        marca = "  <-- informativo" if abs(acerto - .5) > .05 else ""
        print(f"    {rot:<34} {acerto:>6.1%}{marca}")

    print("\n  E o DIA inteiro? Acerto ao prever se o dia fecha em alta usando:")
    for rot, col in [("direcao do gap", "gap"),
                     ("after-hours inteiro", "after_hours_total"),
                     ("direcao do dia anterior", "direcao_dia_anterior")]:
        acerto = (d["direcao_do_dia"] == np.sign(d[col])).mean()
        marca = "  <-- informativo" if abs(acerto - .5) > .05 else ""
        print(f"    {rot:<34} {acerto:>6.1%}{marca}")


# ------------------------------------------------------------------ pergunta 2

def sinais_com_ordem(cfg, pregao: pd.DataFrame) -> pd.DataFrame:
    """Roda a estrategia e numera os sinais dentro de cada pregao."""
    e = CanalRompimento(periodo_canal=cfg.exigir("estrategia.periodo_canal"),
                        modo_saida="stop_gain", lote=cfg.exigir("estrategia.lote"),
                        preco_referencia=cfg.get("estrategia.preco_referencia", "fechamento"))
    pregao = pregao.sort_values("tempo_ativo").reset_index(drop=True)
    registros = []
    ordem_no_dia: dict = {}

    for i, l in enumerate(pregao.itertuples()):
        s = e.on_candle(Candle(tempo=l.tempo_ativo, abertura=l.abertura, maxima=l.maxima,
                               minima=l.minima, fechamento=l.fechamento,
                               volume=l.volume_ticks, spread=l.spread_pontos))
        if s is Sinal.NENHUM:
            continue
        dia = l.tempo_ativo.date()
        ordem_no_dia[dia] = ordem_no_dia.get(dia, 0) + 1
        registros.append({
            "indice": i, "dia": dia, "hora": l.tempo_ativo.strftime("%H:%M"),
            "ordem": ordem_no_dia[dia],
            "direcao": 1 if s is Sinal.COMPRA else -1,
            "preco": l.fechamento,
        })

    sinais = pd.DataFrame(registros)

    # Deslocamento a favor do sinal apos N candles e ate o fim do pregao.
    fechamentos = pregao["fechamento"].to_numpy()
    dias_arr = pregao["tempo_ativo"].dt.date.to_numpy()
    for n in (4, 8):
        alvo = np.minimum(sinais["indice"].to_numpy() + n, len(fechamentos) - 1)
        sinais[f"desloc_{n}"] = ((fechamentos[alvo] - sinais["preco"].to_numpy())
                                 * sinais["direcao"].to_numpy())

    fim_do_dia = []
    for r in sinais.itertuples():
        mesmo_dia = np.where(dias_arr == r.dia)[0]
        fim_do_dia.append((fechamentos[mesmo_dia[-1]] - r.preco) * r.direcao)
    sinais["desloc_fim_do_dia"] = fim_do_dia
    return sinais


def vale_pular_o_primeiro(sinais: pd.DataFrame) -> None:
    titulo("VALE IGNORAR O PRIMEIRO ROMPIMENTO DO DIA?")
    print(f"  {len(sinais)} sinais em {sinais['dia'].nunique()} pregoes.")
    print("  Deslocamento a favor do sinal, em pontos de indice (mediana):\n")
    print(f"    {'grupo':<28}{'sinais':>8}{'+1h':>9}{'+2h':>9}{'fim do dia':>13}{'% positivo':>13}")
    print("    " + "-" * 80)

    grupos = [
        ("1o sinal do dia", sinais["ordem"] == 1),
        ("  ...dele, so os de 09:15", (sinais["ordem"] == 1) & (sinais["hora"] == "09:15")),
        ("  ...dele, depois das 09:15", (sinais["ordem"] == 1) & (sinais["hora"] != "09:15")),
        ("2o sinal do dia", sinais["ordem"] == 2),
        ("3o sinal ou mais", sinais["ordem"] >= 3),
        ("TODOS", sinais["ordem"] >= 1),
    ]
    for rot, mascara in grupos:
        g = sinais[mascara]
        if g.empty:
            continue
        print(f"    {rot:<28}{len(g):>8}{g['desloc_4'].median():>9.0f}"
              f"{g['desloc_8'].median():>9.0f}{g['desloc_fim_do_dia'].median():>13.0f}"
              f"{(g['desloc_8'] > 0).mean():>12.0%}")

    print("\n  Media (sensivel a cauda - onde uma estrategia de tendencia ganha):")
    print(f"    {'grupo':<28}{'+2h medio':>12}{'fim do dia medio':>20}")
    for rot, mascara in grupos:
        g = sinais[mascara]
        if g.empty:
            continue
        print(f"    {rot:<28}{g['desloc_8'].mean():>12.1f}{g['desloc_fim_do_dia'].mean():>20.1f}")


def main() -> int:
    cfg, pregao, bruto = carregar()
    direcao_da_abertura(pregao, bruto)
    sinais = sinais_com_ordem(cfg, pregao)
    vale_pular_o_primeiro(sinais)

    destino = Path(__file__).resolve().parent.parent / "reports" / "sinais_por_ordem.csv"
    sinais.to_csv(destino, index=False, encoding="utf-8")
    print(f"\n  Sinais salvos em: reports/{destino.name}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
