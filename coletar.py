"""
ETAPA 1 - Coleta do historico do HK50 no MetaTrader 5.

Uso:
    .venv/Scripts/python.exe coletar.py

Pre-requisito: terminal MT5 ABERTO E LOGADO. Este script apenas LE dados -
nenhuma ordem e enviada, nenhuma configuracao do terminal e alterada.
"""

from __future__ import annotations

import sys
import traceback

import pandas as pd

from configuracao import Config
from data import armazenamento, coleta, tratamento
from data.mt5_conexao import (
    ErroMT5, conectar, desconectar, descobrir_simbolo,
    garantir_simbolo_visivel, info_terminal, ler_especificacao,
)

LARGURA = 74


def titulo(texto: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {texto}")
    print("=" * LARGURA)


def linha(rotulo: str, valor) -> None:
    print(f"  {rotulo:.<44} {valor}")


def main() -> int:
    cfg = Config.carregar()
    pasta_saida = cfg.caminho_absoluto("coleta.pasta_saida")
    fuso_ativo = cfg.exigir("pregao.fuso_do_ativo")
    timeframes = cfg.exigir("coleta.timeframes")
    data_inicial = cfg.exigir("coleta.data_inicial")

    titulo("ETAPA 1 - COLETA DE DADOS HISTORICOS")

    conectar(cfg)
    try:
        info = info_terminal()
        linha("Terminal build", info["terminal_build"])
        linha("Servidor", info["servidor"])
        linha("Tipo de conta", info["tipo_conta"])
        linha("Conectado a corretora", info["terminal_conectado"])

        simbolo = descobrir_simbolo(cfg)
        garantir_simbolo_visivel(simbolo)
        spec = ler_especificacao(simbolo)

        titulo("ESPECIFICACAO DO CONTRATO")
        linha("Simbolo", spec.nome)
        linha("Descricao", spec.descricao)
        linha("Digitos / tamanho do ponto", f"{spec.digitos} / {spec.ponto}")
        linha("Spread atual (pontos)", f"{spec.spread_atual_pontos} "
                                      f"({'flutuante' if spec.spread_flutuante else 'fixo'})")
        linha("Tamanho do contrato", spec.tamanho_contrato)
        linha("Valor do ponto (1 lote)", f"{spec.valor_ponto} {spec.moeda_lucro}")
        linha("Volume min / max / passo",
              f"{spec.volume_minimo} / {spec.volume_maximo} / {spec.passo_volume}")
        linha("Swap compra / venda", f"{spec.swap_compra} / {spec.swap_venda}")

        fuso_servidor = cfg.get("mt5.fuso_servidor")
        resultados: dict[str, dict] = {}

        for indice, timeframe in enumerate(timeframes):
            titulo(f"COLETANDO {simbolo} - {timeframe}"
                   f"{'  (timeframe prioritario)' if indice == 0 else ''}")

            bruto = coleta.coletar_candles(simbolo, timeframe, data_inicial)
            linha("Candles recebidos do terminal", f"{len(bruto):,}".replace(",", "."))

            # O fuso do servidor e inferido uma unica vez, no timeframe
            # prioritario (mais dados = inferencia mais estavel), e reaproveitado.
            if fuso_servidor is None:
                fuso_servidor, consistencia, abertura = coleta.inferir_fuso_servidor(bruto, cfg)
                linha("Fuso do servidor inferido", fuso_servidor)
                linha("Abertura do pregao detectada", f"{abertura} (hora de Hong Kong)")
                linha("Consistencia da abertura", f"{consistencia:.1%}")
                if consistencia < 0.90:
                    print("\n  [ATENCAO] A abertura do pregao nao e consistente com")
                    print("  nenhum fuso testado. Preencha mt5.fuso_servidor a mao.\n")

            com_fuso = coleta.aplicar_fusos(bruto, fuso_servidor, fuso_ativo)
            df_bruto, df_pregao, rel = tratamento.processar(com_fuso, timeframe, cfg)

            if df_pregao.empty:
                print("  [ERRO] Nenhum candle sobrou apos o filtro de pregao.")
                continue

            p_bruto = armazenamento.salvar(
                df_bruto, armazenamento.caminho_parquet(pasta_saida, simbolo, timeframe, "bruto"))
            p_pregao = armazenamento.salvar(
                df_pregao, armazenamento.caminho_parquet(pasta_saida, simbolo, timeframe, "pregao"))
            armazenamento.salvar_amostra_csv(df_pregao, p_pregao)

            inicio = df_pregao["tempo_ativo"].min()
            fim = df_pregao["tempo_ativo"].max()
            anos = (fim - inicio).days / 365.25

            print()
            linha("Periodo coberto (hora de Hong Kong)",
                  f"{inicio:%Y-%m-%d} ate {fim:%Y-%m-%d}")
            linha("Cobertura", f"{anos:.2f} anos / {rel.dias_negociados} pregoes")
            linha("Candles apos filtro de pregao", f"{rel.candles_pregao:,}".replace(",", "."))
            linha("Candles por pregao (mediana)", rel.candles_por_dia_mediana)
            print("  --- qualidade ---")
            linha("Removidos: fora do horario de pregao", rel.removidos_fora_pregao)
            linha("Removidos: dia nao negociado", rel.removidos_dia_nao_negociado)
            linha("Removidos: volume zero", rel.removidos_volume_zero)
            linha("Removidos: OHLC invalido", rel.removidos_ohlc_invalido)
            linha("Duplicados", rel.duplicados)
            linha("Dias descartados por falta de dado",
                  f"{rel.dias_descartados_por_densidade} "
                  f"({rel.candles_descartados_por_densidade} candles)")
            linha("Candles antes do corte inicial", rel.candles_antes_do_corte_inicial)
            linha("Primeiro dia realmente utilizavel", rel.primeiro_dia_utilizavel)
            linha("Buracos relevantes dentro da sessao", rel.buracos_intra_sessao)
            linha("Maior buraco (candles)", rel.maior_buraco_candles)
            for b in rel.detalhe_maiores_buracos[:3]:
                print(f"      - {b['quando']}: faltam {b['candles_faltando']} candles")
            print("  --- arquivos ---")
            linha("Bruto", p_bruto.name)
            linha("Pregao (usar no backtest)", p_pregao.name)

            resultados[timeframe] = {
                "arquivo_bruto": str(p_bruto),
                "arquivo_pregao": str(p_pregao),
                "inicio": str(inicio),
                "fim": str(fim),
                "anos": round(anos, 2),
                "qualidade": rel.como_dict(),
            }

        meta = armazenamento.salvar_metadados(pasta_saida, {
            "simbolo": simbolo,
            "terminal": info,
            "especificacao_contrato": spec.como_dict(),
            "fuso_servidor": fuso_servidor,
            "fuso_do_ativo": fuso_ativo,
            "sessoes_regulares": cfg.get("pregao.sessoes_regulares"),
            "timeframes": resultados,
        })

        titulo("RESUMO")
        linha("Metadados", meta.name)
        print()
        if not cfg.get("custos.comissao_por_lote"):
            print("  [PENDENTE] custos.comissao_por_lote ainda esta zerado no config.")
            print("  Sem esse numero o backtest superestima o lucro de todo trade.")
        print()
        return 0

    finally:
        desconectar()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ErroMT5 as e:
        print(f"\n[ERRO DE CONEXAO/MT5]\n{e}\n", file=sys.stderr)
        sys.exit(2)
    except Exception:
        print("\n[ERRO INESPERADO]", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
