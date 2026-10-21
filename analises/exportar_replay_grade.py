"""
Exporta o replay vela a vela da grade (versao do autor) para a pagina animada.

    .venv/Scripts/python.exe analises/exportar_replay_grade.py

Versao: M1, 1 gain por dia, no maximo 2 stops, take 1,5 canal a partir da
entrada, 0x0 quando fecha 1 canal alem da entrada, stop fora da zona por
fechamento. Os dias sao escolhidos pela SITUACAO que mostram (take de primeira,
retomada, nova entrada, 0x0, dois stops), nao pelo resultado.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rodar_grade import REFERENCIA, CUSTO_ATUAL, carregar         # noqa: E402
from strategy.grade import simular, simular_dia              # noqa: E402

VERSAO = replace(REFERENCIA, parar_no_take=True, max_stops_dia=2, take_niveis=1.5,
                 usar_0x0=True)


def replay(df: pd.DataFrame, dia) -> dict:
    datas = sorted(df["tempo_ativo"].dt.date.unique())
    bloco = df[df["tempo_ativo"].dt.date == dia].reset_index(drop=True)
    ant = df[df["tempo_ativo"].dt.date == datas[datas.index(dia) - 1]]
    amp = float((ant["maxima"] - ant["minima"]).median())
    fech_ant = float(ant["fechamento"].iloc[-1])
    rastro: list = []
    trades = simular_dia(bloco, fech_ant, amp, VERSAO, CUSTO_ATUAL, rastro=rastro)
    canal = rastro[0]["canal"]
    return {
        "dia": str(dia), "fech_anterior": fech_ant, "canal": canal,
        "velas": [[x.tempo_ativo.strftime("%H:%M"), x.abertura, x.maxima,
                   x.minima, x.fechamento] for x in bloco.itertuples()],
        "estados": rastro[1:],
        "trades": [{"r": round(float(t.r), 2), "motivo": t.motivo, "tipo": t.tipo,
                    "pts": round(float(t.resultado), 1), "be": bool(t.foi_0x0)}
                   for t in trades],
    }


def main() -> int:
    df = carregar("M1")
    df = df[df["tempo_ativo"] >= pd.Timestamp("2026-01-01", tz="Asia/Hong_Kong")]
    t = simular(df, VERSAO, CUSTO_ATUAL)
    por_dia = {d: g for d, g in t.groupby("dia")}

    situacoes = [
        ("Alvo de primeira", lambda g: list(g.motivo) == ["take"] and g.tipo.iloc[0] == "continuacao"),
        ("Retomada", lambda g: g.tipo.iloc[0] == "cinquenta" and "take" in list(g.motivo)),
        ("Reversão", lambda g: g.tipo.iloc[0] == "reversao" and list(g.motivo) == ["take"]),
        ("Stop e nova entrada", lambda g: list(g.motivo) == ["stop", "take"] and not g.foi_0x0.iloc[0]
         and g.tipo.iloc[0] != "cinquenta"),
        ("Saída no 0x0", lambda g: bool(g.foi_0x0.iloc[0]) and g.motivo.iloc[0] == "stop"),
        ("Dois stops, dia encerrado", lambda g: list(g.motivo) == ["stop", "stop"]),
    ]
    escolhidos = []
    for rotulo, teste in situacoes:
        for d, g in por_dia.items():
            if d not in [e[1] for e in escolhidos] and teste(g.reset_index(drop=True)):
                escolhidos.append((rotulo, d))
                break

    saida = []
    for rotulo, d in escolhidos:
        r = replay(df, d)
        r["rotulo"] = rotulo
        saida.append(r)
        print(f"  {rotulo:<28} {d}  w={r['canal']['w']:.0f}  {r['trades']}")
    destino = Path(__file__).resolve().parent.parent / "reports" / "replay_grade.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    print(f"  {destino} ({destino.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
