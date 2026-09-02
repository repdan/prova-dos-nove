"""
Interfaces que toda estrategia do projeto precisa implementar.

O engine de backtest (Etapa 3) so conhece o que esta neste arquivo. Ele nunca
importa uma estrategia concreta, nunca sabe o que e um canal e nunca le config
de estrategia. Consequencia pratica: criar uma estrategia nova e criar um
arquivo novo em /strategy - sem tocar em uma linha do engine.

A mesma interface serve para o backtest e para a operacao ao vivo. A estrategia
recebe um candle por vez, na ordem, e responde com uma decisao usando apenas o
que ja aconteceu. Nao existe acesso ao futuro nem ao DataFrame inteiro.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Sinal(Enum):
    """O que a estrategia quer fazer ao ver um candle."""

    NENHUM = "nenhum"
    COMPRA = "compra"
    VENDA = "venda"


class Direcao(Enum):
    """Lado de uma posicao aberta."""

    COMPRADO = "comprado"
    VENDIDO = "vendido"

    @property
    def sinal_de_abertura(self) -> Sinal:
        return Sinal.COMPRA if self is Direcao.COMPRADO else Sinal.VENDA

    @property
    def multiplicador(self) -> int:
        """+1 para comprado, -1 para vendido. Simplifica calculo de resultado."""
        return 1 if self is Direcao.COMPRADO else -1


@dataclass(frozen=True)
class Candle:
    """Um candle fechado. Imutavel de proposito: ninguem reescreve o passado."""

    tempo: datetime          # sempre no fuso do ativo (Hong Kong)
    abertura: float
    maxima: float
    minima: float
    fechamento: float
    volume: float
    spread: float = 0.0

    @property
    def amplitude(self) -> float:
        return self.maxima - self.minima


@dataclass
class Posicao:
    """Uma posicao aberta, com o contexto do momento em que foi aberta.

    O contexto de entrada nao e enfeite: a saida por expansao de Fibonacci
    precisa da largura do canal NO MOMENTO DO ROMPIMENTO, e a Etapa 4 precisa
    das features daquele instante para treinar o classificador. Guardar isso na
    abertura evita ter que reconstruir o passado depois - que e como se
    introduz look-ahead bias sem perceber.
    """

    direcao: Direcao
    preco_entrada: float
    tempo_entrada: datetime
    lote: float
    contexto_entrada: dict[str, Any] = field(default_factory=dict)
    # Estado que a propria estrategia atualiza a cada candle (ex: nivel do
    # trailing stop). Fica aqui para a estrategia nao guardar estado por
    # posicao em si mesma, o que quebraria se houvesse mais de uma posicao.
    estado: dict[str, Any] = field(default_factory=dict)

    def resultado_em_pontos(self, preco_saida: float) -> float:
        """Resultado bruto em pontos de indice, sem custos."""
        return (preco_saida - self.preco_entrada) * self.direcao.multiplicador


@dataclass(frozen=True)
class DecisaoSaida:
    """Resposta da estrategia sobre encerrar (ou nao) uma posicao."""

    sair: bool
    motivo: str = ""
    # Preco sugerido de saida. None = o engine usa o fechamento do candle.
    # Serve para alvos que sao atingidos DENTRO do candle (ex: Fibonacci):
    # sair no fechamento nesse caso inventaria lucro que nao existiu.
    preco_sugerido: float | None = None


class Estrategia(ABC):
    """Contrato de toda estrategia.

    Regras que valem para qualquer implementacao:

    1. `on_candle` e `deve_sair` recebem candles em ordem cronologica e so
       podem usar o que ja viram. Olhar para frente e o erro que transforma
       backtest ruim em backtest maravilhoso.
    2. Nenhum parametro pode estar escrito no codigo. Tudo vem do config.
    3. A estrategia nao sabe de onde vem o candle (arquivo ou MT5 ao vivo) e
       nao sabe como a ordem e executada. Ela so decide.
    """

    nome: str = "estrategia"

    @abstractmethod
    def on_candle(self, candle: Candle) -> Sinal:
        """Decide se abre posicao ao fechar este candle.

        Chamado para TODO candle, inclusive com posicao aberta - assim a
        estrategia mantem seus indicadores atualizados sem depender de o engine
        lembrar de alimenta-la. Se ja existe posicao, o engine ignora o sinal.
        """

    @abstractmethod
    def deve_sair(self, posicao: Posicao, candle: Candle) -> DecisaoSaida:
        """Decide se encerra a posicao aberta neste candle."""

    def contexto_atual(self) -> dict[str, Any]:
        """Fotografia do estado dos indicadores agora.

        O engine grava isso junto de cada trade. E a materia-prima das features
        da Etapa 4 - sem isso, treinar o modelo exigiria recalcular indicadores
        depois, que e onde o look-ahead costuma entrar de contrabando.
        """
        return {}

    def pronta(self) -> bool:
        """A estrategia ja tem historico suficiente para decidir?

        Enquanto for False o engine ignora sinais. Evita operar nos primeiros
        candles, quando as medias ainda estao se formando com meia janela.
        """
        return True
