"""
Metricas de desempenho.

Duas escolhas que mudam a leitura dos numeros:

1. Tudo e calculado sobre o resultado LIQUIDO, ja com spread, derrapagem e
   comissao descontados. Metrica sobre resultado bruto e propaganda.

2. Sharpe sai do retorno DIARIO do patrimonio, nao do resultado por trade.
   Sharpe por trade sobe artificialmente quando a estrategia opera pouco, e
   compararia mal estrategias com frequencias diferentes - que e exatamente o
   que a Etapa 4 vai fazer entre os quatro modos de saida.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

PREGOES_POR_ANO = 250


@dataclass
class Metricas:
    trades: int = 0
    vencedores: int = 0
    perdedores: int = 0
    taxa_acerto: float = 0.0

    resultado_total_pontos: float = 0.0
    resultado_total_dinheiro: float = 0.0
    custo_total_pontos: float = 0.0
    resultado_bruto_pontos: float = 0.0

    ganho_medio: float = 0.0
    perda_media: float = 0.0
    expectativa_por_trade: float = 0.0
    fator_lucro: float = 0.0

    drawdown_maximo_pontos: float = 0.0
    drawdown_maximo_pct: float = 0.0
    sharpe_anualizado: float = 0.0

    maior_ganho: float = 0.0
    maior_perda: float = 0.0
    pior_excursao_contraria: float = 0.0
    candles_medios_por_trade: float = 0.0

    dias_operados: int = 0
    trades_por_dia: float = 0.0

    def como_dict(self) -> dict:
        return asdict(self)


def calcular(trades: pd.DataFrame, capital_inicial: float = 10_000.0) -> Metricas:
    m = Metricas()
    if trades is None or trades.empty:
        return m

    r = trades["resultado_pontos"]
    m.trades = len(trades)
    m.vencedores = int((r > 0).sum())
    m.perdedores = int((r < 0).sum())
    m.taxa_acerto = m.vencedores / m.trades

    m.resultado_total_pontos = float(r.sum())
    m.resultado_total_dinheiro = float(trades["resultado_dinheiro"].sum())
    m.custo_total_pontos = float(trades["custo_pontos"].sum())
    m.resultado_bruto_pontos = float(trades["resultado_bruto_pontos"].sum())

    ganhos = r[r > 0]
    perdas = r[r < 0]
    m.ganho_medio = float(ganhos.mean()) if len(ganhos) else 0.0
    m.perda_media = float(perdas.mean()) if len(perdas) else 0.0
    m.expectativa_por_trade = float(r.mean())

    soma_perdas = float(perdas.sum())
    # Fator de lucro = quanto se ganha por unidade perdida. Sem nenhuma perda
    # a divisao seria por zero; infinito e a leitura honesta desse caso raro.
    m.fator_lucro = (float(ganhos.sum()) / abs(soma_perdas)) if soma_perdas else float("inf")

    m.maior_ganho = float(r.max())
    m.maior_perda = float(r.min())
    if "excursao_contraria" in trades:
        m.pior_excursao_contraria = float(trades["excursao_contraria"].max())
    m.candles_medios_por_trade = float(trades["candles_no_trade"].mean())

    # --- drawdown sobre a curva de patrimonio em pontos ---
    curva = r.cumsum()
    pico = curva.cummax()
    rebaixamento = curva - pico
    m.drawdown_maximo_pontos = float(-rebaixamento.min())

    # --- serie diaria, para Sharpe e drawdown percentual ---
    diario = _serie_diaria(trades)
    m.dias_operados = int(len(diario))
    m.trades_por_dia = m.trades / m.dias_operados if m.dias_operados else 0.0

    if m.dias_operados > 1:
        patrimonio = capital_inicial + diario["resultado_dinheiro"].cumsum()
        retornos = patrimonio.pct_change().dropna()
        desvio = float(retornos.std())
        if desvio > 0:
            m.sharpe_anualizado = float(retornos.mean() / desvio * np.sqrt(PREGOES_POR_ANO))
        pico_p = patrimonio.cummax()
        m.drawdown_maximo_pct = float(-((patrimonio - pico_p) / pico_p).min())

    return m


def _serie_diaria(trades: pd.DataFrame) -> pd.DataFrame:
    t = trades.copy()
    t["dia"] = pd.to_datetime(t["tempo_saida"]).dt.date
    return t.groupby("dia").agg(resultado_pontos=("resultado_pontos", "sum"),
                               resultado_dinheiro=("resultado_dinheiro", "sum"),
                               trades=("resultado_pontos", "size"))


def por_recorte(trades: pd.DataFrame, coluna: str,
                minimo: int = 20) -> pd.DataFrame:
    """Desempenho agrupado por uma coluna qualquer do contexto.

    Serve para as distribuicoes que o projeto pede - por horario, por dia da
    semana - e tambem para qualquer feature que a Etapa 4 queira inspecionar.
    Grupos pequenos sao descartados: taxa de acerto sobre 5 trades e ruido
    apresentado como resultado.
    """
    if trades.empty or coluna not in trades:
        return pd.DataFrame()

    g = trades.groupby(coluna).agg(
        trades=("resultado_pontos", "size"),
        total=("resultado_pontos", "sum"),
        media=("resultado_pontos", "mean"),
        acerto=("resultado_pontos", lambda s: (s > 0).mean()),
        pior=("resultado_pontos", "min"),
    )
    g = g[g["trades"] >= minimo]
    return g.sort_values("total", ascending=False)


def curva_de_capital(trades: pd.DataFrame,
                     capital_inicial: float = 10_000.0) -> pd.DataFrame:
    """Patrimonio dia a dia - base dos graficos da Etapa 5."""
    if trades.empty:
        return pd.DataFrame()
    d = _serie_diaria(trades).reset_index()
    d["patrimonio"] = capital_inicial + d["resultado_dinheiro"].cumsum()
    d["pontos_acumulados"] = d["resultado_pontos"].cumsum()
    d["pico"] = d["patrimonio"].cummax()
    d["rebaixamento_pct"] = (d["patrimonio"] - d["pico"]) / d["pico"]
    return d
