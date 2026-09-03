"""
Exporta o "filme" da estrategia: candle a candle, com o canal, os sinais e as
posicoes, para renderizar num grafico.

Serve para conferir a olho o que o backtest esta fazendo. Ler numero agregado
esconde erro de logica; ver a estrategia operando na tela nao.

    .venv/Scripts/python.exe analises/exportar_trace.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.executor import ExecutorSimulado  # noqa: E402
from backtest.feed import FeedParquet  # noqa: E402
from backtest.motor import Motor  # noqa: E402
from configuracao import Config  # noqa: E402
from strategy.base import Direcao, Sinal  # noqa: E402
from strategy.canal_rompimento import CanalRompimento  # noqa: E402

CANDLES_NA_JANELA = 260


class MotorComTrace(Motor):
    """Motor identico ao de producao, que alem de operar registra o estado.

    Herda em vez de duplicar: se o motor mudar, o filme muda junto e continua
    mostrando o que o backtest realmente faz - nao uma reconstrucao parecida.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.trace: list[dict] = []

    def rodar(self, feed):
        estrategia = self.estrategia
        posicao_atual = {"lado": None, "preco": None}

        # Envolve os metodos da estrategia para capturar o canal exatamente
        # como ela o viu, antes de absorver o candle.
        on_candle_original = estrategia.on_candle

        def on_candle_espiao(candle):
            canal = estrategia._canal_para(candle)
            sinal = on_candle_original(candle)
            self.trace.append({
                "t": candle.tempo.strftime("%Y-%m-%d %H:%M"),
                "o": round(candle.abertura, 2), "h": round(candle.maxima, 2),
                "l": round(candle.minima, 2), "c": round(candle.fechamento, 2),
                "v": int(candle.volume),
                "sup": round(canal.superior, 2) if canal else None,
                "inf": round(canal.inferior, 2) if canal else None,
                "sinal": sinal.value if sinal is not Sinal.NENHUM else None,
            })
            return sinal

        estrategia.on_candle = on_candle_espiao
        resultado = super().rodar(feed)
        estrategia.on_candle = on_candle_original
        return resultado


def escolher_janela(trades: pd.DataFrame, candles: pd.DataFrame) -> tuple[int, int]:
    """Acha um trecho que contenha tendencia E lateralizacao.

    Um trecho so de tendencia faz a estrategia parecer melhor do que e; um so
    de lateralizacao, pior. O trecho util para inspecao tem os dois.
    """
    t = trades.copy()
    t["tempo_entrada"] = pd.to_datetime(t["tempo_entrada"])
    tempos = candles["tempo_ativo"].reset_index(drop=True)

    melhor, melhor_nota = 0, -1.0
    for inicio in range(0, len(tempos) - CANDLES_NA_JANELA, 20):
        fim = inicio + CANDLES_NA_JANELA
        janela = t[(t["tempo_entrada"] >= tempos[inicio])
                   & (t["tempo_entrada"] < tempos[fim])]
        if len(janela) < 6:
            continue
        ganhos = janela[janela["resultado_pontos"] > 0]["resultado_pontos"]
        perdas = janela[janela["resultado_pontos"] <= 0]["resultado_pontos"]
        if ganhos.empty or len(perdas) < 3:
            continue
        # Nota alta = tem um ganho grande (tendencia) e varios pequenos
        # prejuizos (lateralizacao) no mesmo trecho.
        nota = ganhos.max() / max(abs(perdas.mean()), 1) * min(len(perdas), 8)
        if nota > melhor_nota:
            melhor, melhor_nota = inicio, nota
    return melhor, melhor + CANDLES_NA_JANELA


def main() -> int:
    cfg = Config.carregar()
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    caminho = pasta / "HK50_M15_pregao.parquet"

    estrategia = CanalRompimento(
        periodo_canal=cfg.exigir("estrategia.periodo_canal"),
        modo_saida="stop_gain", lote=cfg.exigir("estrategia.lote"),
        tipo_canal=cfg.get("estrategia.tipo_canal", "media"),
        preco_referencia=cfg.get("estrategia.preco_referencia", "fechamento"))
    executor = ExecutorSimulado(
        spread_padrao=cfg.exigir("custos.spread_indice"),
        slippage=cfg.get("custos.slippage_indice", 0.5),
        comissao_por_lote=cfg.get("custos.comissao_por_lote", 0.0),
        valor_ponto_por_lote=cfg.exigir("custos.valor_ponto_por_lote"),
        swap_compra=cfg.get("custos.swap_compra_indice", 0.0),
        swap_venda=cfg.get("custos.swap_venda_indice", 0.0))

    motor = MotorComTrace(estrategia, executor)
    feed = FeedParquet(caminho)
    resultado = motor.rodar(feed)

    trace = pd.DataFrame(motor.trace)
    trades = resultado.quadro
    ini, fim = escolher_janela(trades, feed.quadro)

    recorte = trace.iloc[ini:fim].reset_index(drop=True)
    t0, t1 = recorte["t"].iloc[0], recorte["t"].iloc[-1]

    trades["tempo_entrada"] = pd.to_datetime(trades["tempo_entrada"])
    trades["tempo_saida"] = pd.to_datetime(trades["tempo_saida"])
    no_recorte = trades[(trades["tempo_entrada"] >= pd.Timestamp(t0, tz="Asia/Hong_Kong"))
                        & (trades["tempo_entrada"] <= pd.Timestamp(t1, tz="Asia/Hong_Kong"))]

    lista_trades = [{
        "entrada": r.tempo_entrada.strftime("%Y-%m-%d %H:%M"),
        "saida": r.tempo_saida.strftime("%Y-%m-%d %H:%M"),
        "lado": r.direcao,
        "preco_entrada": round(r.preco_entrada_bruto, 2),
        "preco_saida": round(r.preco_saida_bruto, 2),
        "pontos": round(r.resultado_pontos, 1),
        "custo": round(r.custo_pontos, 1),
        "motivo": r.motivo_saida,
    } for r in no_recorte.itertuples()]

    saida = Path(__file__).resolve().parent.parent / "reports" / "trace_estrategia.json"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(json.dumps({
        "periodo": [t0, t1],
        "periodo_canal": cfg.exigir("estrategia.periodo_canal"),
        "candles": recorte.to_dict(orient="records"),
        "trades": lista_trades,
    }, ensure_ascii=False), encoding="utf-8")

    print(f"  Janela escolhida: {t0} a {t1}")
    print(f"  Candles: {len(recorte)} | trades no trecho: {len(lista_trades)}")
    ganhos = [t for t in lista_trades if t["pontos"] > 0]
    print(f"  Ganhadores: {len(ganhos)} | perdedores: {len(lista_trades)-len(ganhos)}")
    print(f"  Melhor: {max(t['pontos'] for t in lista_trades):+.0f} pts | "
          f"pior: {min(t['pontos'] for t in lista_trades):+.0f} pts")
    print(f"  Arquivo: reports/{saida.name} ({saida.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
