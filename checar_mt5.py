"""
Diagnostico rapido do ambiente MT5 - roda em segundos.

Serve para responder uma pergunta so: "o terminal ja esta pronto para a coleta?"
Diferente do coletar.py, este script nao grava nada. Ele apenas conta quantos
candles o terminal tem em cache por timeframe, que e exatamente o que voce nao
consegue ver na tela do MT5.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

from configuracao import Config
from data.coleta import TIMEFRAMES
from data.mt5_conexao import (
    ErroMT5, conectar, desconectar, descobrir_simbolo,
    garantir_simbolo_visivel, info_terminal,
)

# Abaixo disso o backtest nao tem base estatistica para walk-forward:
# sao ~2 anos de pregao, o minimo para treinar em N meses e testar no seguinte
# varias vezes sem reciclar dado.
MINIMO_ACEITAVEL_ANOS = 2.0


def main() -> int:
    cfg = Config.carregar()
    print("\n--- DIAGNOSTICO DO AMBIENTE MT5 ---\n")

    conectar(cfg)
    try:
        info = info_terminal()
        print(f"  Servidor .......... {info['servidor']}")
        print(f"  Tipo de conta ..... {info['tipo_conta']}")
        print(f"  Conectado ......... {info['terminal_conectado']}")

        simbolo = descobrir_simbolo(cfg)
        garantir_simbolo_visivel(simbolo)
        print(f"  Simbolo encontrado  {simbolo}\n")

        inicio = datetime(2010, 1, 1, tzinfo=timezone.utc)
        fim = datetime.now(timezone.utc) + timedelta(days=2)
        tudo_ok = True

        for nome in cfg.exigir("coleta.timeframes"):
            rates = mt5.copy_rates_range(simbolo, TIMEFRAMES[nome], inicio, fim)
            if rates is None or len(rates) == 0:
                print(f"  [{nome}] VAZIO - o terminal nao tem historico em cache.")
                tudo_ok = False
                continue

            primeiro = datetime.fromtimestamp(int(rates[0][0]), tz=timezone.utc)
            ultimo = datetime.fromtimestamp(int(rates[-1][0]), tz=timezone.utc)
            anos = (ultimo - primeiro).days / 365.25
            marca = "OK " if anos >= MINIMO_ACEITAVEL_ANOS else "POUCO"
            print(f"  [{nome}] {marca} {len(rates):>8,} candles | "
                  f"{primeiro:%Y-%m-%d} -> {ultimo:%Y-%m-%d} | {anos:.2f} anos"
                  .replace(",", "."))
            if anos < MINIMO_ACEITAVEL_ANOS:
                tudo_ok = False

        print()
        if tudo_ok:
            print("  PRONTO. Pode rodar: .venv/Scripts/python.exe coletar.py")
            print()
            return 0

        print(f"  Historico abaixo de {MINIMO_ACEITAVEL_ANOS} anos em pelo menos um timeframe.")
        print("  No MT5: Ferramentas > Opcoes > Graficos > 'Max. barras no grafico' =")
        print(f"  Ilimitado, depois abra o grafico de {simbolo} e role para tras ate o")
        print("  inicio do historico. Rode este diagnostico de novo em seguida.\n")
        return 1

    finally:
        desconectar()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ErroMT5 as e:
        print(f"\n[NAO CONECTOU]\n{e}\n", file=sys.stderr)
        sys.exit(2)
