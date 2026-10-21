"""
Testes da grade "so gap".

Dia sintetico: fechamento anterior L, abertura acima (gap de alta). Primeira
vela 1050-1100 -> B = 1050, w = 50; NR [1050,1100], ZR [1000,1050].
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from strategy.grade import Custos, ParametrosGrade
from strategy.grade_gap import ParametrosGap, simular_dia_gap
from tests.test_grade import dia

SEM = Custos(slippage=0.0, comissao_pontos=0.0, spread_forcado=0.0)
P = ParametrosGrade(velas_minimas=1, velas_maximas=1, largura_minima=0.0, usar_vela_gigante=False,
                      sem_entrada_antes_do_fim_min=0, take_niveis=1.5, max_stops_dia=2,
                      parar_no_take=False)
G = ParametrosGap()
ABRE = (1080, 1100, 1050, 1060)


def rodar(velas, fech_ant=900.0, p=P, g=G):
    return simular_dia_gap(dia(velas), fech_ant, 10.0, p, g, SEM)


def test_entrada_agressiva_na_zn_com_alvo_no_fechamento_do_gap():
    velas = [ABRE, (1060, 1062, 1035, 1040),     # fechou na ZR: vende
             (1040, 1041, 950, 960), (960, 962, 900, 905), (905, 910, 902, 906)]
    t = rodar(velas)
    assert t[0].tipo == "fecha_gap_zn" and t[0].direcao == -1
    assert t[0].stop_inicial == 1100 and t[0].take == 900
    assert t[0].motivo == "take"


def test_rompeu_a_linha_busca_o_tamanho_do_gap():
    """Gap de 180 (1080 - 900). Fechou abaixo de 900: vende, alvo 900 - 180."""
    velas = [ABRE, (1060, 1062, 1035, 1040), (1040, 1041, 950, 960),
             (960, 962, 880, 890), (890, 892, 700, 710)]
    t = rodar(velas)
    cont = [x for x in t if x.tipo == "continuacao_gap"][0]
    assert cont.preco_entrada == 890 and cont.stop_inicial == 950
    assert cont.take == pytest.approx(720) and cont.motivo == "take"


def test_tocou_e_voltou_vira_grade_cru():
    g = replace(G, operar_preenchimento=False)
    velas = [ABRE, (1060, 1062, 1035, 1040), (1040, 1041, 895, 960),  # toca 900 e volta
             (960, 1010, 955, 1005), (1005, 1060, 1000, 1055), (1055, 1056, 1050, 1052)]
    t = rodar(velas, g=g)
    assert t and all(x.tipo not in ("fecha_gap", "fecha_gap_zn", "continuacao_gap") for x in t)


def test_sem_espaco_ate_a_linha_nao_entra():
    """L = 1010: caminho de 30 pontos contra risco de 60 - nao vale o trade."""
    velas = [ABRE, (1060, 1062, 1035, 1040), (1040, 1045, 1030, 1035)]
    assert rodar(velas, fech_ant=1010.0) == []


def test_na_fase_de_gap_nao_opera_a_favor_do_gap():
    velas = [ABRE, (1060, 1130, 1058, 1120), (1120, 1125, 1115, 1121)]
    assert rodar(velas) == []
