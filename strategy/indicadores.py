"""
Indicadores incrementais.

"Incremental" e o ponto: cada indicador recebe um valor por vez e atualiza seu
estado em tempo constante, sem nunca enxergar a serie inteira. Isso nao e
otimizacao - e a garantia estrutural de que nao existe look-ahead bias. Um
indicador que so conhece o que ja recebeu nao tem como espiar o futuro, mesmo
que alguem escreva a chamada errada no engine.

Efeito colateral util: o mesmo objeto serve para o backtest e para a operacao
ao vivo, onde os candles chegam um a um de qualquer jeito.
"""

from __future__ import annotations

from collections import deque


class MediaMovel:
    """Media movel simples sobre uma janela deslizante.

    Mantem a soma corrente em vez de somar a janela toda a cada candle: com
    27.000 candles e varias combinacoes de parametro no grid search da Etapa 4,
    a diferenca deixa de ser academica.
    """

    def __init__(self, periodo: int):
        if periodo < 1:
            raise ValueError(f"Periodo da media deve ser >= 1, recebi {periodo}")
        self.periodo = periodo
        self._janela: deque[float] = deque(maxlen=periodo)
        self._soma = 0.0

    def atualizar(self, valor: float) -> float | None:
        """Adiciona um valor e devolve a media, ou None se ainda nao encheu."""
        if len(self._janela) == self.periodo:
            self._soma -= self._janela[0]      # sai o mais antigo (deque corta)
        self._janela.append(valor)
        self._soma += valor
        return self.valor

    @property
    def valor(self) -> float | None:
        """Media atual, ou None enquanto a janela nao estiver cheia.

        None em vez de uma media parcial e proposital: media de 3 candles num
        periodo de 20 nao e um canal, e um numero que parece um canal.
        """
        if len(self._janela) < self.periodo:
            return None
        return self._soma / self.periodo

    @property
    def cheia(self) -> bool:
        return len(self._janela) == self.periodo

    def __len__(self) -> int:
        return len(self._janela)


class ATR:
    """Average True Range - medida de volatilidade.

    Nao entra na decisao da estrategia base. Existe porque a Etapa 4 precisa
    dele como feature de contexto ("a estrategia perde em baixa volatilidade?")
    e porque o stop catastrofico opcional e definido em multiplos de ATR.
    """

    def __init__(self, periodo: int):
        self.periodo = periodo
        self._media = MediaMovel(periodo)
        self._fechamento_anterior: float | None = None

    def atualizar(self, maxima: float, minima: float, fechamento: float) -> float | None:
        # True Range considera o gap desde o fechamento anterior, e nao apenas a
        # amplitude do candle - senao um gap de abertura aparece como calmaria.
        if self._fechamento_anterior is None:
            tr = maxima - minima
        else:
            tr = max(maxima - minima,
                     abs(maxima - self._fechamento_anterior),
                     abs(minima - self._fechamento_anterior))
        self._fechamento_anterior = fechamento
        return self._media.atualizar(tr)

    @property
    def valor(self) -> float | None:
        return self._media.valor

    @property
    def cheia(self) -> bool:
        return self._media.cheia


class Extremo:
    """Maximo ou minimo de uma janela deslizante (canal de Donchian classico).

    Alternativa ao canal por media, exposta em config para a Etapa 4 poder
    comparar as duas formulacoes com o mesmo engine.
    """

    def __init__(self, periodo: int, maior: bool):
        self.periodo = periodo
        self.maior = maior
        self._janela: deque[float] = deque(maxlen=periodo)

    def atualizar(self, valor: float) -> float | None:
        self._janela.append(valor)
        return self.valor

    @property
    def valor(self) -> float | None:
        if len(self._janela) < self.periodo:
            return None
        return max(self._janela) if self.maior else min(self._janela)

    @property
    def cheia(self) -> bool:
        return len(self._janela) == self.periodo
