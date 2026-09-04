"""
Testes da Etapa 1 com dados sinteticos.

Objetivo: validar a logica de fuso, filtro de pregao e deteccao de buracos
SEM depender do MetaTrader 5. Assim um bug de tratamento aparece aqui, e nao
disfarcado no meio de um backtest de tres anos.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from configuracao import Config
from data import coleta, tratamento

FUSO_SERVIDOR_FALSO = "Europe/Athens"  # EET/EEST, igual ao servidor real da corretora


def gerar_candles(dias: int = 40, minutos: int = 15,
                  fuso_servidor: str = FUSO_SERVIDOR_FALSO,
                  inicio_em: str = "2024-01-01") -> pd.DataFrame:
    """Constroi um historico falso de HK50 carimbado na hora do servidor.

    Os candles nascem em hora de Hong Kong (09:15-12:00 e 13:00-16:30, mais
    ruido de after-hours) e sao convertidos para a hora local do servidor -
    o caminho inverso do que o codigo de producao faz. Como o fuso do servidor
    tem horario de verao, um periodo longo atravessa a virada: exatamente o
    caso que um offset fixo em horas erraria.
    """
    hk = ZoneInfo("Asia/Hong_Kong")
    servidor = ZoneInfo(fuso_servidor)
    linhas = []
    preco = 20000.0
    dia = datetime.fromisoformat(inicio_em)
    passos_por_hora = 60 // minutos

    for _ in range(dias):
        if dia.weekday() < 5:  # so dias uteis tem pregao
            for hora_hk, dur_h, volume in [(9.25, 2.75, 800), (13.0, 3.5, 900), (17.0, 3.0, 20)]:
                h, m = int(hora_hk), int(round((hora_hk % 1) * 60))
                abertura_hk = datetime(dia.year, dia.month, dia.day, h, m, tzinfo=hk)
                for k in range(int(dur_h * passos_por_hora)):
                    t_hk = abertura_hk + timedelta(minutes=minutos * k)
                    # O MT5 entrega hora local do servidor, sem fuso anexado.
                    t = t_hk.astimezone(servidor).replace(tzinfo=None)
                    preco += np.random.default_rng(len(linhas)).normal(0, 5)
                    linhas.append({
                        "tempo_servidor": t,
                        "abertura": preco, "maxima": preco + 8,
                        "minima": preco - 8, "fechamento": preco + 1,
                        "volume_ticks": volume, "volume_real": 0, "spread_pontos": 2,
                    })
        dia += timedelta(days=1)

    return pd.DataFrame(linhas).sort_values("tempo_servidor").reset_index(drop=True)


@pytest.fixture
def cfg() -> Config:
    """Perfil do HK50, explicitamente.

    Estes testes cobrem o tratamento de mercado com SESSOES fixas. Carregar o
    config sem dizer qual mercado pegaria o ativo do momento - hoje o ouro, que
    e continuo - e os testes passariam a medir outra coisa sem ninguem notar.
    """
    return Config.carregar(mercado="HK50")


def test_infere_o_fuso_do_servidor_corretamente(cfg):
    """O fuso do servidor precisa sair dos dados, sem ninguem informar."""
    df = gerar_candles(dias=120)
    fuso, consistencia, abertura = coleta.inferir_fuso_servidor(df, cfg)
    assert fuso in ("Europe/Athens", "Europe/Helsinki")  # equivalentes na pratica
    assert abertura == "09:15"
    assert consistencia > 0.95


def test_horario_de_verao_do_servidor_nao_desloca_o_pregao(cfg):
    """O caso que um offset fixo em horas erraria: a virada do horario de verao.

    Marco de 2024 atravessa a mudanca EET -> EEST. Com fuso nomeado, a abertura
    tem que continuar caindo as 09:15 de Hong Kong dos dois lados da virada.
    """
    df = gerar_candles(dias=60, inicio_em="2024-03-01")
    com_fuso = coleta.aplicar_fusos(df, FUSO_SERVIDOR_FALSO, "Asia/Hong_Kong")
    _, pregao, _ = tratamento.processar(com_fuso, "M15", cfg)

    aberturas = (pregao.groupby(pregao["tempo_ativo"].dt.date)["tempo_ativo"]
                 .min().dt.strftime("%H:%M").unique())
    assert list(aberturas) == ["09:15"], f"abertura variou em Hong Kong: {aberturas}"

    # E o carimbo cru do servidor muda de hora, provando que a virada ocorreu
    # dentro da amostra - sem isso o teste passaria sem testar nada.
    cruas = (pregao.groupby(pregao["tempo_ativo"].dt.date)["tempo_servidor"]
             .min().dt.strftime("%H:%M").unique())
    assert len(cruas) == 2, f"esperava dois horarios de servidor, vi {cruas}"


def test_conversao_de_fuso_bate_com_o_pregao_de_hong_kong(cfg):
    df = coleta.aplicar_fusos(gerar_candles(), FUSO_SERVIDOR_FALSO, "Asia/Hong_Kong")
    marcado = tratamento.marcar_pregao(df, cfg)
    dentro = marcado[marcado["em_pregao"]]
    assert dentro["tempo_ativo"].dt.hour.min() == 9
    assert dentro["tempo_ativo"].dt.hour.max() == 16


def test_filtro_de_pregao_descarta_after_hours_e_fim_de_semana(cfg):
    df = coleta.aplicar_fusos(gerar_candles(), FUSO_SERVIDOR_FALSO, "Asia/Hong_Kong")
    _, pregao, rel = tratamento.processar(df, "M15", cfg)

    assert rel.removidos_fora_pregao > 0, "after-hours deveria ter sido removido"
    assert pregao["tempo_ativo"].dt.dayofweek.max() <= 4, "sobrou fim de semana"
    # 11 candles em 09:15-12:00 + 14 em 13:00-16:30 = 25 por pregao.
    assert rel.candles_por_dia_mediana == 25


def test_candles_de_volume_zero_e_ohlc_invalido_sao_removidos(cfg):
    df = coleta.aplicar_fusos(gerar_candles(dias=10), FUSO_SERVIDOR_FALSO, "Asia/Hong_Kong")
    df.loc[5, "volume_ticks"] = 0
    df.loc[6, "minima"] = df.loc[6, "maxima"] + 50  # minima acima da maxima

    _, _, rel = tratamento.processar(df, "M15", cfg)
    assert rel.removidos_volume_zero == 1
    assert rel.removidos_ohlc_invalido == 1


def test_buraco_dentro_da_sessao_e_detectado(cfg):
    """Remover candles no meio de um pregao precisa acender o alerta."""
    df = coleta.aplicar_fusos(gerar_candles(dias=10), FUSO_SERVIDOR_FALSO, "Asia/Hong_Kong")
    _, pregao_ok, rel_ok = tratamento.processar(df, "M15", cfg)
    assert rel_ok.buracos_intra_sessao == 0, "base intacta nao deveria ter buracos"

    # Arranca 6 candles do MEIO da sessao da tarde de um pregao qualquer.
    # Tem que ser do meio: remover o inicio ou o fim de uma sessao so a
    # encurta, nao cria buraco - e o codigo esta certo em nao alertar nesse caso.
    tarde = pregao_ok[pregao_ok["sessao_id"] == 1]
    um_dia = tarde[tarde["tempo_ativo"].dt.date == tarde["tempo_ativo"].dt.date.iloc[0]]
    assert len(um_dia) >= 12, "sessao da tarde curta demais para o teste"
    tempos_removidos = set(um_dia["tempo_ativo"].iloc[3:9])
    furado = df[~df["tempo_ativo"].isin(tempos_removidos)].copy()

    _, _, rel_furado = tratamento.processar(furado, "M15", cfg)
    assert rel_furado.buracos_intra_sessao >= 1
    assert rel_furado.maior_buraco_candles >= 6


def test_intervalo_do_almoco_nao_conta_como_buraco(cfg):
    """A pausa 12:00-13:00 e mercado fechado, nao falha de dado."""
    df = coleta.aplicar_fusos(gerar_candles(dias=20), FUSO_SERVIDOR_FALSO, "Asia/Hong_Kong")
    _, _, rel = tratamento.processar(df, "M15", cfg)
    assert rel.buracos_intra_sessao == 0
