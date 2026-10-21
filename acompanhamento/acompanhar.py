"""
Acompanhamento das duas pistas, com as regras CONGELADAS (ver regras_congeladas.md).

    .venv/Scripts/python.exe -m acompanhamento.acompanhar              # desde o inicio oficial
    .venv/Scripts/python.exe -m acompanhamento.acompanhar 2026-09-01   # validacao no passado

So LE dados do MetaTrader (nenhuma ordem e enviada). Baixa o M1 recente, monta
os dias exatamente como no backtest, roda as estrategias congeladas e:
  - grava todos os trades desde o inicio em acompanhamento/trades_<pista>.csv;
  - compara o acumulado com a faixa esperada pelo backtest;
  - mostra o painel de hoje da pista 1 (canal e grade da abertura de NY), para
    acompanhar no grafico.
O dia em andamento nao entra no placar: so pregoes ja encerrados contam.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analises.coletar_m1_indices import montar_dias                     # noqa: E402
from analises.grade_tempo_grafico import reamostrar                   # noqa: E402
from configuracao import Config                                         # noqa: E402
from data import coleta                                                 # noqa: E402
from data.mt5_conexao import conectar, desconectar                      # noqa: E402
from strategy.grade import Custos, ParametrosGrade, canal_de_abertura, simular  # noqa: E402
from strategy.ichimoku import ParametrosIchimoku, simular_ichimoku      # noqa: E402

INICIO_OFICIAL = date(2026, 10, 26)       # primeira segunda-feira depois de congelar
PASTA = Path(__file__).resolve().parent
TFS = {"M15": 15, "M30": 30}

# ------------------------------------------------------------- regras congeladas
GRADE_OURO = ParametrosGrade(tendencia="neutra", max_stops_dia=2, take_niveis=1.5,
                                 velas_minimas=1, velas_maximas=1, largura_minima=0.0,
                                 usar_vela_gigante=False)
CUSTO_OURO = Custos(0.02, 0.001, 0.21)
CUSTO_USDJPY = Custos(0.0008, 0.1 / 628.79)


@dataclass(frozen=True)
class Pista:
    nome: str
    descricao: str
    mercado: str
    tipo: str                    # "grade" | "ichimoku"
    tf: str
    esperado_r: float            # R medio por trade, liquido, 2022-2026 no backtest
    desvio_r: float
    trades_ano: float
    params: object = None
    abertura: tuple | None = None
    custos: Custos = field(default_factory=lambda: CUSTO_OURO)
    ponto: float = 0.01


PISTAS = [
    Pista("P1-A", "Grade ouro, abertura NY, M15, 1a vela, gestao semanal dom-qua",
          "XAUUSD", "grade", "M15", 0.034, 0.96, 117,
          replace(GRADE_OURO, gestao_semanal=True, dias_semana=(0, 1, 2)), (16, 30)),
    Pista("P1-B", "Grade ouro, abertura NY, M30, 1a vela, gestao diaria",
          "XAUUSD", "grade", "M30", 0.025, 0.81, 277, GRADE_OURO, (16, 30)),
    Pista("P2-USDJPY", "Ichimoku classico, USDJPY M15", "USDJPY", "ichimoku", "M15",
          0.107, 3.26, 762, ParametrosIchimoku(), None, CUSTO_USDJPY, 0.001),
    Pista("P2-ouro", "Ichimoku classico, ouro M15", "XAUUSD", "ichimoku", "M15",
          0.014, 2.77, 774, ParametrosIchimoku()),
]


# ------------------------------------------------------------------- dados
def baixar(simbolo: str, desde: date) -> pd.DataFrame:
    mt5.symbol_select(simbolo, True)
    bruto = coleta.coletar_candles(simbolo, "M1", (desde - timedelta(days=45)).isoformat())
    if simbolo == "XAUUSD":
        return montar_dias(bruto, pausa_h=0.75, quantil_tipico=0.9)
    return montar_dias(bruto, pausa_h=0.75, quantil_tipico=0.9)


def preparar(pista: Pista, m1: pd.DataFrame) -> pd.DataFrame:
    d = m1.sort_values("tempo_ativo").reset_index(drop=True)
    if pista.abertura is not None:
        h, mi = pista.abertura
        ts = d["tempo_servidor"]
        d = d[(ts.dt.hour > h) | ((ts.dt.hour == h) & (ts.dt.minute >= mi))].reset_index(drop=True)
    d = reamostrar(d, TFS[pista.tf])
    if pista.tipo == "ichimoku":
        d["dia"] = d["tempo_ativo"].dt.date
    return d


def rodar(pista: Pista, d: pd.DataFrame) -> pd.DataFrame:
    if pista.tipo == "grade":
        return simular(d, pista.params, pista.custos, pista.ponto)
    return simular_ichimoku(d, pista.params, pista.custos, pista.ponto)


# ------------------------------------------------------------------- relatorio
def placar(pista: Pista, t: pd.DataFrame) -> str:
    n = len(t)
    if n == 0:
        return f"  {pista.nome:<10} sem trades ainda"
    soma = t["r"].sum()
    esperado = pista.esperado_r * n
    faixa = 2 * pista.desvio_r * np.sqrt(n)
    if soma < esperado - faixa:
        estado = "ABAIXO do esperado (pior que o backtest, alem do acaso)"
    elif soma > esperado + faixa:
        estado = "ACIMA do esperado"
    else:
        estado = "dentro do esperado"
    return (f"  {pista.nome:<10}{n:>6} trades  acerto {(t['resultado'] > 0).mean():>4.0%}  "
            f"acumulado {soma:+7.2f}R  esperado {esperado:+6.2f}R +-{faixa:5.2f}  -> {estado}")


def painel_ny(pista: Pista, d: pd.DataFrame, hoje) -> None:
    """Canal e grade do dia corrente na abertura de NY, para acompanhar no grafico."""
    dias = sorted(d["tempo_ativo"].dt.date.unique())
    if len(dias) < 2 or dias[-1] != hoje:
        print("    a abertura de NY de hoje ainda nao aconteceu (16:30 no horario do servidor).")
        return
    bloco = d[d["tempo_ativo"].dt.date == hoje].reset_index(drop=True)
    ant = d[d["tempo_ativo"].dt.date == dias[-2]]
    canal = canal_de_abertura(bloco, float((ant["maxima"] - ant["minima"]).median()), pista.params)
    if canal is None:
        print("    canal de hoje ainda nao formado.")
        return
    base, w, _ = canal
    preco = float(bloco["fechamento"].iloc[-1])
    print(f"    canal de hoje: {base:.2f} a {base + w:.2f} (largura {w:.2f} USD); "
          f"ultimo fechamento {preco:.2f}")
    niveis = "  ".join(f"{base + k * w:.2f}" for k in range(-3, 5))
    print(f"    grade (niveis de {w:.2f}): {niveis}")


def main() -> int:
    inicio = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else INICIO_OFICIAL
    conectar(Config.carregar(mercado="XAUUSD"))
    try:
        agora = datetime.fromtimestamp(mt5.symbol_info_tick("XAUUSD").time, tz=timezone.utc).replace(tzinfo=None)
        dados = {s: baixar(s, inicio) for s in {p.mercado for p in PISTAS}}
    finally:
        desconectar()

    print(f"\n  ACOMPANHAMENTO DAS PISTAS - desde {inicio:%d/%m/%Y}  (servidor agora: {agora:%d/%m %H:%M})")
    print("  " + "-" * 110)
    for p in PISTAS:
        d = preparar(p, dados[p.mercado])
        # O bloco em andamento (ultima vela ha menos de 2 h) nao conta no placar.
        ultimo = d["tempo_ativo"].dt.date.max()
        em_andamento = (agora - dados[p.mercado]["tempo_servidor"].max()) < pd.Timedelta(hours=2)
        t = rodar(p, d)
        if not t.empty:
            t = t[pd.to_datetime(t["tempo_entrada"]).dt.date >= inicio]
            if em_andamento:
                t = t[pd.to_datetime(t["tempo_entrada"]).dt.date < ultimo]
        t.to_csv(PASTA / f"trades_{p.nome}.csv", index=False, encoding="utf-8")
        print(placar(p, t))
        if p.nome == "P1-A":
            painel_ny(p, d, ultimo if em_andamento else None)
    print("\n  Trades gravados em acompanhamento/trades_<pista>.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
