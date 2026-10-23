"""Testes do Ichimoku de referencia."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from strategy.grade import Custos
from strategy.ichimoku import ParametrosIchimoku, nuvem, simular_ichimoku

SEM = Custos(0, 0, 0.0)
P = ParametrosIchimoku(tenkan=2, kijun=3, senkou_b=4, deslocamento=2, sem_entrada_antes_do_fim_min=0)


def serie(fech, dia=None):
    n = len(fech)
    t0 = pd.Timestamp("2024-03-04 09:00")
    return pd.DataFrame({
        "tempo_ativo": [t0 + pd.Timedelta(minutes=k) for k in range(n)],
        "abertura": fech, "maxima": np.array(fech) + 0.5, "minima": np.array(fech) - 0.5,
        "fechamento": fech, "spread_pontos": 0, "dia": dia if dia is not None else [0] * n})


def test_nuvem_nao_olha_o_futuro():
    """Mudar as velas depois de t nao muda a nuvem em t."""
    base = list(np.linspace(100, 110, 30))
    alt = base[:20] + [500.0] * 10
    s1, i1 = nuvem(serie(base), P)
    s2, i2 = nuvem(serie(alt), P)
    assert np.allclose(s1[:21], s2[:21], equal_nan=True)
    assert np.allclose(i1[:21], i2[:21], equal_nan=True)


def test_compra_ao_romper_a_nuvem_e_vira_a_mao_no_outro_lado():
    fech = [100.0] * 10 + [101, 103, 106, 110, 114, 118, 120, 119, 112, 104, 98, 94, 92, 91, 90]
    t = simular_ichimoku(serie(fech), P, SEM)
    assert t["direcao"].iloc[0] == 1
    assert (t["direcao"] == -1).any()                 # virou a mao
    assert t["motivo"].iloc[0] == "nuvem"


def test_espelho_sai_junto_com_o_original():
    fech = [100.0] * 10 + [101, 103, 106, 110, 114, 118, 120, 119, 112, 104, 98, 94, 92, 91, 90]
    a = simular_ichimoku(serie(fech), P, SEM)
    b = simular_ichimoku(serie(fech), replace(P, controle_inverter=True), SEM)
    assert list(a["tempo_saida"]) == list(b["tempo_saida"])
    assert np.allclose(a["resultado_bruto"], -b["resultado_bruto"])


def test_saida_na_reentrada_sai_antes_da_raiz():
    """Mesma serie: a saida na reentrada fecha a compra antes (e mais cara) que o classico."""
    fech = [100.0] * 10 + [101, 103, 106, 110, 114, 118, 120, 119, 112, 104, 98, 94, 92, 91, 90]
    classico = simular_ichimoku(serie(fech), P, SEM)
    reent = simular_ichimoku(serie(fech), replace(P, saida="reentrada"), SEM)
    assert reent["motivo"].iloc[0] == "reentrou"
    assert reent["tempo_saida"].iloc[0] <= classico["tempo_saida"].iloc[0]


def test_fecha_no_fim_do_dia():
    fech = [100.0] * 10 + [101, 103, 106, 110, 114, 118, 120]
    dia = [0] * 14 + [1] * 3
    t = simular_ichimoku(serie(fech, dia), P, SEM)
    assert "fim_do_dia" in set(t["motivo"])


def test_pausa_depois_de_trade_grande_ignora_o_proximo_sinal():
    """Com gatilho em qualquer resultado e N=1, nunca vira a mao na vela da saida."""
    rng = np.random.default_rng(7)
    fech = list(100 + np.cumsum(rng.normal(0, 1, 600)))
    base = simular_ichimoku(serie(fech), P, SEM)
    pausa = simular_ichimoku(serie(fech), replace(P, pausa_apos_r=-1e9, pausa_sinais=1), SEM)
    assert (base["tempo_entrada"].iloc[1:].to_numpy() == base["tempo_saida"].iloc[:-1].to_numpy()).any()
    assert (pausa["tempo_entrada"].iloc[1:].to_numpy() > pausa["tempo_saida"].iloc[:-1].to_numpy()).all()
    assert 0 < len(pausa) < len(base)
    alto = simular_ichimoku(serie(fech), replace(P, pausa_apos_r=1e9, pausa_sinais=3), SEM)
    pd.testing.assert_frame_equal(alto, base)
