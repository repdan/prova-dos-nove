"""
Estrategia de rompimento de canal.

O canal e formado por duas medias moveis de mesmo periodo: uma sobre as MAXIMAS
(banda superior) e outra sobre as MINIMAS (banda inferior).

  Nota sobre o nome: isso e parecido com um canal de Donchian, mas nao e igual.
  Donchian usa o MAIOR maximo e o MENOR minimo da janela; aqui e a MEDIA dos
  maximos e a MEDIA dos minimos. O canal por media e mais estreito e reage mais
  rapido. As duas formulacoes estao implementadas e `tipo_canal` escolhe qual
  usar, para a Etapa 4 poder compara-las com o mesmo engine.

ENTRADA (regra dura, nao e parametro)
  So entra quando o preco vai de DENTRO para FORA do canal:
    - candle anterior dentro do canal E candle atual acima da banda superior
      -> COMPRA
    - candle anterior dentro do canal E candle atual abaixo da banda inferior
      -> VENDA
  Preco que ja vinha de fora nunca gera entrada. Isso evita entrar no meio de
  um movimento ja esticado, que e onde o rompimento costuma ja ter acabado.

SAIDA
  Quatro modos, todos sobre a mesma entrada, trocando so um valor no config:
    stop_gain       - baseline: sai ao romper a media oposta do canal
    trailing        - stop que segue o canal e nunca afrouxa
    fibo_expansion  - alvo em N x a largura do canal no momento da entrada
    ml_probabilidade- sai quando o modelo derruba a probabilidade de sucesso
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from strategy.base import Candle, DecisaoSaida, Direcao, Estrategia, Posicao, Sinal
from strategy.indicadores import ATR, Extremo, MediaMovel


class ModoSaida(Enum):
    STOP_GAIN = "stop_gain"
    TRAILING = "trailing"
    FIBO_EXPANSION = "fibo_expansion"
    ML_PROBABILIDADE = "ml_probabilidade"


class PosicaoNoCanal(Enum):
    """Onde o preco de referencia esta em relacao ao canal."""

    DENTRO = "dentro"
    ACIMA = "acima"
    ABAIXO = "abaixo"


@dataclass(frozen=True)
class Canal:
    superior: float
    inferior: float

    @property
    def largura(self) -> float:
        return self.superior - self.inferior

    def onde_esta(self, preco_alto: float, preco_baixo: float) -> PosicaoNoCanal:
        if preco_alto > self.superior:
            return PosicaoNoCanal.ACIMA
        if preco_baixo < self.inferior:
            return PosicaoNoCanal.ABAIXO
        return PosicaoNoCanal.DENTRO


class CanalRompimento(Estrategia):
    """Implementacao concreta da estrategia de rompimento de canal."""

    nome = "canal_rompimento"

    def __init__(
        self,
        periodo_canal: int,
        modo_saida: str,
        lote: float,
        fibo_nivel: float = 2.0,
        ml_limiar_saida: float = 0.45,
        tipo_canal: str = "media",
        preco_referencia: str = "fechamento",
        periodo_atr: int = 14,
        filtro_volume_ativo: bool = False,
        filtro_volume_janela: int = 100,
        filtro_volume_limiar: float = 0.88,
        prever_probabilidade: Callable[[dict[str, Any]], float] | None = None,
    ):
        self.periodo_canal = periodo_canal
        self.modo_saida = ModoSaida(modo_saida)
        self.lote = lote
        self.fibo_nivel = fibo_nivel
        self.ml_limiar_saida = ml_limiar_saida
        self.tipo_canal = tipo_canal
        self.preco_referencia = preco_referencia
        self.filtro_volume_ativo = filtro_volume_ativo
        self.filtro_volume_limiar = filtro_volume_limiar
        # Injetado pela Etapa 4. A estrategia nao sabe o que e um modelo -
        # so sabe pedir um numero entre 0 e 1 para uma funcao qualquer.
        self.prever_probabilidade = prever_probabilidade

        if tipo_canal == "media":
            self._banda_sup: Any = MediaMovel(periodo_canal)
            self._banda_inf: Any = MediaMovel(periodo_canal)
        elif tipo_canal == "donchian":
            self._banda_sup = Extremo(periodo_canal, maior=True)
            self._banda_inf = Extremo(periodo_canal, maior=False)
        else:
            raise ValueError(f"tipo_canal invalido: {tipo_canal!r}. Use 'media' ou 'donchian'.")

        self._atr = ATR(periodo_atr)
        self._media_volume = MediaMovel(filtro_volume_janela)
        # Volume do candle ANTERIOR dividido pela media dos candles que vieram
        # antes DELE. Guardado no momento em que aquele candle foi absorvido -
        # por isso ja esta pronto, e nao contamina a decisao com o candle atual.
        self._volume_relativo: float | None = None

        # Estado entre candles
        self._posicao_anterior: PosicaoNoCanal | None = None
        self._canal_anterior: Canal | None = None
        self._sup_anterior: float | None = None   # para medir inclinacao das bandas
        self._inf_anterior: float | None = None
        self._fechamento_anterior: float | None = None
        self._candles_vistos = 0

        # Cache do canal usado na decisao deste candle. Existe para que
        # on_candle e deve_sair enxerguem exatamente o mesmo canal, na mesma
        # ordem, independentemente de qual o engine chamar primeiro.
        self._cache_tempo: Any = None
        self._cache_canal: Canal | None = None
        self.sinais_recusados_por_volume = 0

    # ------------------------------------------------------------------ util

    def _canal_vigente(self) -> Canal | None:
        """Canal formado pelos candles ANTERIORES ao atual.

        A garantia de nao ter look-ahead esta aqui: este metodo e sempre lido
        ANTES de o candle atual ser absorvido pelos indicadores. O candle que
        rompe o canal nunca participa do calculo do canal que ele rompe.
        """
        sup, inf = self._banda_sup.valor, self._banda_inf.valor
        if sup is None or inf is None:
            return None
        return Canal(superior=sup, inferior=inf)

    def _canal_para(self, candle: Candle) -> Canal | None:
        if self._cache_tempo != candle.tempo:
            self._cache_tempo = candle.tempo
            self._cache_canal = self._canal_vigente()
        return self._cache_canal

    def _volume_aprova(self) -> bool:
        """O volume do candle anterior estava baixo o bastante?

        Enquanto a media de volume nao encheu, o filtro deixa passar: recusar
        sinal por falta de referencia descartaria os primeiros meses da base
        sem motivo nenhum.
        """
        if not self.filtro_volume_ativo:
            return True
        if self._volume_relativo is None:
            return True
        return self._volume_relativo <= self.filtro_volume_limiar

    def _precos_de_referencia(self, candle: Candle) -> tuple[float, float]:
        """(preco para testar rompimento pra cima, idem pra baixo).

        'fechamento' e a leitura conservadora: exige que o candle FECHE fora do
        canal. 'extremo' aceita o rompimento por pavio, o que gera mais sinais
        e mais falsos - por isso e configuravel e nao decidido no codigo.
        """
        if self.preco_referencia == "extremo":
            return candle.maxima, candle.minima
        if self.preco_referencia == "fechamento":
            return candle.fechamento, candle.fechamento
        raise ValueError(f"preco_referencia invalido: {self.preco_referencia!r}")

    def _absorver(self, candle: Candle) -> None:
        """Incorpora o candle aos indicadores. Sempre por ultimo."""
        # A media e lida ANTES de receber este candle: assim o volume relativo
        # guardado compara o candle com o passado dele, nunca consigo mesmo.
        media_antes = self._media_volume.valor
        self._volume_relativo = (candle.volume / media_antes
                                 if media_antes else None)
        self._media_volume.atualizar(candle.volume)

        self._sup_anterior = self._banda_sup.valor
        self._inf_anterior = self._banda_inf.valor
        self._banda_sup.atualizar(candle.maxima)
        self._banda_inf.atualizar(candle.minima)
        self._atr.atualizar(candle.maxima, candle.minima, candle.fechamento)
        self._fechamento_anterior = candle.fechamento
        self._candles_vistos += 1

    def pronta(self) -> bool:
        # Uma janela cheia forma o canal; a segunda garante que ja existe um
        # "candle anterior" com posicao conhecida para comparar.
        return self._banda_sup.cheia and self._posicao_anterior is not None

    # -------------------------------------------------------------- entrada

    def on_candle(self, candle: Candle) -> Sinal:
        canal = self._canal_para(candle)
        if canal is None:
            self._absorver(candle)
            return Sinal.NENHUM

        alto, baixo = self._precos_de_referencia(candle)
        posicao_atual = canal.onde_esta(alto, baixo)

        sinal = Sinal.NENHUM
        # A REGRA DURA: so vale rompimento vindo de dentro do canal.
        if self._posicao_anterior is PosicaoNoCanal.DENTRO and self.pronta():
            if posicao_atual is PosicaoNoCanal.ACIMA:
                sinal = Sinal.COMPRA
            elif posicao_atual is PosicaoNoCanal.ABAIXO:
                sinal = Sinal.VENDA

        # O filtro age DEPOIS da regra, nunca no lugar dela: a estrategia
        # continua a mesma, o filtro apenas recusa alguns dos sinais dela.
        if sinal is not Sinal.NENHUM and not self._volume_aprova():
            self.sinais_recusados_por_volume += 1
            sinal = Sinal.NENHUM

        self._canal_anterior = canal
        self._posicao_anterior = posicao_atual
        self._absorver(candle)
        return sinal

    # ---------------------------------------------------------------- saida

    def deve_sair(self, posicao: Posicao, candle: Candle) -> DecisaoSaida:
        canal = self._canal_para(candle)
        if canal is None:
            return DecisaoSaida(sair=False)

        if self.modo_saida is ModoSaida.STOP_GAIN:
            return self._saida_stop_gain(posicao, candle, canal)
        if self.modo_saida is ModoSaida.TRAILING:
            return self._saida_trailing(posicao, candle, canal)
        if self.modo_saida is ModoSaida.FIBO_EXPANSION:
            return self._saida_fibo(posicao, candle, canal)
        return self._saida_ml(posicao, candle, canal)

    def _rompeu_media_oposta(self, posicao: Posicao, candle: Candle,
                             canal: Canal) -> bool:
        """A regra base: comprado sai ao romper a banda inferior, e vice-versa."""
        alto, baixo = self._precos_de_referencia(candle)
        if posicao.direcao is Direcao.COMPRADO:
            return baixo < canal.inferior
        return alto > canal.superior

    def _saida_stop_gain(self, posicao: Posicao, candle: Candle,
                         canal: Canal) -> DecisaoSaida:
        if self._rompeu_media_oposta(posicao, candle, canal):
            return DecisaoSaida(sair=True, motivo="rompimento_media_oposta")
        return DecisaoSaida(sair=False)

    def _saida_trailing(self, posicao: Posicao, candle: Candle,
                        canal: Canal) -> DecisaoSaida:
        """Stop que acompanha o canal e nunca recua.

        Diferenca em relacao ao stop_gain: a banda do canal sobe e desce; aqui
        o nivel so anda a favor da posicao. Um recuo do canal nao devolve o
        lucro que ja foi travado.
        """
        chave = "nivel_trailing"
        atual = posicao.estado.get(chave)
        alvo = canal.inferior if posicao.direcao is Direcao.COMPRADO else canal.superior

        if atual is None:
            posicao.estado[chave] = alvo
        elif posicao.direcao is Direcao.COMPRADO:
            posicao.estado[chave] = max(atual, alvo)
        else:
            posicao.estado[chave] = min(atual, alvo)

        nivel = posicao.estado[chave]
        alto, baixo = self._precos_de_referencia(candle)
        rompeu = baixo < nivel if posicao.direcao is Direcao.COMPRADO else alto > nivel
        if rompeu:
            return DecisaoSaida(sair=True, motivo="trailing_stop")
        return DecisaoSaida(sair=False)

    def _saida_fibo(self, posicao: Posicao, candle: Candle,
                    canal: Canal) -> DecisaoSaida:
        """Alvo de lucro por expansao, com a regra base como stop.

        A perna de referencia e a largura do canal NO MOMENTO DO ROMPIMENTO -
        por isso ela e lida do contexto de entrada e nao recalculada agora.
        Sem o stop base junto, um trade perdedor nunca encontraria a saida.
        """
        largura = posicao.contexto_entrada.get("largura_canal")
        if largura:
            deslocamento = self.fibo_nivel * largura * posicao.direcao.multiplicador
            alvo = posicao.preco_entrada + deslocamento
            # O alvo e atingido DENTRO do candle: sair pelo fechamento aqui
            # inventaria (ou apagaria) lucro que o preco realmente tocou.
            atingiu = (candle.maxima >= alvo if posicao.direcao is Direcao.COMPRADO
                       else candle.minima <= alvo)
            if atingiu:
                return DecisaoSaida(sair=True, motivo="alvo_fibo",
                                    preco_sugerido=alvo)

        if self._rompeu_media_oposta(posicao, candle, canal):
            return DecisaoSaida(sair=True, motivo="rompimento_media_oposta")
        return DecisaoSaida(sair=False)

    def _saida_ml(self, posicao: Posicao, candle: Candle,
                  canal: Canal) -> DecisaoSaida:
        """Sai quando o modelo julga que o trade deixou de ter chance.

        A regra base continua valendo por baixo: o modelo pode antecipar a
        saida, nunca prolonga-la. Assim a comparacao da Etapa 4 mede o efeito
        de sair antes, e nao uma estrategia diferente.
        """
        if self.prever_probabilidade is None:
            raise RuntimeError(
                "modo_saida='ml_probabilidade' exige um modelo ja treinado.\n"
                "A ordem correta e a de duas passadas (Etapa 4):\n"
                "  1. rode a engine com stop_gain/trailing/fibo_expansion para\n"
                "     gerar o historico de trades com contexto, e treine o modelo\n"
                "  2. so entao rode com ml_probabilidade, injetando o modelo em\n"
                "     'prever_probabilidade'\n"
                "Treinar e usar na mesma passada vazaria o futuro para dentro da\n"
                "decisao e o resultado seria fantasia."
            )

        contexto = {**self.contexto_atual(),
                    "pontos_no_trade": posicao.resultado_em_pontos(candle.fechamento),
                    "candles_no_trade": posicao.estado.get("candles", 0)}
        posicao.estado["candles"] = contexto["candles_no_trade"] + 1

        if self.prever_probabilidade(contexto) < self.ml_limiar_saida:
            return DecisaoSaida(sair=True, motivo="ml_probabilidade_baixa")
        if self._rompeu_media_oposta(posicao, candle, canal):
            return DecisaoSaida(sair=True, motivo="rompimento_media_oposta")
        return DecisaoSaida(sair=False)

    # ------------------------------------------------------------- contexto

    def contexto_atual(self) -> dict[str, Any]:
        """Features do momento, gravadas junto de cada trade pela engine."""
        canal = self._canal_vigente()
        if canal is None:
            return {}

        inclinacao_sup = (canal.superior - self._sup_anterior
                          if self._sup_anterior is not None else 0.0)
        inclinacao_inf = (canal.inferior - self._inf_anterior
                          if self._inf_anterior is not None else 0.0)
        return {
            "canal_superior": canal.superior,
            "canal_inferior": canal.inferior,
            "largura_canal": canal.largura,
            "atr": self._atr.valor,
            "inclinacao_canal_superior": inclinacao_sup,
            "inclinacao_canal_inferior": inclinacao_inf,
            "volume_relativo": self._volume_relativo,
            "candles_vistos": self._candles_vistos,
        }


def criar_do_config(cfg, prever_probabilidade=None) -> CanalRompimento:
    """Monta a estrategia a partir do config.yaml. Nada de valor literal aqui."""
    return CanalRompimento(
        periodo_canal=cfg.exigir("estrategia.periodo_canal"),
        modo_saida=cfg.exigir("estrategia.modo_saida"),
        lote=cfg.exigir("estrategia.lote"),
        fibo_nivel=cfg.get("estrategia.fibo_nivel", 2.0),
        ml_limiar_saida=cfg.get("estrategia.ml_limiar_saida", 0.45),
        tipo_canal=cfg.get("estrategia.tipo_canal", "media"),
        preco_referencia=cfg.get("estrategia.preco_referencia", "fechamento"),
        periodo_atr=cfg.get("estrategia.periodo_atr", 14),
        filtro_volume_ativo=cfg.get("estrategia.filtro_volume_ativo", False),
        filtro_volume_janela=cfg.get("estrategia.filtro_volume_janela", 100),
        filtro_volume_limiar=cfg.get("estrategia.filtro_volume_limiar", 0.88),
        prever_probabilidade=prever_probabilidade,
    )
