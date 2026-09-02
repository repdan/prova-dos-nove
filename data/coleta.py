"""
Coleta de candles historicos do MT5.

Duas sutilezas que costumam estragar backtest e que sao tratadas aqui:

1. O MT5 devolve o horario do SERVIDOR da corretora, nao UTC e nao seu horario
   local. Se voce ignorar isso, toda analise por horario do dia sai deslocada em
   algumas horas - e a Etapa 4 depende exatamente dessa analise. O offset do
   servidor e inferido a partir dos proprios dados (ver inferir_offset_servidor).

2. O terminal so entrega o historico que ja baixou. Pedir um periodo maior do
   que o cache nao da erro: ele simplesmente devolve menos candles, em silencio.
   Por isso a coleta sempre reporta o periodo real obtido.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from configuracao import Config
from data.mt5_conexao import ErroMT5

# Mapa de nome legivel -> constante da API.
TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

MINUTOS_POR_TIMEFRAME = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


def _puxar_bloco(simbolo: str, tf: int, inicio: datetime, fim: datetime,
                 tentativas: int, espera_s: float) -> np.ndarray | None:
    """Pede um bloco ao terminal, com repeticao.

    Detalhe que economiza muito trabalho manual: copy_rates_range NAO le apenas
    o cache - ela tambem dispara o download do periodo pedido no terminal. So
    que o download e assincrono, entao a primeira chamada costuma voltar vazia
    enquanto o terminal ainda busca. Repetir depois de uma pausa curta resolve,
    e evita ter que rolar o grafico para tras na mao.
    """
    melhor = None
    for tentativa in range(tentativas):
        rates = mt5.copy_rates_range(simbolo, tf, inicio, fim)
        if rates is not None and len(rates) > 0:
            if melhor is None or len(rates) > len(melhor):
                melhor = rates
            # Duas leituras seguidas com o mesmo tamanho = download terminou.
            if tentativa > 0 and len(rates) == len(melhor):
                break
        if tentativa < tentativas - 1:
            time.sleep(espera_s)
    return melhor


def coletar_candles(simbolo: str, timeframe: str, data_inicial: str,
                    tentativas: int = 3, espera_s: float = 2.0) -> pd.DataFrame:
    """Baixa todos os candles disponiveis, em blocos anuais.

    O bloco anual existe porque o terminal limita quantas barras devolve de uma
    vez ('Max. barras no grafico'). Pedir ano a ano contorna esse teto sem
    depender da configuracao da maquina.

    Blocos vazios sao repetidos algumas vezes antes de desistir, para dar tempo
    do terminal baixar o periodo do servidor da corretora.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Timeframe '{timeframe}' desconhecido. Use: {list(TIMEFRAMES)}")

    tf = TIMEFRAMES[timeframe]
    inicio = datetime.fromisoformat(data_inicial).replace(tzinfo=timezone.utc)
    # Margem para frente garante que o ultimo candle fechado entre no resultado.
    fim = datetime.now(timezone.utc) + timedelta(days=2)

    blocos: list[np.ndarray] = []
    cursor = inicio
    vazios_seguidos = 0
    while cursor < fim:
        proximo = min(cursor.replace(year=cursor.year + 1), fim)
        # Antes do primeiro dado aparecer, insistir em cada ano vazio custaria
        # minutos a toa (o historico do HK50 nao comeca em 2010). So vale
        # insistir depois que o historico ja comecou.
        insistir = tentativas if blocos else 1
        rates = _puxar_bloco(simbolo, tf, cursor, proximo, insistir, espera_s)

        if rates is not None and len(rates) > 0:
            blocos.append(rates)
            vazios_seguidos = 0
        elif blocos:
            vazios_seguidos += 1
            # Dois anos seguidos vazios depois de ja ter dado = fim do historico.
            if vazios_seguidos >= 2:
                break
        cursor = proximo

    if not blocos:
        codigo, mensagem = mt5.last_error()
        raise ErroMT5(
            f"Nenhum candle retornado para {simbolo} {timeframe} "
            f"(ultimo erro da API: {codigo} - {mensagem}).\n"
            "Causa quase sempre e cache vazio no terminal. No MT5:\n"
            "  1. Ferramentas > Opcoes > Graficos > 'Max. barras no grafico' = Ilimitado\n"
            f"  2. Abra o grafico de {simbolo} em {timeframe} e role para tras ate o inicio\n"
            "  3. Rode este script de novo"
        )

    df = pd.DataFrame(np.concatenate(blocos))
    # 'time' vem em segundos desde a epoca, ja no horario do servidor.
    df["tempo_servidor"] = pd.to_datetime(df["time"], unit="s")
    df = df.drop(columns=["time"])

    df = df.rename(columns={
        "open": "abertura",
        "high": "maxima",
        "low": "minima",
        "close": "fechamento",
        "tick_volume": "volume_ticks",
        "real_volume": "volume_real",
        "spread": "spread_pontos",
    })

    # Blocos anuais podem se sobrepor na fronteira: desduplica e ordena.
    df = df.drop_duplicates(subset="tempo_servidor").sort_values("tempo_servidor")
    return df.reset_index(drop=True)


def inferir_offset_servidor(df: pd.DataFrame, cfg: Config) -> tuple[int, float]:
    """Descobre o fuso do servidor da corretora a partir dos proprios dados.

    Ideia: o pregao de Hong Kong tem horario conhecido e fixo. Testamos cada
    offset possivel (UTC-12 a UTC+14) e ficamos com aquele que joga a maior
    parte do volume negociado para dentro da janela de pregao. E auto-corretivo:
    se a corretora mudar de fuso no horario de verao, o numero muda junto.

    Retorna (offset_em_horas, fracao_do_volume_dentro_do_pregao).
    """
    fuso = ZoneInfo(cfg.exigir("pregao.fuso_do_ativo"))
    sessoes = cfg.exigir("pregao.sessoes_regulares")
    volume = df["volume_ticks"].to_numpy(dtype="float64")
    total = volume.sum()
    if total <= 0:
        raise ErroMT5("Volume total zerado - impossivel inferir o fuso do servidor.")

    melhor_offset, melhor_score = 0, -1.0
    for offset in range(-12, 15):
        # Interpreta o horario do servidor como UTC+offset e converte para HK.
        local = (
            df["tempo_servidor"]
            .dt.tz_localize(timezone.utc)
            .sub(pd.Timedelta(hours=offset))
            .dt.tz_convert(fuso)
        )
        minutos = local.dt.hour * 60 + local.dt.minute
        dentro = np.zeros(len(df), dtype=bool)
        for s in sessoes:
            ini = _para_minutos(s["inicio"])
            fim = _para_minutos(s["fim"])
            dentro |= (minutos >= ini) & (minutos < fim)
        score = volume[dentro].sum() / total
        if score > melhor_score:
            melhor_offset, melhor_score = offset, score

    return melhor_offset, float(melhor_score)


def aplicar_fusos(df: pd.DataFrame, offset_servidor: int, fuso_ativo: str) -> pd.DataFrame:
    """Cria as colunas de tempo em UTC e no fuso do ativo.

    Todo o resto do projeto decide por 'tempo_ativo' (horario de Hong Kong),
    porque e o horario que define abertura, almoco e fechamento do pregao.
    'tempo_utc' fica como referencia absoluta e imune a horario de verao.
    """
    df = df.copy()
    df["tempo_utc"] = (
        df["tempo_servidor"].dt.tz_localize(timezone.utc)
        - pd.Timedelta(hours=offset_servidor)
    )
    df["tempo_ativo"] = df["tempo_utc"].dt.tz_convert(ZoneInfo(fuso_ativo))
    return df


def _para_minutos(hhmm: str) -> int:
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)
