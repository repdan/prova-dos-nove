"""
Testes do motor de backtest.

O foco esta nas duas coisas que, se estiverem erradas, produzem um backtest
bonito e falso: o custo de transacao e a ordem das chamadas. Um engine que
esquece o spread ou que deixa o candle atual influenciar a decisao dele mesmo
nao da erro - ele da lucro.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterator

import pytest

from backtest.executor import ExecutorSimulado
from backtest.feed import DataFeed
from backtest.motor import Motor
from strategy.base import (Candle, DecisaoSaida, Direcao, Estrategia,
                           Posicao, Sinal)

INICIO = datetime(2024, 1, 2, 9, 15)


def candle(i: int, maxima: float, minima: float, fechamento: float,
           abertura: float | None = None, dia: int = 0,
           spread: float = 0.0) -> Candle:
    return Candle(
        tempo=INICIO + timedelta(days=dia, minutes=15 * i),
        abertura=abertura if abertura is not None else (maxima + minima) / 2,
        maxima=maxima, minima=minima, fechamento=fechamento,
        volume=1000, spread=spread,
    )


class FeedLista(DataFeed):
    """Feed de teste: entrega exatamente os candles que recebeu."""

    def __init__(self, candles: list[Candle]):
        self._candles = candles

    def __iter__(self) -> Iterator[Candle]:
        return iter(self._candles)


class EstrategiaRoteirizada(Estrategia):
    """Estrategia de teste que segue um roteiro fixo.

    Existe para isolar o motor: com a decisao pre-definida, qualquer diferenca
    no resultado vem do motor ou do executor, nunca da estrategia.
    """

    nome = "roteirizada"

    def __init__(self, entradas: dict[int, Sinal], saidas: dict[int, DecisaoSaida],
                 lote: float = 0.01, atr: float = 10.0):
        self.entradas = entradas
        self.saidas = saidas
        self.lote = lote
        self._atr = atr
        self.indice = -1
        self.ordem_das_chamadas: list[str] = []

    def on_candle(self, candle: Candle) -> Sinal:
        self.indice += 1
        self.ordem_das_chamadas.append(f"on_candle:{self.indice}")
        return self.entradas.get(self.indice, Sinal.NENHUM)

    def deve_sair(self, posicao: Posicao, candle: Candle) -> DecisaoSaida:
        # O motor chama deve_sair ANTES de on_candle, entao o indice aqui
        # ainda aponta para o candle anterior: por isso o +1.
        self.ordem_das_chamadas.append(f"deve_sair:{self.indice + 1}")
        return self.saidas.get(self.indice + 1, DecisaoSaida(sair=False))

    def contexto_atual(self) -> dict:
        return {"atr": self._atr}


def novo_executor(spread=4.0, slippage=0.5, comissao=0.0, valor_ponto=0.1275):
    return ExecutorSimulado(spread_padrao=spread, slippage=slippage,
                            comissao_por_lote=comissao,
                            valor_ponto_por_lote=valor_ponto)


# ------------------------------------------------------------------- custos

def test_custo_de_transacao_sai_sempre_contra_quem_opera():
    """Compra entra no caro e sai no barato; venda e o espelho.

    Preco de tela 100 nas duas pontas, spread 4 e slippage 0,5: a penalidade e
    de 2,5 por ponta. Um trade que nao anda um centavo tem que perder 5 pontos.
    """
    ex = novo_executor(spread=4.0, slippage=0.5)
    entrada = candle(0, 101, 99, 100)
    saida = candle(1, 101, 99, 100)

    for direcao in (Direcao.COMPRADO, Direcao.VENDIDO):
        ex.trades.clear()
        pos = ex.abrir(direcao, entrada, 0.01, {})
        ex.acompanhar(pos, saida)
        t = ex.fechar(pos, saida, "teste")

        assert t.resultado_bruto_pontos == pytest.approx(0.0)
        assert t.resultado_pontos == pytest.approx(-5.0), \
            f"{direcao.value} deveria perder o giro completo do spread"
        assert t.custo_pontos == pytest.approx(5.0)


def test_spread_do_candle_tem_prioridade_sobre_o_do_config():
    """O spread real varia; usar a media da abertura barateia o custo."""
    ex = novo_executor(spread=4.0, slippage=0.0)
    largo = candle(0, 101, 99, 100, spread=20.0)
    pos = ex.abrir(Direcao.COMPRADO, largo, 0.01, {})
    ex.acompanhar(pos, largo)
    t = ex.fechar(pos, largo, "teste")
    assert t.custo_pontos == pytest.approx(20.0), "ignorou o spread do candle"


def test_comissao_entra_no_resultado_em_pontos():
    ex = novo_executor(spread=0.0, slippage=0.0, comissao=1.275, valor_ponto=0.1275)
    c = candle(0, 101, 99, 100)
    pos = ex.abrir(Direcao.COMPRADO, c, 0.01, {})
    ex.acompanhar(pos, c)
    t = ex.fechar(pos, c, "teste")
    # 1.275 USD / 0.1275 USD por ponto = 10 pontos
    assert t.resultado_pontos == pytest.approx(-10.0)


def test_excursoes_registram_o_melhor_e_o_pior_do_trade():
    """A perda maxima por trade e a metrica que substitui o stop ausente."""
    ex = novo_executor(spread=0.0, slippage=0.0)
    pos = ex.abrir(Direcao.COMPRADO, candle(0, 100, 100, 100), 0.01, {})
    for c in [candle(1, 130, 95, 120), candle(2, 125, 70, 80), candle(3, 110, 105, 108)]:
        ex.acompanhar(pos, c)
    t = ex.fechar(pos, candle(4, 110, 105, 108), "teste")

    assert t.excursao_favoravel == pytest.approx(30.0)   # chegou a 130
    assert t.excursao_contraria == pytest.approx(30.0)   # chegou a 70


# -------------------------------------------------------------- ordem/motor

def test_saida_e_avaliada_antes_de_a_estrategia_absorver_o_candle():
    """A ordem que impede o candle de influenciar o canal que ele rompe."""
    e = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA}, saidas={})
    motor = Motor(e, novo_executor())
    motor.rodar(FeedLista([candle(i, 101, 99, 100) for i in range(4)]))

    # A partir do candle 1 (com posicao aberta) deve_sair sempre precede on_candle.
    for i in range(1, 4):
        pos_sair = e.ordem_das_chamadas.index(f"deve_sair:{i}")
        pos_entrar = e.ordem_das_chamadas.index(f"on_candle:{i}")
        assert pos_sair < pos_entrar, f"ordem invertida no candle {i}"


def test_sinal_com_posicao_aberta_e_contado_mas_nao_executado():
    e = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA, 1: Sinal.COMPRA,
                                        2: Sinal.VENDA}, saidas={})
    motor = Motor(e, novo_executor())
    r = motor.rodar(FeedLista([candle(i, 101, 99, 100) for i in range(4)]))

    assert r.sinais_gerados == 3
    assert r.sinais_ignorados_posicao_aberta == 2
    assert len(r.trades) == 0, "nenhuma saida foi roteirizada, nao pode haver trade"


def test_posicao_aberta_no_fim_da_base_nao_vira_trade():
    """Fechar no ultimo candle inventaria um encerramento que nao houve."""
    e = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA}, saidas={})
    motor = Motor(e, novo_executor())
    r = motor.rodar(FeedLista([candle(i, 101, 99, 100) for i in range(5)]))
    assert r.trades == []


def test_fechar_no_fim_do_pregao_encerra_na_virada_do_dia():
    e = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA}, saidas={})
    candles = [candle(0, 101, 99, 100, dia=0), candle(1, 101, 99, 100, dia=0),
               candle(0, 121, 119, 120, dia=1)]

    aberto = Motor(e, novo_executor(), fechar_no_fim_do_pregao=False)
    assert aberto.rodar(FeedLista(candles)).fechamentos_por_fim_de_pregao == 0

    e2 = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA}, saidas={})
    fechado = Motor(e2, novo_executor(), fechar_no_fim_do_pregao=True)
    r = fechado.rodar(FeedLista(candles))
    assert r.fechamentos_por_fim_de_pregao == 1
    assert r.trades[0].motivo_saida == "fim_do_pregao"
    # Fecha no ULTIMO candle do dia anterior, nao no primeiro do dia novo.
    assert r.trades[0].preco_saida_bruto == pytest.approx(100.0)


# ------------------------------------------------------ stop e desempate

def test_stop_catastrofico_desligado_por_padrao():
    e = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA}, saidas={}, atr=1.0)
    motor = Motor(e, novo_executor())
    r = motor.rodar(FeedLista([candle(0, 101, 99, 100), candle(1, 100, 1, 5),
                               candle(2, 100, 99, 99)]))
    assert r.stops_catastroficos == 0
    assert r.trades == [], "posicao nao deveria ter sido fechada"


def test_stop_catastrofico_dispara_no_nivel_calculado():
    e = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA}, saidas={}, atr=10.0)
    motor = Motor(e, novo_executor(spread=0.0, slippage=0.0),
                  stop_catastrofico_ativo=True, stop_catastrofico_atr=3.0)
    r = motor.rodar(FeedLista([candle(0, 101, 99, 100), candle(1, 100, 50, 60)]))

    assert r.stops_catastroficos == 1
    # Entrada em 100 (sem custo), stop a 3 x ATR(10) = 30 pontos abaixo.
    assert r.trades[0].preco_saida == pytest.approx(70.0)
    assert r.trades[0].motivo_saida == "stop_catastrofico"


def test_sem_resolvedor_o_empate_intrabar_vai_para_o_pior_caso():
    """Alvo e stop no mesmo candle, sem M5 para desempatar: assume o stop.

    Escolher o alvo aqui seria escolher a favor de quem opera - a forma mais
    silenciosa de um backtest inflar o proprio resultado.
    """
    saida_com_alvo = DecisaoSaida(sair=True, motivo="alvo_fibo", preco_sugerido=140.0)
    e = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA},
                              saidas={1: saida_com_alvo}, atr=10.0)
    motor = Motor(e, novo_executor(spread=0.0, slippage=0.0),
                  resolvedor=None, stop_catastrofico_ativo=True,
                  stop_catastrofico_atr=3.0)
    # O candle toca 140 (alvo) e 50 (abaixo do stop em 70).
    r = motor.rodar(FeedLista([candle(0, 101, 99, 100), candle(1, 150, 50, 60)]))

    assert r.trades[0].motivo_saida == "stop_catastrofico"
    assert r.trades[0].preco_saida == pytest.approx(70.0)


def test_resolvedor_decide_o_empate_pelo_que_veio_primeiro():
    class ResolvedorFalso:
        """Diz que o alvo veio antes do stop."""
        def qual_veio_primeiro(self, *a, **kw):
            return "a"

    saida_com_alvo = DecisaoSaida(sair=True, motivo="alvo_fibo", preco_sugerido=140.0)
    e = EstrategiaRoteirizada(entradas={0: Sinal.COMPRA},
                              saidas={1: saida_com_alvo}, atr=10.0)
    motor = Motor(e, novo_executor(spread=0.0, slippage=0.0),
                  resolvedor=ResolvedorFalso(), stop_catastrofico_ativo=True,
                  stop_catastrofico_atr=3.0)
    r = motor.rodar(FeedLista([candle(0, 101, 99, 100), candle(1, 150, 50, 60)]))

    assert r.desempates_intrabar == 1
    assert r.trades[0].motivo_saida == "alvo_fibo"
    assert r.trades[0].preco_saida == pytest.approx(140.0)


# ------------------------------------------------------------------ metricas

def test_metricas_batem_com_trades_construidos_a_mao():
    from backtest import metricas as met

    ex = novo_executor(spread=0.0, slippage=0.0)
    # Dois ganhos de 10 e uma perda de 20 -> fator de lucro exatamente 1.0
    for entrada, saida in [(100, 110), (100, 110), (100, 80)]:
        pos = ex.abrir(Direcao.COMPRADO, candle(0, entrada, entrada, entrada), 0.01, {})
        c = candle(1, saida, saida, saida)
        ex.acompanhar(pos, c)
        ex.fechar(pos, c, "teste")

    import pandas as pd
    m = met.calcular(pd.DataFrame([t.como_dict() for t in ex.trades]))

    assert m.trades == 3
    assert m.vencedores == 2 and m.perdedores == 1
    assert m.taxa_acerto == pytest.approx(2 / 3)
    assert m.resultado_total_pontos == pytest.approx(0.0)
    assert m.fator_lucro == pytest.approx(1.0)
    assert m.maior_perda == pytest.approx(-20.0)
    assert m.drawdown_maximo_pontos == pytest.approx(20.0)
