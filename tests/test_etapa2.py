"""
Testes da estrategia de rompimento de canal.

Os candles aqui sao construidos a mao, com numeros escolhidos para que cada
teste tenha uma unica resposta certa. Serie aleatoria nao serve: ela esconde
justamente os erros que importam (look-ahead, regra de entrada frouxa).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from strategy.base import Candle, Direcao, Posicao, Sinal
from strategy.canal_rompimento import CanalRompimento, ModoSaida

INICIO = datetime(2024, 1, 2, 9, 15)
PERIODO = 20


def candle(indice: int, maxima: float, minima: float,
           fechamento: float | None = None) -> Candle:
    return Candle(
        tempo=INICIO + timedelta(minutes=15 * indice),
        abertura=(maxima + minima) / 2,
        maxima=maxima,
        minima=minima,
        fechamento=fechamento if fechamento is not None else (maxima + minima) / 2,
        volume=1000,
    )


def nova(modo: str = "stop_gain", **kw) -> CanalRompimento:
    padrao = dict(periodo_canal=PERIODO, modo_saida=modo, lote=0.01)
    return CanalRompimento(**{**padrao, **kw})


def encher_canal(estrategia: CanalRompimento, maxima=100.0, minima=90.0,
                 fechamento=95.0, quantos=PERIODO + 1) -> int:
    """Alimenta candles estaveis ate a estrategia poder decidir.

    Sao PERIODO + 1 candles, nao PERIODO: os primeiros 20 enchem a janela das
    medias, e o 21o e o primeiro que chega a ser comparado contra um canal ja
    formado - so a partir dai existe "candle anterior" com posicao conhecida,
    que e o que a regra de entrada exige.
    """
    for i in range(quantos):
        estrategia.on_candle(candle(i, maxima, minima, fechamento))
    return quantos


# --------------------------------------------------------------- fundamentos

def test_nao_opera_antes_de_formar_o_canal():
    e = nova()
    for i in range(PERIODO - 1):
        assert e.on_candle(candle(i, 100, 90, 95)) is Sinal.NENHUM
    assert not e.pronta(), "estrategia nao deveria estar pronta com janela incompleta"


def test_canal_e_a_media_das_maximas_e_das_minimas():
    e = nova()
    encher_canal(e)
    ctx = e.contexto_atual()
    assert ctx["canal_superior"] == pytest.approx(100.0)
    assert ctx["canal_inferior"] == pytest.approx(90.0)
    assert ctx["largura_canal"] == pytest.approx(10.0)


# ------------------------------------------------------- ausencia de look-ahead

def test_o_candle_que_rompe_nao_entra_no_canal_que_ele_rompe():
    """O teste central contra look-ahead bias.

    Canal formado: (100, 90). O candle seguinte fecha em 101 - rompe 100.
    Mas a maxima dele e 140: se ele fosse incluido no proprio canal, a banda
    superior subiria para (19*100 + 140)/20 = 102, e 101 nao romperia nada.

    Portanto: sinal de COMPRA prova que o canal foi lido antes de absorver o
    candle. Sinal NENHUM denunciaria contaminacao pelo futuro.
    """
    e = nova()
    n = encher_canal(e)
    assert e.on_candle(candle(n, maxima=140, minima=95, fechamento=101)) is Sinal.COMPRA


def test_o_canal_se_atualiza_depois_do_candle():
    """Complemento do teste acima: o candle precisa entrar no canal seguinte."""
    e = nova()
    n = encher_canal(e)
    largura_antes = e.contexto_atual()["canal_superior"]
    e.on_candle(candle(n, maxima=140, minima=95, fechamento=101))
    assert e.contexto_atual()["canal_superior"] > largura_antes


# ------------------------------------------------------- regra dura de entrada

def test_rompimento_para_cima_gera_compra_e_para_baixo_gera_venda():
    para_cima = nova()
    n = encher_canal(para_cima)
    assert para_cima.on_candle(candle(n, 102, 95, 101)) is Sinal.COMPRA

    para_baixo = nova()
    n = encher_canal(para_baixo)
    assert para_baixo.on_candle(candle(n, 95, 88, 89)) is Sinal.VENDA


def test_preco_que_ja_estava_fora_do_canal_nao_gera_entrada():
    """A regra dura do projeto: so vale rompimento de dentro para fora."""
    e = nova()
    n = encher_canal(e)

    assert e.on_candle(candle(n, 102, 95, 101)) is Sinal.COMPRA      # rompeu
    # Continua acima do canal por varios candles: nenhum novo sinal.
    for k in range(1, 6):
        sinal = e.on_candle(candle(n + k, 108, 100, 106))
        assert sinal is Sinal.NENHUM, f"gerou sinal repetido no candle {k} fora do canal"


def test_precisa_voltar_para_dentro_antes_de_romper_de_novo():
    e = nova()
    n = encher_canal(e)
    assert e.on_candle(candle(n, 102, 95, 101)) is Sinal.COMPRA

    # Volta para dentro do canal por alguns candles...
    for k in range(1, 6):
        e.on_candle(candle(n + k, 99, 92, 95))
    # ...e so entao um novo rompimento vale.
    ctx = e.contexto_atual()
    rompe = ctx["canal_superior"] + 1
    assert e.on_candle(candle(n + 6, rompe + 2, 95, rompe)) is Sinal.COMPRA


def test_modo_extremo_aceita_rompimento_por_pavio():
    """Com preco_referencia='extremo' o pavio basta; com 'fechamento', nao."""
    por_fechamento = nova(preco_referencia="fechamento")
    n = encher_canal(por_fechamento)
    assert por_fechamento.on_candle(candle(n, 105, 95, 99)) is Sinal.NENHUM

    por_extremo = nova(preco_referencia="extremo")
    n = encher_canal(por_extremo)
    assert por_extremo.on_candle(candle(n, 105, 95, 99)) is Sinal.COMPRA


# ------------------------------------------------------------------- saidas

def posicao_comprada(preco=101.0, largura=10.0) -> Posicao:
    return Posicao(direcao=Direcao.COMPRADO, preco_entrada=preco,
                   tempo_entrada=INICIO, lote=0.01,
                   contexto_entrada={"largura_canal": largura})


def test_stop_gain_sai_ao_romper_a_media_oposta():
    e = nova("stop_gain")
    n = encher_canal(e)
    pos = posicao_comprada()

    # Ainda dentro do canal: mantem.
    assert not e.deve_sair(pos, candle(n, 99, 92, 95)).sair

    e2 = nova("stop_gain")
    n2 = encher_canal(e2)
    d = e2.deve_sair(pos, candle(n2, 95, 85, 89))   # fecha abaixo da banda inferior
    assert d.sair and d.motivo == "rompimento_media_oposta"


def test_trailing_nunca_afrouxa():
    """O nivel do trailing so anda a favor da posicao, mesmo se o canal recuar."""
    e = nova("trailing")
    n = encher_canal(e)
    pos = posicao_comprada()

    e.deve_sair(pos, candle(n, 99, 92, 95))
    nivel_inicial = pos.estado["nivel_trailing"]

    # Canal sobe -> o nivel acompanha.
    for k in range(1, PERIODO + 1):
        e.on_candle(candle(n + k, 120, 110, 115))
    e.deve_sair(pos, candle(n + PERIODO + 1, 121, 112, 118))
    nivel_alto = pos.estado["nivel_trailing"]
    assert nivel_alto > nivel_inicial

    # Canal desce -> o nivel NAO devolve o que ja travou.
    for k in range(1, PERIODO + 1):
        e.on_candle(candle(n + PERIODO + 1 + k, 100, 90, 95))
    e.deve_sair(pos, candle(n + 2 * PERIODO + 2, 99, 92, 95))
    assert pos.estado["nivel_trailing"] == nivel_alto, "o trailing afrouxou"


def test_fibo_usa_a_largura_da_entrada_e_sai_no_alvo_exato():
    e = nova("fibo_expansion", fibo_nivel=2.0)
    n = encher_canal(e)
    pos = posicao_comprada(preco=101.0, largura=10.0)
    alvo = 101.0 + 2.0 * 10.0          # 121

    # Candle que chega perto mas nao encosta: mantem.
    assert not e.deve_sair(pos, candle(n, 120.9, 110, 118)).sair

    # Candle que toca o alvo: sai NO ALVO, nao no fechamento.
    d = e.deve_sair(pos, candle(n + 1, 125, 118, 119))
    assert d.sair and d.motivo == "alvo_fibo"
    assert d.preco_sugerido == pytest.approx(alvo)


def test_fibo_ainda_tem_a_saida_base_como_stop():
    """Sem isso, um trade perdedor com alvo de Fibonacci nunca fecharia."""
    e = nova("fibo_expansion")
    n = encher_canal(e)
    pos = posicao_comprada()
    d = e.deve_sair(pos, candle(n, 95, 85, 89))
    assert d.sair and d.motivo == "rompimento_media_oposta"


def test_ml_sem_modelo_falha_com_mensagem_util():
    """A ordem de duas passadas da Etapa 4 precisa ser impossivel de esquecer."""
    e = nova("ml_probabilidade")
    n = encher_canal(e)
    with pytest.raises(RuntimeError, match="duas passadas"):
        e.deve_sair(posicao_comprada(), candle(n, 99, 92, 95))


def test_ml_antecipa_a_saida_mas_nao_a_prolonga():
    baixa = nova("ml_probabilidade", ml_limiar_saida=0.5,
                 prever_probabilidade=lambda ctx: 0.10)
    n = encher_canal(baixa)
    d = baixa.deve_sair(posicao_comprada(), candle(n, 99, 92, 95))
    assert d.sair and d.motivo == "ml_probabilidade_baixa"

    # Probabilidade alta nao segura uma posicao que rompeu a media oposta.
    alta = nova("ml_probabilidade", ml_limiar_saida=0.5,
                prever_probabilidade=lambda ctx: 0.99)
    n = encher_canal(alta)
    d = alta.deve_sair(posicao_comprada(), candle(n, 95, 85, 89))
    assert d.sair and d.motivo == "rompimento_media_oposta"


# ----------------------------------------------------------- canal donchian

def test_donchian_usa_extremos_e_nao_medias():
    e = nova(tipo_canal="donchian")
    for i in range(PERIODO - 1):
        e.on_candle(candle(i, 100, 90, 95))
    e.on_candle(candle(PERIODO - 1, 130, 70, 95))   # um candle bem mais amplo

    ctx = e.contexto_atual()
    assert ctx["canal_superior"] == pytest.approx(130.0)  # maior maxima
    assert ctx["canal_inferior"] == pytest.approx(70.0)   # menor minima


def test_tipo_de_canal_invalido_falha_na_criacao():
    with pytest.raises(ValueError, match="tipo_canal"):
        nova(tipo_canal="bollinger")
