"""
ETAPA 3 - Roda o backtest e imprime as metricas.

    .venv/Scripts/python.exe rodar_backtest.py

Nao precisa do MT5 aberto: opera sobre os parquet da Etapa 1.

Roda os tres modos de saida ja implementaveis (stop_gain, trailing,
fibo_expansion) nas duas politicas de fim de pregao, para a comparacao sair de
numero. O quarto modo, ml_probabilidade, exige um modelo treinado e so entra
na Etapa 4 - por construcao, nao por falta de tempo.
"""

from __future__ import annotations

import sys

import pandas as pd

from backtest import metricas as met
from backtest.contexto_diario import direcionalidade_por_dia
from backtest.motor import montar_do_config
from configuracao import Config

LARGURA = 84
MODOS = ["stop_gain", "trailing", "fibo_expansion"]


def titulo(t: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {t}")
    print("=" * LARGURA)


def rodar(cfg: Config, modo: str, fechar_no_fim: bool):
    motor, feed = montar_do_config(cfg, modo_saida=modo)
    motor.fechar_no_fim_do_pregao = fechar_no_fim
    resultado = motor.rodar(feed)
    quadro = resultado.quadro
    m = met.calcular(quadro, cfg.get("backtest.capital_inicial", 10_000.0))
    return resultado, quadro, m


def linha_resumo(rot: str, m: met.Metricas) -> str:
    fator = "inf" if m.fator_lucro == float("inf") else f"{m.fator_lucro:.2f}"
    return (f"  {rot:<26}{m.trades:>7}{m.taxa_acerto:>8.0%}{fator:>8}"
            f"{m.resultado_total_pontos:>11.0f}{m.expectativa_por_trade:>9.1f}"
            f"{m.drawdown_maximo_pontos:>10.0f}{m.sharpe_anualizado:>8.2f}")


def main() -> int:
    cfg = Config.carregar()
    capital = cfg.get("backtest.capital_inicial", 10_000.0)

    titulo("ETAPA 3 - BACKTEST EVENT-DRIVEN")
    _, feed_desc = montar_do_config(cfg, modo_saida="stop_gain")
    print(f"  Dados ............ {feed_desc.descricao}")
    print(f"  Custos ........... spread {cfg.get('custos.spread_indice')} pts + "
          f"slippage {cfg.get('custos.slippage_indice')} pts por ponta + "
          f"comissao {cfg.get('custos.comissao_por_lote')}")
    print(f"  Lote ............. {cfg.get('estrategia.lote')} "
          f"({cfg.get('custos.valor_ponto_por_lote')} USD por ponto, por lote)")
    print(f"  Canal ............ {cfg.get('estrategia.tipo_canal')} de "
          f"{cfg.get('estrategia.periodo_canal')} periodos, rompimento por "
          f"{cfg.get('estrategia.preco_referencia')}")

    guardados: dict[str, pd.DataFrame] = {}

    titulo("COMPARATIVO DE MODOS DE SAIDA")
    print(f"  {'modo':<26}{'trades':>7}{'acerto':>8}{'fator':>8}"
          f"{'pontos':>11}{'exp/trade':>9}{'drawdown':>10}{'sharpe':>8}")
    print("  " + "-" * 78)

    for fechar in (False, True):
        rotulo_politica = ("mantem posicao na virada" if not fechar
                           else "encerra no fim do pregao")
        print(f"\n  [{rotulo_politica}]")
        for modo in MODOS:
            resultado, quadro, m = rodar(cfg, modo, fechar)
            print(linha_resumo(modo, m))
            if not fechar:
                guardados[modo] = quadro
                guardados[f"_res_{modo}"] = resultado

    # ------------------------------------------------------ diagnostico
    res = guardados["_res_stop_gain"]
    quadro = guardados["stop_gain"]
    m = met.calcular(quadro, capital)

    titulo("BASELINE stop_gain - DIAGNOSTICO")
    print(f"  Candles processados .............. {res.candles_processados:,}".replace(",", "."))
    print(f"  Sinais gerados ................... {res.sinais_gerados}")
    print(f"  Sinais perdidos (posicao aberta) . {res.sinais_ignorados_posicao_aberta}"
          f"  ({res.sinais_ignorados_posicao_aberta/max(res.sinais_gerados,1):.0%})")
    print(f"  Trades executados ................ {m.trades}")
    print()
    print(f"  Resultado BRUTO .................. {m.resultado_bruto_pontos:>10.0f} pontos")
    print(f"  Custo de transacao ............... {-m.custo_total_pontos:>10.0f} pontos")
    print(f"  Resultado LIQUIDO ................ {m.resultado_total_pontos:>10.0f} pontos"
          f"  =  {m.resultado_total_dinheiro:.2f} USD")
    if m.resultado_bruto_pontos:
        print(f"  Custo consumiu ................... "
              f"{abs(m.custo_total_pontos / m.resultado_bruto_pontos):>10.0%} do bruto")
    print()
    print(f"  Ganho medio ...................... {m.ganho_medio:>10.1f} pontos")
    print(f"  Perda media ...................... {m.perda_media:>10.1f} pontos")
    print(f"  Maior ganho ...................... {m.maior_ganho:>10.0f}")
    print(f"  Maior perda ...................... {m.maior_perda:>10.0f}")
    print(f"  PIOR excursao contraria .......... {m.pior_excursao_contraria:>10.0f} pontos"
          f"   <- perda maxima que um trade chegou a ter")
    print(f"  Candles medios por trade ......... {m.candles_medios_por_trade:>10.1f}")
    print(f"  Trades por pregao ................ {m.trades_por_dia:>10.2f}")

    # ------------------------------------------------------ distribuicoes
    titulo("DESEMPENHO POR HORARIO DE ENTRADA")
    imprimir_recorte(met.por_recorte(quadro, "ctx_hora", minimo=25), "hora HK")

    titulo("DESEMPENHO POR DIA DA SEMANA")
    nomes = {0: "segunda", 1: "terca", 2: "quarta", 3: "quinta", 4: "sexta"}
    por_dia = met.por_recorte(quadro, "ctx_dia_semana", minimo=25)
    if not por_dia.empty:
        por_dia.index = [nomes.get(i, i) for i in por_dia.index]
    imprimir_recorte(por_dia, "dia")

    titulo("DESEMPENHO POR ORDEM DO SINAL NO DIA")
    imprimir_recorte(met.por_recorte(quadro, "ctx_ordem_do_sinal_no_dia", minimo=25),
                     "ordem")

    titulo("DESEMPENHO POR REGIME DE DIRECIONALIDADE DO DIA")
    regime(quadro, cfg)

    # ------------------------------------------------------------ saidas
    destino = cfg.caminho_absoluto("coleta.pasta_saida").parent.parent / "reports"
    destino.mkdir(exist_ok=True)
    for modo in MODOS:
        guardados[modo].to_csv(destino / f"trades_{modo}.csv", index=False,
                               encoding="utf-8")
    met.curva_de_capital(quadro, capital).to_csv(
        destino / "curva_stop_gain.csv", index=False, encoding="utf-8")

    print(f"\n  Trades e curva de capital salvos em reports/\n")
    return 0


def imprimir_recorte(g: pd.DataFrame, rotulo: str) -> None:
    if g.empty:
        print("  (sem grupos com trades suficientes)")
        return
    print(f"  {rotulo:<12}{'trades':>8}{'total':>10}{'media':>9}"
          f"{'acerto':>9}{'pior':>9}")
    print("  " + "-" * 57)
    for i, l in g.iterrows():
        print(f"  {str(i):<12}{l['trades']:>8.0f}{l['total']:>10.0f}"
              f"{l['media']:>9.1f}{l['acerto']:>8.0%}{l['pior']:>9.0f}")


def regime(quadro: pd.DataFrame, cfg: Config) -> None:
    """Cruza cada trade com a direcionalidade do dia em que ele ocorreu.

    A direcionalidade e informacao POSTERIOR ao trade - por isso nao entra como
    feature. Aqui ela e so o rotulo que separa dia de tendencia de dia lateral,
    para quantificar a fraqueza que o prompt original apontou.
    """
    if quadro.empty:
        print("  (sem trades)")
        return
    pasta = cfg.caminho_absoluto("coleta.pasta_saida")
    pregao = pd.read_parquet(pasta / "HK50_M15_pregao.parquet")
    dir_dia = direcionalidade_por_dia(pregao)

    t = quadro.copy()
    t["dia"] = pd.to_datetime(t["tempo_entrada"]).dt.date
    t = t.join(dir_dia, on="dia")
    t = t.dropna(subset=["posterior_direcionalidade"])
    if t.empty:
        print("  (sem cruzamento)")
        return

    t["regime"] = pd.cut(t["posterior_direcionalidade"],
                         [0, .25, .50, .75, 1.01],
                         labels=["0-25% lateral", "25-50%", "50-75%", "75-100% tendencia"])
    g = t.groupby("regime", observed=True).agg(
        trades=("resultado_pontos", "size"), total=("resultado_pontos", "sum"),
        media=("resultado_pontos", "mean"),
        acerto=("resultado_pontos", lambda s: (s > 0).mean()),
        pior=("resultado_pontos", "min"))
    imprimir_recorte(g, "regime")


if __name__ == "__main__":
    sys.exit(main())
