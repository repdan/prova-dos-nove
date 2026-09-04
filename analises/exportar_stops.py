"""
Exporta um trade real com TODOS os niveis de stop desenhados no mesmo grafico.

Serve para ver, no preco de verdade, onde cada tipo de stop coloca a ordem na
mesa - e por que um sobrevive ao vaivem e o outro nao.

    .venv/Scripts/python.exe analises/exportar_stops.py
"""
from __future__ import annotations

import json, sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.motor import montar_do_config          # noqa: E402
from configuracao import Config                      # noqa: E402

ANTES, DEPOIS = 22, 34


def main() -> int:
    cfg = Config.carregar()
    cfg.definir("estrategia.tipo_stop", "nenhum")
    motor, feed = montar_do_config(cfg, modo_saida="stop_gain")
    trades = motor.rodar(feed).quadro
    p = feed.quadro.sort_values("tempo_ativo").reset_index(drop=True)

    # ATR e canal, reconstruidos como a estrategia os enxerga (sem o candle atual).
    tr = pd.concat([p["maxima"] - p["minima"],
                    (p["maxima"] - p["fechamento"].shift()).abs(),
                    (p["minima"] - p["fechamento"].shift()).abs()], axis=1).max(axis=1)
    p["atr"] = tr.rolling(14).mean().shift(1)
    p["sup"] = p["maxima"].rolling(20).mean().shift(1)
    p["inf"] = p["minima"].rolling(20).mean().shift(1)

    # Escolhe um trade vencedor cujo recuo caia ENTRE os niveis de stop: assim
    # o grafico mostra um stop apertado sendo estourado e um largo sobrevivendo
    # no mesmo trade. Um trade que atinge todos, ou nenhum, nao ensina nada.
    trades["tempo_entrada"] = pd.to_datetime(trades["tempo_entrada"])
    trades["atr_na_entrada"] = trades["tempo_entrada"].map(
        p.set_index("tempo_ativo")["atr"])
    trades["recuo_em_atr"] = trades["excursao_contraria"] / trades["atr_na_entrada"]

    cand = trades[(trades["resultado_pontos"] > 250)
                  & (trades["recuo_em_atr"].between(1.35, 1.85))
                  & (trades["candles_no_trade"].between(10, 34))]
    if cand.empty:
        cand = trades[trades["resultado_pontos"] > 250]
    t = cand.sort_values("resultado_pontos", ascending=False).iloc[0]

    i = int(p.index[p["tempo_ativo"] == t.tempo_entrada][0])
    janela = p.iloc[max(0, i - ANTES): i + DEPOIS].reset_index(drop=True)
    entrada = p.loc[i]
    atr = float(entrada["atr"])
    comprado = t.direcao == "comprado"
    m = 1 if comprado else -1
    preco = float(t.preco_entrada_bruto)

    niveis = {
        "atr_2":          preco - m * 2.0 * atr,
        "atr_1_5":        preco - m * 1.5 * atr,
        "candle_entrada": (float(entrada["minima"]) if comprado
                           else float(entrada["maxima"])) - m * 0.25 * atr,
        "canal_externo":  (float(entrada["inf"]) if comprado
                           else float(entrada["sup"])) - m * 0.25 * atr,
    }

    dados = {
        "trade": {
            "lado": t.direcao, "entrada": str(t.tempo_entrada)[:16],
            "saida": str(t.tempo_saida)[:16],
            "preco_entrada": round(preco, 2),
            "preco_saida": round(float(t.preco_saida_bruto), 2),
            "pontos": round(float(t.resultado_pontos), 1),
            "excursao_contraria": round(float(t.excursao_contraria), 1),
            "atr": round(atr, 1),
        },
        "niveis": {k: round(v, 2) for k, v in niveis.items()},
        "indice_entrada": int(i - max(0, i - ANTES)),
        "candles": [{
            "t": str(l.tempo_ativo)[:16], "o": round(l.abertura, 2),
            "h": round(l.maxima, 2), "l": round(l.minima, 2),
            "c": round(l.fechamento, 2),
            "sup": round(l.sup, 2) if pd.notna(l.sup) else None,
            "inf": round(l.inf, 2) if pd.notna(l.inf) else None,
        } for l in janela.itertuples()],
    }

    destino = Path(__file__).resolve().parent.parent / "reports" / "trace_stops.json"
    destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    print(f"  Trade: {t.direcao} em {str(t.tempo_entrada)[:16]}, "
          f"{t.resultado_pontos:+.0f} pts")
    print(f"  ATR na entrada: {atr:.1f} pontos")
    print(f"  Excursao contraria antes de dar certo: {t.excursao_contraria:.0f} pontos")
    print(f"  Niveis de stop:")
    for k, v in niveis.items():
        dist = abs(preco - v)
        print(f"    {k:<16} {v:>10.2f}   ({dist:>5.0f} pts da entrada"
              f" = {dist/atr:.2f} ATR)"
              + ("   <- SERIA ATINGIDO" if dist < t.excursao_contraria else ""))
    print(f"  Arquivo: reports/{destino.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
