"""
Backtest de CARTEIRA.

O engine da Etapa 3 mede um ativo por vez com lote fixo. Isso serve para
estudar uma estrategia, mas nao descreve o que acontece numa conta - e trend
following so faz sentido medido em carteira, porque a promessa dele nao e
acertar um mercado, e que a soma de muitas apostas independentes tenha
esperanca positiva.

Duas diferencas que mudam o resultado, nao so a apresentacao:

1. DIMENSIONAMENTO POR RISCO, nao lote fixo.
   O tamanho da posicao sai de quanto se aceita perder se o stop for atingido:

       tamanho = (risco em dolares) / (distancia ate o stop x valor do ponto)

   Assim um mercado volatil entra pequeno e um calmo entra grande, e todos
   arriscam o mesmo. Com lote fixo, a prata sozinha carregaria o resultado
   inteiro da carteira - para o bem e para o mal.

2. LOTE MINIMO E RESTRICAO REAL.
   Se a conta e pequena, o tamanho calculado pode ficar ABAIXO do lote minimo
   da corretora. Nesse caso ha duas saidas honestas: nao operar, ou operar o
   minimo e aceitar risco maior que o planejado. As duas sao contabilizadas
   separadamente, porque e exatamente aqui que uma conta pequena deixa de
   conseguir executar a estrategia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from strategy.base import Candle, Direcao, Sinal


@dataclass
class Especificacao:
    """O que o backtest precisa saber de um mercado para dimensionar posicao."""

    nome: str
    usd_por_ponto_lote: float   # quanto vale 1.0 de preco, por 1 lote, em USD
    spread: float               # em unidades de preco
    lote_minimo: float
    passo_lote: float
    swap_compra: float = 0.0    # em unidades de preco, por noite, por lote
    swap_venda: float = 0.0


@dataclass
class TradeCarteira:
    mercado: str
    direcao: str
    entrada: date
    saida: date
    preco_entrada: float
    preco_saida: float
    lote: float
    risco_planejado: float
    motivo: str
    resultado_usd: float
    dias: int
    lote_abaixo_do_minimo: bool


@dataclass
class ResultadoCarteira:
    trades: list[TradeCarteira] = field(default_factory=list)
    patrimonio: pd.Series | None = None
    sinais_recusados_por_lote: int = 0
    sinais_recusados_por_margem: int = 0
    sinais_gerados: int = 0

    @property
    def quadro(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.__dict__ for t in self.trades])


class BacktestCarteira:
    """Roda a mesma estrategia em varios mercados sobre um calendario comum."""

    def __init__(self, criar_estrategia, especificacoes: dict[str, Especificacao],
                 capital_inicial: float = 10_000.0,
                 risco_por_trade: float = 0.01,
                 slippage_em_atr: float = 0.05,
                 comissao_por_lote: float = 0.1,
                 aceitar_lote_minimo: bool = True,
                 max_posicoes: int | None = None):
        self.criar_estrategia = criar_estrategia
        self.specs = especificacoes
        self.capital_inicial = capital_inicial
        self.risco_por_trade = risco_por_trade
        self.slippage_em_atr = slippage_em_atr
        self.comissao_por_lote = comissao_por_lote
        # Quando o tamanho calculado fica abaixo do lote minimo: operar o
        # minimo (aceitando risco maior) ou desistir do trade.
        self.aceitar_lote_minimo = aceitar_lote_minimo
        self.max_posicoes = max_posicoes

    # ------------------------------------------------------------ auxiliar

    def _tamanho(self, equity: float, distancia_stop: float,
                 spec: Especificacao) -> tuple[float, bool]:
        """(lote, ficou_abaixo_do_minimo)."""
        risco_usd = equity * self.risco_por_trade
        valor_do_stop = distancia_stop * spec.usd_por_ponto_lote
        if valor_do_stop <= 0:
            return 0.0, False
        bruto = risco_usd / valor_do_stop
        passo = spec.passo_lote or spec.lote_minimo
        lote = np.floor(bruto / passo) * passo
        if lote < spec.lote_minimo:
            return (spec.lote_minimo, True) if self.aceitar_lote_minimo else (0.0, True)
        return float(lote), False

    # --------------------------------------------------------------- laco

    def rodar(self, dados: dict[str, pd.DataFrame]) -> ResultadoCarteira:
        # Calendario comum: a uniao de todas as datas, em ordem. Mercados com
        # feriados diferentes simplesmente nao produzem candle naquele dia.
        datas = sorted({d for df in dados.values()
                        for d in df["tempo_ativo"].dt.date})
        por_mercado = {m: df.set_index(df["tempo_ativo"].dt.date)
                       for m, df in dados.items()}
        estrategias = {m: self.criar_estrategia() for m in dados}
        abertas: dict[str, dict] = {}

        res = ResultadoCarteira()
        equity = self.capital_inicial
        curva = []

        for dia in datas:
            # --- 1. atualiza posicoes abertas e fecha o que tiver de fechar ---
            for mercado in list(abertas):
                if dia not in por_mercado[mercado].index:
                    continue
                linha = por_mercado[mercado].loc[dia]
                if isinstance(linha, pd.DataFrame):
                    linha = linha.iloc[0]
                candle = self._candle(linha)
                pos = abertas[mercado]
                e, spec = estrategias[mercado], self.specs[mercado]

                fechou, preco, motivo = self._avaliar_saida(e, pos, candle)
                if fechou:
                    equity += self._encerrar(res, pos, mercado, spec, dia,
                                             preco, motivo)
                    del abertas[mercado]

            # --- 2. alimenta todas as estrategias e coleta sinais ---
            for mercado, e in estrategias.items():
                if dia not in por_mercado[mercado].index:
                    continue
                linha = por_mercado[mercado].loc[dia]
                if isinstance(linha, pd.DataFrame):
                    linha = linha.iloc[0]
                candle = self._candle(linha)
                sinal = e.on_candle(candle)

                if sinal is Sinal.NENHUM or mercado in abertas:
                    continue
                if self.max_posicoes and len(abertas) >= self.max_posicoes:
                    continue

                res.sinais_gerados += 1
                atr = getattr(e, "atr_atual", None)
                if not atr:
                    continue
                distancia = e.stop.mult_atr * atr
                spec = self.specs[mercado]
                lote, abaixo = self._tamanho(equity, distancia, spec)
                if lote <= 0:
                    res.sinais_recusados_por_lote += 1
                    continue

                direcao = (Direcao.COMPRADO if sinal is Sinal.COMPRA
                           else Direcao.VENDIDO)
                mult = direcao.multiplicador
                custo_entrada = spec.spread / 2 + self.slippage_em_atr * atr
                preco_entrada = candle.fechamento + mult * custo_entrada

                abertas[mercado] = {
                    "direcao": direcao, "preco": preco_entrada, "lote": lote,
                    "entrada": dia, "nivel_stop": preco_entrada - mult * distancia,
                    "atr": atr, "abaixo_minimo": abaixo,
                    "risco": lote * distancia * spec.usd_por_ponto_lote,
                }

            curva.append({"dia": dia, "patrimonio": equity,
                          "posicoes": len(abertas)})

        res.patrimonio = pd.DataFrame(curva).set_index("dia")
        return res

    # ------------------------------------------------------------ internos

    @staticmethod
    def _candle(linha) -> Candle:
        return Candle(tempo=linha["tempo_ativo"], abertura=float(linha["abertura"]),
                      maxima=float(linha["maxima"]), minima=float(linha["minima"]),
                      fechamento=float(linha["fechamento"]),
                      volume=float(linha.get("volume_ticks", 0)))

    def _avaliar_saida(self, estrategia, pos: dict, candle: Candle):
        """Stop primeiro: dentro de um dia ele e o evento mais proximo."""
        comprado = pos["direcao"] is Direcao.COMPRADO
        nivel = pos["nivel_stop"]
        tocou = candle.minima <= nivel if comprado else candle.maxima >= nivel
        if tocou:
            # Stop garante execucao, nao preco: gap de abertura sai na abertura.
            preco = min(nivel, candle.abertura) if comprado else max(nivel, candle.abertura)
            return True, preco, "stop"

        from strategy.base import Posicao
        fake = Posicao(direcao=pos["direcao"], preco_entrada=pos["preco"],
                       tempo_entrada=candle.tempo, lote=pos["lote"])
        d = estrategia.deve_sair(fake, candle)
        if d.sair:
            return True, (d.preco_sugerido or candle.fechamento), d.motivo
        return False, None, ""

    def _encerrar(self, res: ResultadoCarteira, pos: dict, mercado: str,
                  spec: Especificacao, dia, preco_bruto: float, motivo: str) -> float:
        mult = pos["direcao"].multiplicador
        custo_saida = spec.spread / 2 + self.slippage_em_atr * pos["atr"]
        preco_saida = preco_bruto - mult * custo_saida

        pontos = (preco_saida - pos["preco"]) * mult
        noites = (dia - pos["entrada"]).days
        swap = (spec.swap_compra if pos["direcao"] is Direcao.COMPRADO
                else spec.swap_venda) * noites
        resultado = ((pontos + swap) * spec.usd_por_ponto_lote * pos["lote"]
                     - self.comissao_por_lote * pos["lote"])

        res.trades.append(TradeCarteira(
            mercado=mercado, direcao=pos["direcao"].value, entrada=pos["entrada"],
            saida=dia, preco_entrada=pos["preco"], preco_saida=preco_saida,
            lote=pos["lote"], risco_planejado=pos["risco"], motivo=motivo,
            resultado_usd=resultado, dias=noites,
            lote_abaixo_do_minimo=pos["abaixo_minimo"]))
        return resultado
