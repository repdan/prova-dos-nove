"""
Motor de backtest event-driven.

Processa um candle por vez, em ordem cronologica, decidindo com o que existia
naquele instante. Nao ha DataFrame inteiro visivel, nao ha operacao vetorizada
sobre o futuro, nao ha "olhar o proximo candle para saber o que fazer neste".

O laco e deliberadamente curto. Toda a inteligencia mora na estrategia; todo o
custo mora no executor; toda a leitura mora no feed. O motor so orquestra - e
essa e a razao de a Etapa 4 poder trocar o modo de saida sem tocar aqui.

ORDEM DAS CHAMADAS, e por que ela importa:
  1. contexto.observar(candle)      - atualiza o que se sabe do dia
  2. executor.acompanhar(posicao)   - registra excursoes da posicao aberta
  3. estrategia.deve_sair(...)      - decide saida ANTES de a estrategia
                                      absorver o candle nos indicadores
  4. estrategia.on_candle(candle)   - decide entrada e so entao absorve
Inverter 3 e 4 faria o candle atual participar do canal que ele mesmo rompe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backtest.contexto_diario import ContextoDiario
from backtest.executor import ExecutorSimulado, Trade
from backtest.feed import DataFeed, FeedParquet, ResolvedorIntrabar
from strategy.base import Candle, Direcao, Estrategia, Sinal


@dataclass
class ResultadoBacktest:
    trades: list[Trade] = field(default_factory=list)
    candles_processados: int = 0
    sinais_gerados: int = 0
    sinais_ignorados_posicao_aberta: int = 0
    fechamentos_por_fim_de_pregao: int = 0
    stops_da_estrategia: int = 0
    inversoes_forcadas: int = 0
    inversoes_bloqueadas: int = 0
    stops_catastroficos: int = 0
    desempates_intrabar: int = 0
    parametros: dict[str, Any] = field(default_factory=dict)

    @property
    def quadro(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.como_dict() for t in self.trades])


class Motor:
    """Orquestra feed, estrategia e executor. Nao decide nada sozinho."""

    def __init__(self, estrategia: Estrategia, executor: ExecutorSimulado,
                 contexto: ContextoDiario | None = None,
                 resolvedor: ResolvedorIntrabar | None = None,
                 minutos_por_candle: int = 15,
                 fechar_no_fim_do_pregao: bool = False,
                 stop_catastrofico_ativo: bool = False,
                 stop_catastrofico_atr: float = 3.0,
                 permitir_simultaneas: bool = False,
                 politica_inversao: str = "regra"):
        self.estrategia = estrategia
        self.executor = executor
        self.contexto = contexto
        self.resolvedor = resolvedor
        self.minutos_por_candle = minutos_por_candle
        self.fechar_no_fim_do_pregao = fechar_no_fim_do_pregao
        self.stop_catastrofico_ativo = stop_catastrofico_ativo
        self.stop_catastrofico_atr = stop_catastrofico_atr
        # Com posicoes simultaneas o motor deixa de simular uma conta e passa a
        # simular cada sinal isoladamente. Util para pesquisa, invalido para
        # medir patrimonio - por isso e explicito e nunca o padrao.
        self.permitir_simultaneas = permitir_simultaneas
        if politica_inversao not in ("regra", "sempre", "nunca"):
            raise ValueError(
                f"politica_inversao invalida: {politica_inversao!r}. "
                "Use 'regra', 'sempre' ou 'nunca'.")
        self.politica_inversao = politica_inversao

    def rodar(self, feed: DataFeed) -> ResultadoBacktest:
        resultado = ResultadoBacktest(parametros={
            "estrategia": self.estrategia.nome,
            "modo_saida": getattr(self.estrategia, "modo_saida", None)
                          and self.estrategia.modo_saida.value,
            "periodo_canal": getattr(self.estrategia, "periodo_canal", None),
            "lote": getattr(self.estrategia, "lote", None),
            "fechar_no_fim_do_pregao": self.fechar_no_fim_do_pregao,
            "politica_inversao": self.politica_inversao,
            "stop_catastrofico_ativo": self.stop_catastrofico_ativo,
            "feed": feed.descricao,
        })

        abertas: list = []
        candle_anterior: Candle | None = None

        for candle in feed:
            resultado.candles_processados += 1

            if self.contexto is not None:
                self.contexto.observar(candle)

            # --- virada de pregao: fecha as posicoes antes de o dia mudar ---
            if (abertas and self.fechar_no_fim_do_pregao
                    and candle_anterior is not None
                    and candle.tempo.date() != candle_anterior.tempo.date()):
                for posicao in abertas:
                    self.executor.fechar(posicao, candle_anterior, "fim_do_pregao")
                    resultado.fechamentos_por_fim_de_pregao += 1
                abertas = []

            # --- posicoes abertas: acompanhar e avaliar saida ---
            sobreviventes, encerradas = [], []
            for posicao in abertas:
                self.executor.acompanhar(posicao, candle)
                if self._avaliar_saida(posicao, candle, resultado):
                    encerradas.append(posicao)
                else:
                    sobreviventes.append(posicao)
            abertas = sobreviventes

            # --- sempre alimenta a estrategia, mesmo com posicao aberta ---
            sinal = self.estrategia.on_candle(candle)

            # A politica de inversao age SOBRE o sinal da estrategia, nunca
            # dentro dela: a estrategia continua sendo a mesma nas tres
            # variantes, o que muda e o que se faz com o sinal.
            if encerradas and not self.permitir_simultaneas:
                if self.politica_inversao == "nunca" and sinal is not Sinal.NENHUM:
                    resultado.inversoes_bloqueadas += 1
                    sinal = Sinal.NENHUM
                elif self.politica_inversao == "sempre" and sinal is Sinal.NENHUM:
                    # Inverte o lado da posicao que acabou de fechar.
                    fechada = encerradas[-1]
                    sinal = (Sinal.VENDA if fechada.direcao is Direcao.COMPRADO
                             else Sinal.COMPRA)
                    resultado.inversoes_forcadas += 1

            if sinal is not Sinal.NENHUM:
                resultado.sinais_gerados += 1
                if abertas and not self.permitir_simultaneas:
                    resultado.sinais_ignorados_posicao_aberta += 1
                else:
                    abertas.append(self._abrir(sinal, candle))

            candle_anterior = candle

        # Posicao ainda aberta no fim da base nao vira trade: contabiliza-la
        # com preco do ultimo candle inventaria um encerramento que o mercado
        # nao deu. Fica de fora, e o relatorio informa.
        resultado.trades = list(self.executor.trades)
        return resultado

    # ---------------------------------------------------------------- interno

    def _abrir(self, sinal: Sinal, candle: Candle):
        direcao = Direcao.COMPRADO if sinal is Sinal.COMPRA else Direcao.VENDIDO

        ctx: dict[str, Any] = dict(self.estrategia.contexto_atual())
        if self.contexto is not None:
            ordem = self.contexto.registrar_sinal()
            ctx.update(self.contexto.contexto(candle, ordem))

        posicao = self.executor.abrir(direcao, candle, self.estrategia.lote, ctx)
        armar = getattr(self.estrategia, "armar_stop", None)
        if armar is not None:
            armar(posicao, candle)
        return posicao

    def _nivel_stop_catastrofico(self, posicao) -> float | None:
        """Rede de seguranca opcional, desligada por padrao.

        A estrategia base nao tem stop - e essa e a regra que o projeto quer
        medir. Este stop existe para responder "quanto custaria ter um limite?"
        sem alterar o baseline. Em multiplos de ATR, nunca fixo: a analise da
        abertura mostrou que a volatilidade das 09:30 e 3x a da tarde, entao um
        stop fixo seria apertado demais cedo e frouxo demais tarde.
        """
        if not self.stop_catastrofico_ativo:
            return None
        atr = self.estrategia.contexto_atual().get("atr")
        if not atr:
            return None
        mult = posicao.direcao.multiplicador
        return posicao.preco_entrada - mult * (self.stop_catastrofico_atr * atr)

    @staticmethod
    def _preco_real_do_stop(candle: Candle, nivel: float, comprado: bool) -> float:
        """Onde o stop REALMENTE seria executado.

        Um stop nao garante preco, garante execucao. Se o candle abre alem do
        nivel - gap de abertura, noticia, virada de pregao - a ordem e
        executada na abertura, nao no nivel. Assumir preenchimento no preco
        exato faz o stop parecer melhor do que e, e o erro cresce justamente
        nos momentos em que ele mais importa.
        """
        if comprado:
            return min(nivel, candle.abertura)
        return max(nivel, candle.abertura)

    def _avaliar_saida(self, posicao, candle: Candle,
                       resultado: ResultadoBacktest) -> bool:
        """Decide e executa a saida. Devolve True se a posicao foi fechada.

        O caso delicado e quando DOIS niveis de saida caem dentro do mesmo
        candle - tipicamente um alvo de Fibonacci e o stop catastrofico. O M15
        informa a maxima e a minima, mas nao a ordem entre elas. Escolher a
        ordem no chute e, na pratica, escolher a favor: e assim que um backtest
        vira propaganda. Quando ha M5 disponivel, o desempate vem do dado.
        """
        comprado = posicao.direcao is Direcao.COMPRADO
        nivel_stop = self._nivel_stop_catastrofico(posicao)
        stop_tocado = nivel_stop is not None and (
            candle.minima <= nivel_stop if comprado else candle.maxima >= nivel_stop)

        # O stop da estrategia e avaliado PRIMEIRO: dentro de um candle ele e
        # o evento mais proximo do preco de entrada, entao acontece antes.
        checar = getattr(self.estrategia, "checar_stop", None)
        if checar is not None:
            d_stop = checar(posicao, candle)
            if d_stop.sair:
                resultado.stops_da_estrategia += 1
                self.executor.fechar(posicao, candle, d_stop.motivo,
                                     d_stop.preco_sugerido)
                return True

        decisao = self.estrategia.deve_sair(posicao, candle)
        alvo = decisao.preco_sugerido if decisao.sair else None

        # Caso simples: so o stop dispara.
        if stop_tocado and alvo is None:
            resultado.stops_catastroficos += 1
            self.executor.fechar(posicao, candle, "stop_catastrofico",
                                 self._preco_real_do_stop(candle, nivel_stop, comprado))
            return True

        # Caso delicado: os dois niveis estao dentro do mesmo candle.
        if stop_tocado and alvo is not None:
            primeiro = None
            if self.resolvedor is not None:
                resultado.desempates_intrabar += 1
                primeiro = self.resolvedor.qual_veio_primeiro(
                    candle, self.minutos_por_candle,
                    nivel_a=alvo, sobe_a=comprado,
                    nivel_b=nivel_stop, sobe_b=not comprado)
            # Sem M5 para desempatar, assume o stop - o pior caso para quem
            # esta posicionado. Nunca o contrario.
            if primeiro == "a":
                self.executor.fechar(posicao, candle, decisao.motivo, alvo)
            else:
                resultado.stops_catastroficos += 1
                self.executor.fechar(posicao, candle, "stop_catastrofico",
                                     self._preco_real_do_stop(candle, nivel_stop, comprado))
            return True

        if decisao.sair:
            self.executor.fechar(posicao, candle, decisao.motivo, alvo)
            return True
        return False


def montar_do_config(cfg, caminho_pregao=None, caminho_menor=None,
                     modo_saida=None, periodo_canal=None,
                     prever_probabilidade=None, inicio=None, fim=None):
    """Monta feed, estrategia, executor e motor a partir do config.

    Ponto unico de montagem: a Etapa 4 varre parametros chamando esta funcao
    com sobrescritas, sem duplicar a fiacao em cada experimento.
    """
    from strategy.canal_rompimento import CanalRompimento

    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    caminho_pregao = caminho_pregao or (pasta / "HK50_M15_pregao.parquet")
    feed = FeedParquet(caminho_pregao, inicio=inicio, fim=fim)

    resolvedor = None
    if caminho_menor is None:
        candidato = pasta / "HK50_M5_pregao.parquet"
        caminho_menor = candidato if candidato.exists() else None
    if caminho_menor is not None:
        resolvedor = ResolvedorIntrabar(caminho_menor, minutos_menor=5)

    bruto = pasta / "HK50_M15_bruto.parquet"
    contexto = ContextoDiario(
        feed.quadro,
        pd.read_parquet(bruto) if bruto.exists() else None,
    )

    estrategia = CanalRompimento(
        periodo_canal=periodo_canal or cfg.exigir("estrategia.periodo_canal"),
        modo_saida=modo_saida or cfg.exigir("estrategia.modo_saida"),
        lote=cfg.exigir("estrategia.lote"),
        fibo_nivel=cfg.get("estrategia.fibo_nivel", 2.0),
        ml_limiar_saida=cfg.get("estrategia.ml_limiar_saida", 0.45),
        tipo_canal=cfg.get("estrategia.tipo_canal", "media"),
        preco_referencia=cfg.get("estrategia.preco_referencia", "fechamento"),
        periodo_atr=cfg.get("estrategia.periodo_atr", 14),
        filtro_volume_ativo=cfg.get("estrategia.filtro_volume_ativo", False),
        filtro_volume_janela=cfg.get("estrategia.filtro_volume_janela", 100),
        filtro_volume_limiar=cfg.get("estrategia.filtro_volume_limiar", 0.88),
        tipo_stop=cfg.get("estrategia.tipo_stop", "nenhum"),
        stop_mult_atr=cfg.get("estrategia.stop_mult_atr", 2.5),
        stop_folga_atr=cfg.get("estrategia.stop_folga_atr", 0.25),
        stop_breakeven_atr=cfg.get("estrategia.stop_breakeven_atr"),
        prever_probabilidade=prever_probabilidade,
    )

    executor = ExecutorSimulado(
        spread_padrao=cfg.exigir("custos.spread_indice"),
        slippage=cfg.get("custos.slippage_indice", 0.5),
        comissao_por_lote=cfg.get("custos.comissao_por_lote", 0.0),
        valor_ponto_por_lote=cfg.exigir("custos.valor_ponto_por_lote"),
        swap_compra=cfg.get("custos.swap_compra_indice", 0.0),
        swap_venda=cfg.get("custos.swap_venda_indice", 0.0),
        dia_swap_triplo=cfg.get("custos.dia_swap_triplo", 4),
        spread_forcado=cfg.get("custos.spread_forcado"),
    )

    motor = Motor(
        estrategia, executor, contexto, resolvedor,
        fechar_no_fim_do_pregao=cfg.get("backtest.fechar_no_fim_do_pregao", False),
        politica_inversao=cfg.get("backtest.politica_inversao", "regra"),
        stop_catastrofico_ativo=cfg.get("estrategia.stop_catastrofico_ativo", False),
        stop_catastrofico_atr=cfg.get("estrategia.stop_catastrofico_atr", 3.0),
    )
    return motor, feed
