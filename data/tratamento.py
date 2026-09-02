"""
Tratamento e diagnostico de qualidade dos dados.

Filosofia: nada e apagado em silencio. Toda linha removida entra no relatorio
de qualidade, com o motivo. Se o backtest der um resultado estranho la na
frente, voce consegue voltar aqui e ver o que foi mexido.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from configuracao import Config
from data.coleta import MINUTOS_POR_TIMEFRAME, _para_minutos


@dataclass
class RelatorioQualidade:
    """O que a coleta encontrou e o que ela mexeu."""

    candles_brutos: int = 0
    candles_pregao: int = 0
    removidos_ohlc_invalido: int = 0
    removidos_volume_zero: int = 0
    removidos_fora_pregao: int = 0
    removidos_dia_nao_negociado: int = 0
    duplicados: int = 0
    dias_descartados_por_densidade: int = 0
    candles_descartados_por_densidade: int = 0
    candles_antes_do_corte_inicial: int = 0
    primeiro_dia_utilizavel: str = ""
    buracos_intra_sessao: int = 0
    maior_buraco_candles: int = 0
    detalhe_maiores_buracos: list = field(default_factory=list)
    dias_negociados: int = 0
    candles_por_dia_mediana: float = 0.0

    def como_dict(self) -> dict:
        return asdict(self)


def marcar_pregao(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Adiciona a coluna booleana 'em_pregao' sem remover nada ainda."""
    sessoes = cfg.exigir("pregao.sessoes_regulares")
    dias_ok = set(cfg.exigir("pregao.dias_negociados"))

    minutos = df["tempo_ativo"].dt.hour * 60 + df["tempo_ativo"].dt.minute

    # sessao_id identifica em QUAL bloco do pregao o candle caiu (0 = manha,
    # 1 = tarde...). -1 significa fora do pregao. Essa marcacao e o que permite
    # distinguir, depois, um buraco de dado de uma pausa normal do mercado:
    # a pausa do almoco e uma troca de sessao, nao candles faltando.
    sessao_id = np.full(len(df), -1, dtype=int)
    for indice, s in enumerate(sessoes):
        na_sessao = (minutos >= _para_minutos(s["inicio"])) & (minutos < _para_minutos(s["fim"]))
        sessao_id[na_sessao.to_numpy()] = indice

    dia_ok = df["tempo_ativo"].dt.dayofweek.isin(dias_ok).to_numpy()

    df = df.copy()
    df["sessao_id"] = sessao_id
    df["em_pregao"] = (sessao_id >= 0) & dia_ok
    df["dia_negociado"] = dia_ok
    return df


def limpar(df: pd.DataFrame, cfg: Config, rel: RelatorioQualidade) -> pd.DataFrame:
    """Remove candles invalidos. Cada remocao e contabilizada no relatorio."""
    antes = len(df)

    duplicados = int(df["tempo_ativo"].duplicated().sum())
    if duplicados:
        df = df[~df["tempo_ativo"].duplicated()].copy()
    rel.duplicados = duplicados

    if cfg.get("tratamento.remover_ohlc_invalido", True):
        # Um candle so e valido se maxima >= max(abertura, fechamento) >= minima.
        valido = (
            (df["maxima"] >= df["minima"])
            & (df["maxima"] >= df[["abertura", "fechamento"]].max(axis=1))
            & (df["minima"] <= df[["abertura", "fechamento"]].min(axis=1))
        )
        rel.removidos_ohlc_invalido = int((~valido).sum())
        df = df[valido].copy()

    if cfg.get("tratamento.remover_volume_zero", True):
        # Barra sem nenhum tick nao representa negociacao real: e preenchimento
        # do terminal. Manter isso infla o numero de candles e distorce o ATR.
        com_volume = df["volume_ticks"] > 0
        rel.removidos_volume_zero = int((~com_volume).sum())
        df = df[com_volume].copy()

    assert len(df) <= antes
    return df.reset_index(drop=True)


def filtrar_pregao(df: pd.DataFrame, rel: RelatorioQualidade) -> pd.DataFrame:
    """Mantem apenas os candles do pregao regular."""
    rel.removidos_dia_nao_negociado = int((~df["dia_negociado"]).sum())
    rel.removidos_fora_pregao = int((df["dia_negociado"] & ~df["em_pregao"]).sum())
    filtrado = df[df["em_pregao"]].copy()
    return filtrado.reset_index(drop=True)


def descartar_dias_ralos(df: pd.DataFrame, cfg: Config,
                         rel: RelatorioQualidade) -> pd.DataFrame:
    """Remove dias que tem candles de menos para serem pregao de verdade.

    O terminal MT5 as vezes guarda uma barra solitaria por dia em periodos que
    ele nunca baixou de fato. Essas barras passam por todas as validacoes
    individuais - OHLC coerente, volume positivo - e mesmo assim nao descrevem
    um pregao. Se entrarem no backtest viram sinais de rompimento inventados.

    O corte e relativo a mediana do proprio ativo, entao nao depende de saber
    quantos candles "deveria" ter cada timeframe.
    """
    fracao_minima = float(cfg.get("tratamento.densidade_minima_do_dia", 0.25))
    if fracao_minima <= 0 or df.empty:
        return df

    por_dia = df.groupby(df["tempo_ativo"].dt.date).size()
    minimo = por_dia.median() * fracao_minima
    dias_ok = set(por_dia[por_dia >= minimo].index)

    rel.dias_descartados_por_densidade = int(len(por_dia) - len(dias_ok))
    manter = df["tempo_ativo"].dt.date.isin(dias_ok)
    rel.candles_descartados_por_densidade = int((~manter).sum())

    filtrado = df[manter]

    # Corte explicito de data, aplicado depois do filtro estatistico.
    corte = cfg.get("tratamento.data_inicial_utilizavel")
    if corte:
        limite = pd.Timestamp(corte).date()
        antes = filtrado["tempo_ativo"].dt.date < limite
        rel.candles_antes_do_corte_inicial = int(antes.sum())
        filtrado = filtrado[~antes]

    filtrado = filtrado.reset_index(drop=True)
    if not filtrado.empty:
        rel.primeiro_dia_utilizavel = str(filtrado["tempo_ativo"].dt.date.min())
    return filtrado


def analisar_buracos(df: pd.DataFrame, timeframe: str, cfg: Config,
                     rel: RelatorioQualidade) -> pd.DataFrame:
    """Procura candles faltando DENTRO de uma mesma sessao.

    Distincao que importa: o intervalo entre 16:30 e as 09:15 do dia seguinte
    nao e um buraco, e o mercado fechado. So conta como buraco a ausencia de
    candles dentro de uma sequencia continua do mesmo dia - isso sim indica
    falha de download ou feriado parcial.
    """
    passo = MINUTOS_POR_TIMEFRAME[timeframe]
    limite_alerta = int(cfg.get("tratamento.candles_faltando_para_alertar", 4))

    diferenca = df["tempo_ativo"].diff().dt.total_seconds().div(60)

    # So faz sentido comparar dois candles se eles pertencem ao mesmo bloco
    # continuo de negociacao: mesmo dia E mesma sessao. Qualquer troca de
    # sessao (almoco) ou de dia (noite, fim de semana, feriado) e mercado
    # fechado - nao e dado faltando.
    mesmo_bloco = (
        (df["tempo_ativo"].dt.date == df["tempo_ativo"].dt.date.shift())
        & (df["sessao_id"] == df["sessao_id"].shift())
    )

    # Candles ausentes = quantos passos "sumiram" entre um candle e o anterior.
    ausentes = (diferenca / passo).sub(1).fillna(0)

    buracos = mesmo_bloco & (ausentes >= 1)
    rel.buracos_intra_sessao = int((buracos & (ausentes >= limite_alerta)).sum())
    rel.maior_buraco_candles = int(ausentes[buracos].max()) if buracos.any() else 0

    if buracos.any():
        piores = (
            df.loc[buracos, ["tempo_ativo"]]
            .assign(candles_faltando=ausentes[buracos].astype(int))
            .nlargest(5, "candles_faltando")
        )
        rel.detalhe_maiores_buracos = [
            {"quando": str(linha.tempo_ativo), "candles_faltando": int(linha.candles_faltando)}
            for linha in piores.itertuples()
        ]

    por_dia = df.groupby(df["tempo_ativo"].dt.date).size()
    rel.dias_negociados = int(len(por_dia))
    rel.candles_por_dia_mediana = float(por_dia.median()) if len(por_dia) else 0.0

    df = df.copy()
    df["candles_ausentes_antes"] = ausentes.where(buracos, 0).astype(int)
    return df


def processar(df_bruto: pd.DataFrame, timeframe: str,
              cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, RelatorioQualidade]:
    """Pipeline completo. Retorna (bruto_marcado, so_pregao, relatorio)."""
    rel = RelatorioQualidade(candles_brutos=len(df_bruto))

    df = marcar_pregao(df_bruto, cfg)
    df = limpar(df, cfg, rel)
    df = marcar_pregao(df, cfg)  # remarca apos a limpeza reindexar

    pregao = filtrar_pregao(df, rel)
    pregao = descartar_dias_ralos(pregao, cfg, rel)
    pregao = analisar_buracos(pregao, timeframe, cfg, rel)
    rel.candles_pregao = len(pregao)

    return df, pregao, rel
