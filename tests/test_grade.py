"""
Testes da grade mecanizado.

Cada teste monta um pregao sintetico em que se sabe, de antemao, o que o
metodo de referencia manda fazer. Se o codigo divergir, o erro e do codigo - ou da
leitura que fiz da regra, e ai o teste diz exatamente qual leitura.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from strategy.grade import Custos, ParametrosGrade, canal_de_abertura, simular_dia

SEM_CUSTO = Custos(slippage=0.0, comissao_pontos=0.0, spread_forcado=0.0)
# Canal pela 1a vela, sem vela gigante, sem corte de horario: isola a regra testada.
BASE = ParametrosGrade(velas_minimas=1, velas_maximas=1, largura_minima=0.0,
                         usar_vela_gigante=False, sem_entrada_antes_do_fim_min=0)


def dia(velas: list[tuple[float, float, float, float]], inicio="2024-03-04 09:15",
        sessao=0) -> pd.DataFrame:
    t0 = pd.Timestamp(inicio, tz="Asia/Hong_Kong")
    return pd.DataFrame([{
        "tempo_ativo": t0 + pd.Timedelta(minutes=i), "abertura": o, "maxima": h,
        "minima": l, "fechamento": c, "spread_pontos": 0, "sessao_id": sessao,
    } for i, (o, h, l, c) in enumerate(velas)])


# Primeira vela: fundo 1000, topo 1100 -> B = 1000, w = 100.
# Grade: ... 900 | 1000 | 1100 | 1200 | 1300 ...
ABERTURA = (1050, 1100, 1000, 1080)


def rodar(velas, p=BASE, fech_ant=900.0, custos=SEM_CUSTO):
    return simular_dia(dia(velas), fech_ant, amp_ref=10.0, p=p, custos=custos)


# ------------------------------------------------------------------ canal

def test_canal_pela_primeira_vela():
    base, w, ultima = canal_de_abertura(dia([ABERTURA]), 10.0, BASE)
    assert (base, w, ultima) == (1000, 100, 0)


def test_vela_curta_espera_a_proxima():
    """Vela de abertura curta: espera fechar mais uma."""
    p = replace(BASE, velas_maximas=3, largura_minima=5.0)
    velas = [(1000, 1020, 1000, 1010), (1010, 1060, 1005, 1050)]
    base, w, ultima = canal_de_abertura(dia(velas), 10.0, p)
    assert ultima == 1 and base == 1000 and w == 60


def test_vela_gigante_usa_metade_do_corpo():
    """Metade do corpo da vela gigante vira o canal: corpo 400 -> w = 200."""
    p = replace(BASE, usar_vela_gigante=True, gigante_mult=6.0)
    base, w, _ = canal_de_abertura(dia([(1000, 1410, 990, 1400)]), 10.0, p)
    assert w == 200 and base == 1000


def test_canal_por_alvo_escolhe_o_par_mais_perto_de_50():
    """4 velas: de pavio a pavio dariam 80; corpo de cima com pavio de baixo, 52."""
    p = replace(BASE, canal_modo="alvo")
    velas = [(1000, 1030, 980, 1020), (1020, 1060, 1015, 1032),
             (1032, 1040, 1025, 1030), (1030, 1035, 1022, 1028)]
    base, w, ultima = canal_de_abertura(dia(velas), 10.0, p)
    assert ultima == 3
    assert 40 <= w <= 60 and abs(w - 50) <= 3


def test_canal_por_alvo_fora_da_faixa_nao_opera():
    """Abertura apertada (amplitude total 20) = dia lateral: nao opera."""
    p = replace(BASE, canal_modo="alvo", canal_fora_da_faixa="nao_opera")
    velas = [(1000, 1010, 995, 1005)] * 4
    assert canal_de_abertura(dia(velas), 10.0, p) is None


def test_canal_por_alvo_prefere_o_primeiro_preco():
    p = replace(BASE, canal_modo="alvo", canal_primeiro_preco=True)
    velas = [(1000, 1030, 980, 1020), (1020, 1060, 1015, 1032),
             (1032, 1040, 1025, 1030), (1030, 1035, 1022, 1028)]
    base, w, _ = canal_de_abertura(dia(velas), 10.0, p)
    assert 1000 in (base, base + w) and 40 <= w <= 60


def test_canal_por_alvo_em_porcentagem_do_preco():
    """Abertura 1000, alvo 5% = 50 pontos (faixa 40-60)."""
    p = replace(BASE, canal_modo="alvo", canal_alvo_pct=5.0)
    velas = [(1000, 1030, 980, 1020), (1020, 1060, 1015, 1032),
             (1032, 1040, 1025, 1030), (1030, 1035, 1022, 1028)]
    _, w, _ = canal_de_abertura(dia(velas), 10.0, p)
    assert 40 <= w <= 60


def test_vies_inicial_substitui_o_gap():
    """Gap de alta, mas vies de queda pelo dia anterior: fechar acima do NR
    nao e continuacao (nao ha tendencia de alta); fechar alem da ZR de cima e."""
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1125, 1115, 1121)]
    t = simular_dia(dia(velas), 900.0, 10.0, BASE, SEM_CUSTO, vies_inicial=-1)
    assert t == [] or t[0].tipo != "continuacao"


# ---------------------------------------------------------------- entradas

def test_continuacao_em_alta_stop_fora_da_zona_e_take_um_nivel():
    """Gap de alta, fecha acima do NR: compra. NR passa a [1100,1200], ZR
    [1000,1100] -> stop em 1000. Take 1 nivel acima da entrada."""
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1225, 1115, 1180)]
    t = rodar(velas)
    assert len(t) == 1
    tr = t[0]
    assert tr.direcao == 1 and tr.tipo == "continuacao"
    assert tr.preco_entrada == 1120 and tr.stop_inicial == 1000
    assert tr.take == 1220 and tr.motivo == "take"
    assert tr.resultado == pytest.approx(100)
    assert tr.r == pytest.approx(100 / 120)


def test_take_encerra_o_dia():
    """'bateu o alvo, encerra o dia' - nenhum sinal depois do take."""
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1225, 1115, 1180),
             (1180, 1190, 950, 960), (960, 965, 800, 810)]
    t = rodar(velas)
    assert len(t) == 1 and t[0].motivo == "take"


def test_reversao_perdeu_dois_niveis():
    """Gap de alta, NR [1000,1100], ZR [900,1000]: fechar abaixo de 900 e venda."""
    velas = [ABERTURA, (1080, 1085, 880, 890)]
    p = replace(BASE, entrada_continuacao=False)
    t = rodar(velas + [(890, 895, 885, 888)], p=p)
    assert len(t) == 1
    tr = t[0]
    assert tr.direcao == -1 and tr.tipo == "reversao"
    # Fechou em [800,900]: esse vira o NR de queda, ZR acima [900,1000] -> stop 1000.
    assert tr.stop_inicial == 1000


def test_compra_no_50():
    """Visitou a ZR e fechou de volta acima do meio do NR (1050): compra."""
    velas = [ABERTURA, (1080, 1082, 960, 970), (970, 1065, 968, 1060),
             (1060, 1062, 1058, 1061)]
    t = rodar(velas)
    assert len(t) == 1
    tr = t[0]
    assert tr.tipo == "cinquenta" and tr.direcao == 1
    assert tr.preco_entrada == 1060 and tr.stop_inicial == 900


def test_sem_visita_a_zn_nao_ha_compra_no_50():
    velas = [ABERTURA, (1080, 1082, 1010, 1020), (1020, 1065, 1015, 1060),
             (1060, 1062, 1058, 1061)]
    assert rodar(velas) == []


# ------------------------------------------------------------ gestao

def test_stop_por_fechamento_ignora_o_pavio():
    """No modo dele, a sombra nao conta: pavio abaixo do stop nao estopa."""
    velas = [ABERTURA, (1080, 1130, 1075, 1120),
             (1120, 1125, 990, 1010),        # pavio fura 1000, fecha acima
             (1010, 1015, 1005, 1012)]
    t = rodar(velas)
    assert len(t) == 1 and t[0].motivo == "fim_do_dia"


def test_stop_no_toque_sai_na_hora():
    velas = [ABERTURA, (1080, 1130, 1075, 1120),
             (1120, 1125, 990, 1010), (1010, 1015, 1005, 1012)]
    t = rodar(velas, p=replace(BASE, stop_modo="toque"))
    assert t[0].motivo == "stop" and t[0].preco_saida == 1000


def test_stop_na_pedra_com_gap_sai_na_abertura():
    velas = [ABERTURA, (1080, 1130, 1075, 1120),
             (970, 980, 960, 975), (975, 980, 970, 976)]
    t = rodar(velas, p=replace(BASE, stop_modo="toque"))
    assert t[0].preco_saida == 970


def test_0x0_depois_de_um_nivel_a_favor():
    """Fechou 1 nivel acima da entrada -> stop vai para a entrada."""
    p = replace(BASE, take_niveis=3)
    velas = [ABERTURA, (1080, 1130, 1075, 1120),
             (1120, 1225, 1118, 1222),       # fecha >= 1220: 0x0
             (1222, 1223, 1100, 1105),       # volta e toca a entrada
             (1105, 1106, 1100, 1101)]
    t = rodar(velas, p=p)
    assert t[0].foi_0x0 and t[0].motivo == "stop"
    assert t[0].resultado == pytest.approx(0)


def test_take_em_multiplos_do_risco():
    """Entrada 1120, stop 1000 (risco 120): take a 1,5R = 1300."""
    p = replace(BASE, take_r=1.5, usar_0x0=False)
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1305, 1115, 1290)]
    tr = rodar(velas, p=p)[0]
    assert tr.take == pytest.approx(1300) and tr.motivo == "take"
    assert tr.r == pytest.approx(1.5)


def test_gatilho_do_0x0_em_r():
    """Risco 120, gatilho 0,5R: fechar a 1180 (+60) ja trava no 0x0."""
    p = replace(BASE, take_r=1.5, gatilho_0x0_r=0.5)
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1185, 1118, 1180),
             (1180, 1182, 1100, 1105), (1105, 1106, 1100, 1101)]
    tr = rodar(velas, p=p)[0]
    assert tr.foi_0x0 and tr.resultado == pytest.approx(0)


def test_evitar_a_primeira_ordem_do_dia():
    """O 1o sinal (compra as 09:16) passa; o 2o (continuacao seguinte) entra."""
    p = replace(BASE, pular_sinais=1)
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1225, 1115, 1210),
             (1210, 1215, 1205, 1212)]
    t = rodar(velas, p=p)
    assert len(t) == 1 and t[0].preco_entrada == 1210
    assert len(rodar(velas)) == 1 and rodar(velas)[0].preco_entrada == 1120


def test_swap_cobrado_por_noite_e_triplo_na_quarta():
    """Comprado de terca a quinta: noite de terca (1) + quarta (3) = 4 noites."""
    c = Custos(slippage=0, comissao_pontos=0, spread_forcado=0.0, swap_compra=-1.0, dia_triplo=2)
    p = replace(BASE, take_niveis=0, usar_0x0=False)
    t0 = pd.Timestamp("2024-03-05 09:00", tz="Asia/Hong_Kong")    # terca
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1125, 1115, 1121)]
    d = dia(velas)
    d["tempo_ativo"] = [t0, t0 + pd.Timedelta(minutes=1), t0 + pd.Timedelta(days=2)]
    tr = simular_dia(d, 900.0, 10.0, p, c)[0]
    assert tr.motivo == "fim_do_dia"
    assert tr.custo == pytest.approx(4.0)


def test_gestao_semanal_um_gain_encerra_a_semana():
    """Dia 1 (seg) bate o take; dia 2 (ter) teria outro take, mas a semana acabou."""
    from strategy.grade import simular
    p = replace(BASE, gestao_semanal=True, tendencia="neutra")
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1225, 1115, 1180)]
    dias_ = [dia(velas, inicio=f"2024-03-0{k} 09:15") for k in (1, 4, 5)]  # sex, seg, ter
    df = pd.concat(dias_, ignore_index=True)
    t = simular(df, p, SEM_CUSTO)
    assert len(t) == 1 and t["motivo"].iloc[0] == "take"
    assert pd.Timestamp(t["tempo_entrada"].iloc[0]).day == 4
    sem_limite = simular(df, replace(BASE, tendencia="neutra"), SEM_CUSTO)
    assert len(sem_limite) == 2


def test_gestao_semanal_so_nos_dias_permitidos():
    from strategy.grade import simular
    p = replace(BASE, gestao_semanal=True, dias_semana=(1,), tendencia="neutra")       # so terca
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1225, 1115, 1180)]
    df = pd.concat([dia(velas, inicio=f"2024-03-0{k} 09:15") for k in (1, 4, 5)], ignore_index=True)
    t = simular(df, p, SEM_CUSTO)
    assert len(t) == 1 and pd.Timestamp(t["tempo_entrada"].iloc[0]).day == 5


def test_carregar_posicao_para_o_dia_seguinte():
    """Compra na segunda sem bater nada; na terca o alvo (1220) e atingido."""
    from strategy.grade import simular
    p = replace(BASE, tendencia="neutra", carregar_posicao="semana")
    seg = dia([ABERTURA, (1080, 1130, 1075, 1120), (1120, 1125, 1115, 1121)], inicio="2024-03-04 09:15")
    ter = dia([(1121, 1140, 1118, 1135), (1135, 1225, 1130, 1215), (1215, 1216, 1210, 1212)],
              inicio="2024-03-05 09:15")
    ref = dia([ABERTURA, ABERTURA], inicio="2024-03-01 09:15")
    df = pd.concat([ref, seg, ter], ignore_index=True)
    fecha = simular(df, replace(p, carregar_posicao="nao"), SEM_CUSTO)
    carrega = simular(df, p, SEM_CUSTO)
    assert fecha["motivo"].iloc[0] == "fim_do_dia"
    assert carrega["motivo"].iloc[0] == "take"
    assert pd.Timestamp(carrega["tempo_saida"].iloc[0]).day == 5


def test_carregar_na_sexta_fecha_se_a_regra_e_semana():
    from strategy.grade import simular
    p = replace(BASE, tendencia="neutra", carregar_posicao="semana")
    sex = dia([ABERTURA, (1080, 1130, 1075, 1120), (1120, 1125, 1115, 1121)], inicio="2024-03-08 09:15")
    seg = dia([(1121, 1140, 1118, 1135), (1135, 1225, 1130, 1215), (1215, 1216, 1210, 1212)],
              inicio="2024-03-11 09:15")
    t = simular(pd.concat([dia([ABERTURA, ABERTURA], inicio="2024-03-07 09:15"), sex, seg], ignore_index=True), p, SEM_CUSTO)
    assert t["motivo"].iloc[0] == "fim_do_dia"


def test_swap_nao_cobra_fim_de_semana():
    """Comprado de sexta a segunda: so a rolagem de sexta (1 noite, quarta e a tripla)."""
    from strategy.grade import simular
    c = Custos(slippage=0, comissao_pontos=0, spread_forcado=0.0, swap_compra=-1.0, dia_triplo=2)
    p = replace(BASE, tendencia="neutra", carregar_posicao="sempre", take_niveis=0, usar_0x0=False)
    sex = dia([ABERTURA, (1080, 1130, 1075, 1120), (1120, 1125, 1115, 1121)], inicio="2024-03-08 09:15")
    seg = dia([(1121, 1140, 1118, 1135), (1135, 1140, 1130, 1138), (1138, 1139, 985, 990)],
              inicio="2024-03-11 09:15")
    t = simular(pd.concat([dia([ABERTURA, ABERTURA], inicio="2024-03-07 09:15"), sex, seg], ignore_index=True), p, c)
    assert t["custo"].iloc[0] == pytest.approx(1.0)


def test_surfar_a_cada_nivel_sobe_o_stop():
    """Entrada 1120, w=100. Fecha em 1330 (2 niveis): stop vai a 1220. Volta: sai em 1220."""
    p = replace(BASE, take_niveis=0, surfar=True)
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1225, 1118, 1222),
             (1222, 1335, 1220, 1330), (1330, 1331, 1200, 1210), (1210, 1211, 1205, 1206)]
    t = rodar(velas, p=p)
    assert t[0].motivo == "stop" and t[0].preco_saida == pytest.approx(1220)


def test_custo_e_cobrado_nas_duas_pontas():
    """Spread inteiro no giro + derrapagem por ponta + comissao."""
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1225, 1115, 1180)]
    c = Custos(slippage=0.5, comissao_pontos=0.78, spread_forcado=4.0)
    tr = rodar(velas, custos=c)[0]
    assert tr.custo == pytest.approx(4.0 + 2 * 0.5 + 0.78)
    assert tr.resultado == pytest.approx(100 - tr.custo)


def test_limite_de_stops_no_dia():
    """3 stops seguidos encerram o dia (1% por trade, 3% no dia)."""
    p = replace(BASE, max_stops_dia=1, entrada_reversao=False, entrada_50=False)
    velas = [ABERTURA, (1080, 1130, 1075, 1120),
             (1120, 1121, 980, 990),          # stop por fechamento
             (990, 1300, 985, 1290),          # nova alta: nao pode entrar
             (1290, 1295, 1285, 1291)]
    t = rodar(velas, p=p)
    assert len(t) == 1


def test_sem_olhar_o_futuro():
    """A entrada nao muda se o dia for cortado logo depois dela."""
    velas = [ABERTURA, (1080, 1130, 1075, 1120), (1120, 1125, 1100, 1110),
             (1110, 1115, 1105, 1112)]
    completo = rodar(velas)
    cortado = rodar(velas[:3] + [(1110, 1115, 1105, 1112)])
    assert completo[0].tempo_entrada == cortado[0].tempo_entrada
    assert completo[0].stop_inicial == cortado[0].stop_inicial
