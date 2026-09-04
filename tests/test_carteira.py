"""
Testes do backtest de carteira.

O foco esta no dimensionamento por risco. E a peca que substitui o lote fixo, e
um erro aqui nao aparece como bug - aparece como uma curva de patrimonio bonita
construida sobre posicoes que ninguem conseguiria abrir.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from backtest.carteira import BacktestCarteira, Especificacao
from strategy.base import Direcao
from strategy.tendencia_diaria import TendenciaDiaria


def spec(usd_por_ponto=1.0, minimo=0.01, passo=0.01, spread=0.0) -> Especificacao:
    return Especificacao(nome="TESTE", usd_por_ponto_lote=usd_por_ponto,
                         spread=spread, lote_minimo=minimo, passo_lote=passo)


def backtest(**kw) -> BacktestCarteira:
    padrao = dict(criar_estrategia=lambda: TendenciaDiaria(20, 10),
                  especificacoes={"TESTE": spec()}, capital_inicial=10_000,
                  risco_por_trade=0.01)
    return BacktestCarteira(**{**padrao, **kw})


# ------------------------------------------------------- dimensionamento

def test_tamanho_da_posicao_arrisca_exatamente_o_planejado():
    """Conta de 10.000, risco de 1% = 100 USD. Stop a 50 pontos, 1 USD por
    ponto por lote: cabem 2 lotes, que perdem exatamente 100 se o stop bater."""
    bt = backtest()
    lote, abaixo = bt._tamanho(10_000, distancia_stop=50, spec=spec(usd_por_ponto=1.0))
    assert lote == pytest.approx(2.0)
    assert not abaixo
    assert lote * 50 * 1.0 == pytest.approx(100.0)


def test_mercado_mais_volatil_entra_menor():
    """O ponto do dimensionamento por risco: todos arriscam o mesmo."""
    bt = backtest()
    calmo, _ = bt._tamanho(10_000, distancia_stop=10, spec=spec())
    volatil, _ = bt._tamanho(10_000, distancia_stop=100, spec=spec())
    assert volatil == pytest.approx(calmo / 10)
    # E os dois arriscam os mesmos 100 USD.
    assert calmo * 10 == pytest.approx(volatil * 100)


def test_lote_e_arredondado_para_baixo_no_passo_da_corretora():
    """Arredondar para cima arriscaria mais que o planejado."""
    bt = backtest()
    lote, _ = bt._tamanho(10_000, distancia_stop=33, spec=spec(passo=0.01))
    # 100 / 33 = 3.0303... -> tem que virar 3.03, nao 3.04
    assert lote == pytest.approx(3.03)


def test_conta_pequena_e_sinalizada_quando_nao_cabe_o_lote_minimo():
    """A restricao que decide se uma conta consegue rodar a estrategia."""
    bt = backtest()
    # Conta de 200 USD, risco 1% = 2 USD. Stop de 500 pontos a 1 USD/ponto
    # exigiria 0.004 lote - abaixo do minimo de 0.01.
    lote, abaixo = bt._tamanho(200, distancia_stop=500, spec=spec(minimo=0.01))
    assert abaixo, "deveria sinalizar que o tamanho ficou abaixo do minimo"
    assert lote == pytest.approx(0.01), "com aceitar_lote_minimo, opera o minimo"


def test_pular_o_trade_quando_o_lote_minimo_estoura_o_risco():
    bt = backtest(aceitar_lote_minimo=False)
    lote, abaixo = bt._tamanho(200, distancia_stop=500, spec=spec(minimo=0.01))
    assert abaixo and lote == 0.0


def test_lote_minimo_forcado_arrisca_mais_do_que_o_planejado():
    """A conta pequena nao arrisca 1% - arrisca o que o lote minimo impuser.

    Este teste existe para o numero nao passar despercebido: com 200 USD e
    stop de 500 pontos, o lote minimo arrisca 5 USD, que sao 2.5% da conta e
    nao 1%.
    """
    bt = backtest()
    lote, abaixo = bt._tamanho(200, distancia_stop=500, spec=spec(minimo=0.01))
    risco_real = lote * 500 * 1.0
    assert abaixo
    assert risco_real == pytest.approx(5.0)
    assert risco_real / 200 == pytest.approx(0.025)


# -------------------------------------------------------------- execucao

def serie(precos: list[float], inicio="2020-01-01") -> pd.DataFrame:
    d0 = datetime.fromisoformat(inicio)
    return pd.DataFrame([{
        "tempo_ativo": d0 + timedelta(days=i), "abertura": p,
        "maxima": p + 1, "minima": p - 1, "fechamento": p, "volume_ticks": 100,
    } for i, p in enumerate(precos)])


def test_stop_com_gap_e_executado_na_abertura():
    """Mesma regra do engine intradiario: stop garante execucao, nao preco."""
    bt = backtest()
    pos = {"direcao": Direcao.COMPRADO, "preco": 100.0, "nivel_stop": 90.0,
           "lote": 1.0, "atr": 5.0, "entrada": date(2020, 1, 1),
           "abaixo_minimo": False, "risco": 100.0}
    from strategy.base import Candle
    com_gap = Candle(tempo=datetime(2020, 1, 2), abertura=80.0, maxima=85.0,
                     minima=78.0, fechamento=82.0, volume=100)
    fechou, preco, motivo = bt._avaliar_saida(TendenciaDiaria(20, 10), pos, com_gap)
    assert fechou and motivo == "stop"
    assert preco == pytest.approx(80.0), "ignorou o gap e assumiu o nivel"


def test_carteira_nao_abre_duas_posicoes_no_mesmo_mercado():
    dados = {"TESTE": serie([100 + i for i in range(120)])}
    res = backtest(especificacoes={"TESTE": spec()}).rodar(dados)
    q = res.quadro
    if not q.empty:
        sobrepostas = q.sort_values("entrada")
        anterior_saida = None
        for l in sobrepostas.itertuples():
            if anterior_saida is not None:
                assert l.entrada >= anterior_saida, "posicoes sobrepostas"
            anterior_saida = l.saida


def test_limite_de_posicoes_simultaneas_e_respeitado():
    dados = {n: serie([100 + i for i in range(120)]) for n in ("A", "B", "C")}
    specs = {n: spec() for n in dados}
    bt = BacktestCarteira(lambda: TendenciaDiaria(20, 10), specs,
                          capital_inicial=10_000, risco_por_trade=0.01,
                          max_posicoes=2)
    res = bt.rodar(dados)
    assert res.patrimonio["posicoes"].max() <= 2
