"""
Carregamento do config.yaml.

Regra do projeto: nenhum parametro vive no codigo. Todo modulo que precisa de
um numero pede para este carregador. Assim voce muda comportamento editando um
arquivo de texto, sem tocar em logica.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Raiz do projeto = pasta onde este arquivo esta.
RAIZ = Path(__file__).resolve().parent
CAMINHO_CONFIG_PADRAO = RAIZ / "config.yaml"


class Config:
    """Acesso ao config.yaml com caminho pontilhado: cfg.get('mt5.simbolo')."""

    def __init__(self, dados: dict[str, Any], caminho: Path):
        self._dados = dados
        self.caminho = caminho

    @classmethod
    def carregar(cls, caminho: str | Path | None = None) -> "Config":
        caminho = Path(caminho) if caminho else CAMINHO_CONFIG_PADRAO
        if not caminho.exists():
            raise FileNotFoundError(f"config.yaml nao encontrado em: {caminho}")
        with open(caminho, encoding="utf-8") as f:
            dados = yaml.safe_load(f) or {}
        return cls(dados, caminho)

    def get(self, chave: str, padrao: Any = None) -> Any:
        """Busca por caminho pontilhado. Ex: get('pregao.fuso_do_ativo')."""
        atual: Any = self._dados
        for parte in chave.split("."):
            if not isinstance(atual, dict) or parte not in atual:
                return padrao
            atual = atual[parte]
        return atual

    def exigir(self, chave: str) -> Any:
        """Igual ao get, mas explode se o valor estiver ausente ou nulo.

        Usado para parametros sem os quais o resultado seria silenciosamente
        errado - preferimos quebrar cedo a produzir um backtest que mente.
        """
        valor = self.get(chave)
        if valor is None:
            raise KeyError(f"Parametro obrigatorio ausente no config.yaml: '{chave}'")
        return valor

    def definir(self, chave: str, valor: Any) -> None:
        """Grava um valor em memoria (nao persiste em disco)."""
        partes = chave.split(".")
        atual = self._dados
        for parte in partes[:-1]:
            atual = atual.setdefault(parte, {})
        atual[partes[-1]] = valor

    def caminho_absoluto(self, chave: str) -> Path:
        """Resolve um caminho do config em relacao a pasta do projeto."""
        return (RAIZ / str(self.exigir(chave))).resolve()

    @property
    def bruto(self) -> dict[str, Any]:
        return self._dados
