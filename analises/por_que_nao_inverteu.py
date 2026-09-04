"""
Por que algumas saidas viram entrada contraria e outras nao?

A regra de entrada exige que o candle ANTERIOR tenha fechado DENTRO do canal.
Quando o preco vem cavalgando fora do canal (tendencia forte) e desaba
atravessando o canal inteiro num candle so, o candle anterior estava FORA -
do outro lado - e a regra nao se cumpre. A posicao e encerrada, mas nenhuma
entrada nova dispara.

Este script conta quantas vezes cada caso acontece, e mede o que teria
acontecido se a inversao tivesse sido feita.

    .venv/Scripts/python.exe analises/por_que_nao_inverteu.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.motor import Motor, montar_do_config  # noqa: E402
from configuracao import Config  # noqa: E402
from strategy.base import Sinal  # noqa: E402
from strategy.canal_rompimento import PosicaoNoCanal  # noqa: E402

LARGURA = 78


class MotorQueExplica(Motor):
    """Registra, a cada candle, onde o candle ANTERIOR estava em relacao ao canal."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.registro: list[dict] = []

    def rodar(self, feed):
        e = self.estrategia
        original = e.on_candle

        def espiao(candle):
            # Lido ANTES da chamada: e a posicao do candle anterior, que e o
            # que a regra de entrada consulta.
            anterior = e._posicao_anterior
            canal = e._canal_para(candle)
            sinal = original(candle)
            self.registro.append({
                "t": candle.tempo,
                "anterior": anterior.value if anterior else None,
                "atual": (canal.onde_esta(*e._precos_de_referencia(candle)).value
                          if canal else None),
                "sinal": sinal.value if sinal is not Sinal.NENHUM else None,
            })
            return sinal

        e.on_candle = espiao
        resultado = super().rodar(feed)
        e.on_candle = original
        return resultado


def main() -> int:
    cfg = Config.carregar()
    motor_base, feed = montar_do_config(cfg, modo_saida="stop_gain")
    motor = MotorQueExplica(motor_base.estrategia, motor_base.executor,
                            motor_base.contexto, motor_base.resolvedor)
    resultado = motor.rodar(feed)

    trades = resultado.quadro
    trades["tempo_entrada"] = pd.to_datetime(trades["tempo_entrada"])
    trades["tempo_saida"] = pd.to_datetime(trades["tempo_saida"])
    reg = pd.DataFrame(motor.registro).set_index("t")

    entradas = set(trades["tempo_entrada"])
    saidas = trades[["tempo_saida", "direcao", "resultado_pontos"]].copy()

    print("=" * LARGURA)
    print("  POR QUE ALGUMAS SAIDAS NAO VIRAM ENTRADA CONTRARIA")
    print("=" * LARGURA)
    print(f"  Saidas analisadas: {len(saidas)}\n")

    casos = {"inverteu": 0, "veio_de_fora": 0, "sem_canal": 0, "outro": 0}
    exemplos: list[dict] = []

    for r in saidas.itertuples():
        t = r.tempo_saida
        if t not in reg.index:
            casos["outro"] += 1
            continue
        linha = reg.loc[t]
        if t in entradas:
            casos["inverteu"] += 1
        elif linha["anterior"] is None:
            casos["sem_canal"] += 1
        elif linha["anterior"] != PosicaoNoCanal.DENTRO.value:
            casos["veio_de_fora"] += 1
            if len(exemplos) < 5:
                exemplos.append({"quando": t, "anterior": linha["anterior"],
                                 "atual": linha["atual"], "lado": r.direcao,
                                 "resultado": r.resultado_pontos})
        else:
            casos["outro"] += 1

    total = sum(casos.values())
    rotulos = {
        "inverteu": "SAIU E INVERTEU (candle anterior estava dentro)",
        "veio_de_fora": "SAIU SEM INVERTER (candle anterior ja estava fora)",
        "sem_canal": "sem canal formado ainda",
        "outro": "outros",
    }
    for chave, n in casos.items():
        if n:
            print(f"  {rotulos[chave]:<52}{n:>6}{n/total:>8.0%}")

    print("\n  A regra que produz isso e a mesma que voce definiu: so entra quem")
    print("  vem de DENTRO do canal para fora. Um candle que atravessa o canal")
    print("  inteiro de uma vez fecha a posicao, mas nao gera entrada nova -")
    print("  o candle anterior nao estava dentro, estava do outro lado de fora.")

    if exemplos:
        print("\n  Exemplos de saida sem inversao:")
        print(f"    {'quando':<20}{'candle anterior':>18}{'candle da saida':>18}"
              f"{'posicao':>12}")
        for e in exemplos:
            print(f"    {str(e['quando'])[:16]:<20}{e['anterior']:>18}"
                  f"{e['atual']:>18}{e['lado']:>12}")

    # ------------------------------------------------------------------
    print("\n" + "=" * LARGURA)
    print("  E SE AS INVERSOES PERDIDAS TIVESSEM SIDO FEITAS?")
    print("=" * LARGURA)
    print("  Nao da para responder so com este backtest: a partir do momento em")
    print("  que uma entrada extra e feita, todo o encadeamento seguinte muda.")
    print("  A resposta honesta exige rodar a estrategia inteira com a regra")
    print("  alterada - que e o que rodar_comparativo_inversao.py faz.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
