"""
Tipos de stop.

Separado da estrategia de propósito: a estrategia decide QUANDO entrar e quando
o movimento acabou; o stop decide ate onde aceitar estar errado. Sao perguntas
diferentes e conviria poder trocar uma sem mexer na outra.

Onde cada um coloca a ordem na mesa (exemplo de COMPRA):

    atr             entrada - N x ATR
                    Distancia proporcional a volatilidade do momento. Se ajusta
                    sozinho ao horario: as 09:30 o ATR e 3x maior que as 16:00.

    candle_entrada  minima do candle que gerou o sinal - folga
                    O classico de leitura de grafico. Se o preco voltar abaixo
                    do candle que rompeu, o rompimento falhou.

    canal_externo   banda oposta do canal no momento da entrada - folga
                    Coloca o stop FORA da caixa: enquanto o preco estiver dentro
                    ou acima do canal, a tese segue de pe.

    trailing_forca  entrada - N x ATR, e dai em diante acompanha o preco
                    mantendo a mesma distancia, sem nunca afrouxar. Com
                    breakeven opcional: depois de X ATR de lucro, o stop vai
                    para o preco de entrada e o trade deixa de poder perder.

Nenhum deles fica em "sair no maximo": todos existem para limitar a perda. O
estudo mostrou que cortar ganho cedo destroi a estrategia - os 10 melhores
trades sustentam todo o resultado.
"""

from __future__ import annotations

from enum import Enum

from strategy.base import Candle, Direcao, Posicao


class TipoStop(Enum):
    NENHUM = "nenhum"
    ATR = "atr"
    CANDLE_ENTRADA = "candle_entrada"
    CANAL_EXTERNO = "canal_externo"
    TRAILING_FORCA = "trailing_forca"


class Stop:
    """Calcula e mantem o nivel de stop de uma posicao."""

    def __init__(self, tipo: str, mult_atr: float = 2.5, folga_atr: float = 0.25,
                 breakeven_apos_atr: float | None = None):
        self.tipo = TipoStop(tipo)
        self.mult_atr = mult_atr
        self.folga_atr = folga_atr
        # None desliga o breakeven. Com valor, o stop vai para o preco de
        # entrada assim que o trade acumular esse tanto de ATR a favor.
        self.breakeven_apos_atr = breakeven_apos_atr

    @property
    def ativo(self) -> bool:
        return self.tipo is not TipoStop.NENHUM

    # ------------------------------------------------------------ abertura

    def nivel_inicial(self, posicao: Posicao, candle_entrada: Candle,
                      atr: float | None, canal_oposto: float | None) -> float | None:
        """Onde a ordem de stop entra na mesa, no momento da abertura."""
        if not self.ativo or not atr:
            return None
        mult = posicao.direcao.multiplicador
        entrada = posicao.preco_entrada

        if self.tipo in (TipoStop.ATR, TipoStop.TRAILING_FORCA):
            return entrada - mult * self.mult_atr * atr

        if self.tipo is TipoStop.CANDLE_ENTRADA:
            # Extremo contrario do candle que gerou o sinal, com uma folga para
            # o preco nao encostar de raspao e derrubar a posicao.
            extremo = (candle_entrada.minima if posicao.direcao is Direcao.COMPRADO
                       else candle_entrada.maxima)
            return extremo - mult * self.folga_atr * atr

        if self.tipo is TipoStop.CANAL_EXTERNO:
            if canal_oposto is None:
                return None
            return canal_oposto - mult * self.folga_atr * atr

        return None

    # ------------------------------------------------------------ evolucao

    def atualizar(self, posicao: Posicao, candle: Candle,
                  atr: float | None) -> float | None:
        """Reposiciona o stop a cada candle. Ele so anda a favor, nunca contra."""
        nivel = posicao.estado.get("nivel_stop")
        if nivel is None or not atr:
            return nivel

        mult = posicao.direcao.multiplicador
        comprado = posicao.direcao is Direcao.COMPRADO
        novo = nivel

        if self.tipo is TipoStop.TRAILING_FORCA:
            # Acompanha o extremo favoravel do candle mantendo a distancia.
            referencia = candle.maxima if comprado else candle.minima
            candidato = referencia - mult * self.mult_atr * atr
            novo = max(nivel, candidato) if comprado else min(nivel, candidato)

        if self.breakeven_apos_atr is not None:
            lucro = (candle.fechamento - posicao.preco_entrada) * mult
            if lucro >= self.breakeven_apos_atr * atr:
                entrada = posicao.preco_entrada
                novo = max(novo, entrada) if comprado else min(novo, entrada)
                posicao.estado["breakeven_acionado"] = True

        posicao.estado["nivel_stop"] = novo
        return novo

    # ------------------------------------------------------------ disparo

    @staticmethod
    def foi_atingido(posicao: Posicao, candle: Candle, nivel: float | None) -> bool:
        if nivel is None:
            return False
        if posicao.direcao is Direcao.COMPRADO:
            return candle.minima <= nivel
        return candle.maxima >= nivel

    @staticmethod
    def preco_de_execucao(posicao: Posicao, candle: Candle, nivel: float) -> float:
        """Onde o stop realmente e executado.

        Stop garante execucao, nao preco. Se o candle ABRE alem do nivel, a
        ordem sai na abertura. Assumir preenchimento no nivel exato inflava o
        resultado desta estrategia de fator 1.12 para 1.39 - mais da metade do
        ganho era ficcao de execucao.
        """
        if posicao.direcao is Direcao.COMPRADO:
            return min(nivel, candle.abertura)
        return max(nivel, candle.abertura)
