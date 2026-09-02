"""
Gravacao e leitura dos dados historicos em parquet.

Parquet e nao CSV porque preserva tipo e fuso horario das colunas de tempo -
com CSV o timezone vira texto e alguem, uma hora, le errado. Um CSV de amostra
e gravado junto so para inspecao humana rapida.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

COLUNAS_ESSENCIAIS = [
    "tempo_ativo", "tempo_utc", "tempo_servidor",
    "abertura", "maxima", "minima", "fechamento",
    "volume_ticks", "volume_real", "spread_pontos",
]


def caminho_parquet(pasta: Path, simbolo: str, timeframe: str, sufixo: str) -> Path:
    simbolo_seguro = simbolo.replace(".", "_").replace("/", "_")
    return pasta / f"{simbolo_seguro}_{timeframe}_{sufixo}.parquet"


def salvar(df: pd.DataFrame, caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    colunas = [c for c in COLUNAS_ESSENCIAIS if c in df.columns]
    extras = [c for c in df.columns if c not in colunas]
    df[colunas + extras].to_parquet(caminho, index=False, compression="snappy")
    return caminho


def salvar_amostra_csv(df: pd.DataFrame, caminho_parquet_: Path, linhas: int = 500) -> Path:
    """Grava as ultimas N linhas em CSV, so para voce abrir e conferir a olho."""
    destino = caminho_parquet_.with_name(caminho_parquet_.stem + "_amostra.csv")
    df.tail(linhas).to_csv(destino, index=False, encoding="utf-8")
    return destino


def carregar(caminho: Path) -> pd.DataFrame:
    if not Path(caminho).exists():
        raise FileNotFoundError(
            f"Arquivo de historico nao encontrado: {caminho}\n"
            "Rode 'python coletar.py' com o MetaTrader 5 aberto e logado."
        )
    return pd.read_parquet(caminho)


def salvar_metadados(pasta: Path, dados: dict) -> Path:
    """Metadados da coleta: sem isso voce nao sabe de quando sao os dados."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / "metadados_coleta.json"
    dados = {"gerado_em_utc": datetime.now(timezone.utc).isoformat(), **dados}
    destino.write_text(json.dumps(dados, indent=2, ensure_ascii=False, default=str),
                       encoding="utf-8")
    return destino
