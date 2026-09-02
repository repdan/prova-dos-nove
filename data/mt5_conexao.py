"""
Conexao com o terminal MetaTrader 5 e descoberta do simbolo.

IMPORTANTE: a biblioteca MetaTrader5 NAO fala com a corretora pela internet.
Ela conversa com o terminal instalado nesta maquina. Consequencia pratica:
o terminal precisa estar ABERTO E LOGADO antes de qualquer script rodar.
Todo o acesso feito aqui e SOMENTE LEITURA - nenhuma ordem e enviada.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import MetaTrader5 as mt5

from configuracao import Config


class ErroMT5(RuntimeError):
    """Falha de conexao ou de consulta ao terminal."""


@dataclass
class EspecificacaoSimbolo:
    """Especificacao do contrato - a base dos custos do backtest."""

    nome: str
    descricao: str
    digitos: int
    ponto: float
    spread_atual_pontos: int
    spread_flutuante: bool
    tamanho_contrato: float
    valor_ponto: float
    volume_minimo: float
    volume_maximo: float
    passo_volume: float
    moeda_lucro: str
    swap_compra: float
    swap_venda: float

    def como_dict(self) -> dict:
        return asdict(self)


def conectar(cfg: Config) -> None:
    """Inicializa a conexao com o terminal. Levanta ErroMT5 se nao conseguir."""
    caminho = cfg.get("mt5.caminho_terminal")

    # initialize() com caminho tenta subir o terminal se ele estiver fechado,
    # mas ele so fica utilizavel se a conta ja estiver logada (credenciais
    # salvas no proprio terminal - este projeto nunca manipula senha).
    ok = mt5.initialize(caminho) if caminho and Path(caminho).exists() else mt5.initialize()

    if not ok:
        codigo, mensagem = mt5.last_error()
        raise ErroMT5(
            f"Nao foi possivel conectar ao MetaTrader 5 (codigo {codigo}: {mensagem}).\n"
            "Checklist:\n"
            "  1. O terminal esta aberto?\n"
            "  2. A conta esta logada (canto inferior direito mostra a conexao)?\n"
            "  3. O caminho em config.yaml (mt5.caminho_terminal) esta correto?"
        )


def desconectar() -> None:
    mt5.shutdown()


def info_terminal() -> dict:
    """Dados do terminal e da conta conectada, para registrar no relatorio."""
    terminal = mt5.terminal_info()
    conta = mt5.account_info()
    return {
        "terminal_build": getattr(terminal, "build", None),
        "terminal_conectado": getattr(terminal, "connected", None),
        "trade_permitido": getattr(terminal, "trade_allowed", None),
        "servidor": getattr(conta, "server", None),
        "moeda_conta": getattr(conta, "currency", None),
        "tipo_conta": "DEMO" if getattr(conta, "trade_mode", None) == 0 else "REAL/OUTRO",
        # O numero da conta e omitido de proposito - nao e necessario para o
        # backtest e nao ha razao para grava-lo em arquivo de relatorio.
    }


def descobrir_simbolo(cfg: Config) -> str:
    """Retorna o nome exato do simbolo do HK50 nesta corretora.

    Se o config traz um nome fixo, usa ele. Senao varre os simbolos disponiveis
    procurando pelos padroes configurados - cada corretora batiza o indice de um
    jeito (HK50, HK50.cash, HKG33...).
    """
    fixo = cfg.get("mt5.simbolo")
    if fixo:
        if mt5.symbol_info(fixo) is None:
            raise ErroMT5(f"Simbolo '{fixo}' definido no config nao existe nesta corretora.")
        return fixo

    padroes = [p.upper() for p in cfg.get("mt5.padroes_busca_simbolo", [])]
    todos = mt5.symbols_get() or ()
    candidatos = [
        s.name for s in todos
        if any(p in s.name.upper().replace(".", "").replace("_", "") for p in
               (pp.replace(".", "").replace("_", "") for pp in padroes))
    ]

    if not candidatos:
        raise ErroMT5(
            "Nenhum simbolo do HK50 encontrado.\n"
            f"Padroes procurados: {padroes}\n"
            f"A corretora expoe {len(todos)} simbolos. Abra 'Exibir > Simbolos' no MT5, "
            "localize o indice de Hong Kong e escreva o nome exato em config.yaml "
            "(mt5.simbolo)."
        )

    # Prefere o nome mais curto: costuma ser o contrato principal, e nao uma
    # variante tipo HK50.raw / HK50-Z25.
    candidatos.sort(key=lambda n: (len(n), n))
    return candidatos[0]


def garantir_simbolo_visivel(simbolo: str) -> None:
    """Adiciona o simbolo ao Market Watch.

    Simbolo fora do Market Watch costuma devolver historico vazio, mesmo existindo.
    """
    info = mt5.symbol_info(simbolo)
    if info is None:
        raise ErroMT5(f"Simbolo '{simbolo}' nao encontrado no terminal.")
    if not info.visible and not mt5.symbol_select(simbolo, True):
        raise ErroMT5(f"Nao consegui adicionar '{simbolo}' ao Market Watch.")


def ler_especificacao(simbolo: str) -> EspecificacaoSimbolo:
    """Le a especificacao do contrato - alimenta os custos do backtest."""
    info = mt5.symbol_info(simbolo)
    if info is None:
        raise ErroMT5(f"Sem especificacao para '{simbolo}'.")

    # valor_ponto = quanto vale 1 ponto de movimento, por 1 lote, na moeda do lucro.
    valor_ponto = info.trade_tick_value * (info.point / info.trade_tick_size) \
        if info.trade_tick_size else 0.0

    return EspecificacaoSimbolo(
        nome=info.name,
        descricao=info.description,
        digitos=info.digits,
        ponto=info.point,
        spread_atual_pontos=info.spread,
        spread_flutuante=bool(info.spread_float),
        tamanho_contrato=info.trade_contract_size,
        valor_ponto=round(valor_ponto, 6),
        volume_minimo=info.volume_min,
        volume_maximo=info.volume_max,
        passo_volume=info.volume_step,
        moeda_lucro=info.currency_profit,
        swap_compra=info.swap_long,
        swap_venda=info.swap_short,
    )
