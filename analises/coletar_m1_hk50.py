"""
Coleta o HK50 em M1 - o tempo grafico em que a grade e operado.

O perfil HK50 do config.yaml continua congelado (M15/M5); este script so
acrescenta o M1 na mesma pasta, pelo mesmo pipeline de fuso e pregao.

    .venv/Scripts/python.exe analises/coletar_m1_hk50.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configuracao import Config                                    # noqa: E402
from data import armazenamento, coleta, tratamento                 # noqa: E402
from data.mt5_conexao import (conectar, desconectar, descobrir_simbolo,  # noqa: E402
                              garantir_simbolo_visivel)


def main() -> int:
    cfg = Config.carregar(mercado="HK50")
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    conectar(cfg)
    try:
        simbolo = descobrir_simbolo(cfg)
        garantir_simbolo_visivel(simbolo)
        bruto = coleta.coletar_candles(simbolo, "M1", cfg.exigir("coleta.data_inicial"))
        print(f"  candles M1 recebidos: {len(bruto):,}")

        fuso = cfg.get("mt5.fuso_servidor")
        if fuso is None:
            fuso, consistencia, abertura = coleta.inferir_fuso_servidor(bruto, cfg)
            print(f"  fuso {fuso}, abertura {abertura}, consistencia {consistencia:.1%}")

        com_fuso = coleta.aplicar_fusos(bruto, fuso, cfg.exigir("pregao.fuso_do_ativo"))
        df_bruto, df_pregao, _ = tratamento.processar(com_fuso, "M1", cfg)
        armazenamento.salvar(df_bruto, armazenamento.caminho_parquet(pasta, simbolo, "M1", "bruto"))
        destino = armazenamento.caminho_parquet(pasta, simbolo, "M1", "pregao")
        armazenamento.salvar(df_pregao, destino)
        print(f"  pregao: {len(df_pregao):,} candles, "
              f"{df_pregao['tempo_ativo'].min()} a {df_pregao['tempo_ativo'].max()}")
        print(f"  salvo em {destino}")
    finally:
        desconectar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
