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


def _mesclar(base: dict, sobreposicao: dict) -> dict:
    """Mescla dicionarios em profundidade, sem alterar o original.

    Sobrepor no nivel raso apagaria secoes inteiras: um mercado que so quer
    trocar 'custos.spread_indice' perderia todo o resto de 'custos'.
    """
    saida = dict(base)
    for chave, valor in (sobreposicao or {}).items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            saida[chave] = _mesclar(saida[chave], valor)
        else:
            saida[chave] = valor
    return saida


class Config:
    """Acesso ao config.yaml com caminho pontilhado: cfg.get('mt5.simbolo')."""

    def __init__(self, dados: dict[str, Any], caminho: Path):
        self._dados = dados
        self.caminho = caminho

    @classmethod
    def carregar(cls, caminho: str | Path | None = None,
                 mercado: str | None = None) -> "Config":
        """Carrega o config e aplica por cima o perfil do mercado ativo.

        O arquivo tem uma base comum e uma secao 'mercados' com o que muda de
        um instrumento para outro - simbolo, fuso, sessoes, custos. O perfil e
        mesclado sobre a base, entao cada mercado so precisa declarar suas
        diferencas em vez de repetir o config inteiro.
        """
        caminho = Path(caminho) if caminho else CAMINHO_CONFIG_PADRAO
        if not caminho.exists():
            raise FileNotFoundError(f"config.yaml nao encontrado em: {caminho}")
        with open(caminho, encoding="utf-8") as f:
            dados = yaml.safe_load(f) or {}

        nome = mercado or dados.get("mercado_ativo")
        perfis = dados.get("mercados") or {}
        if nome:
            if nome not in perfis:
                raise KeyError(
                    f"Mercado '{nome}' nao existe no config. "
                    f"Disponiveis: {sorted(perfis)}")
            dados = _mesclar(dados, perfis[nome])
            dados["mercado_ativo"] = nome
        return cls(dados, caminho)

    @property
    def mercado(self) -> str:
        return self._dados.get("mercado_ativo", "(nenhum)")

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
