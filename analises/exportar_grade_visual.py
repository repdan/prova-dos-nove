"""
Exporta os dados da pagina visual da grade: dias de exemplo com a grade
desenhada, e acerto x payoff de cada variante (metodo e espelho, sem custo).

    .venv/Scripts/python.exe analises/exportar_grade_visual.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rodar_grade import REFERENCIA, CUSTO_ATUAL, carregar            # noqa: E402
from strategy.grade import Custos, canal_de_abertura, simular  # noqa: E402

SEM_CUSTO = Custos(0, 0, 0.0)


def dia_exemplo(df: pd.DataFrame, trades: pd.DataFrame, dia) -> dict:
    bloco = df[df["tempo_ativo"].dt.date == dia].reset_index(drop=True)
    datas = sorted(df["tempo_ativo"].dt.date.unique())
    anterior = df[df["tempo_ativo"].dt.date == datas[datas.index(dia) - 1]]
    amp = float((anterior["maxima"] - anterior["minima"]).median())
    base, w, ultima = canal_de_abertura(bloco, amp, REFERENCIA)
    t = trades[trades["dia"] == dia]
    return {
        "dia": str(dia), "base": base, "w": w, "canal_ate": int(ultima),
        "fech_anterior": float(anterior["fechamento"].iloc[-1]),
        "velas": [[x.tempo_ativo.strftime("%H:%M"), x.abertura, x.maxima,
                   x.minima, x.fechamento] for x in bloco.itertuples()],
        "trades": [{"dir": int(x.direcao), "tipo": x.tipo, "motivo": x.motivo,
                    "t_in": pd.Timestamp(x.tempo_entrada).strftime("%H:%M"),
                    "t_out": pd.Timestamp(x.tempo_saida).strftime("%H:%M"),
                    "p_in": x.preco_entrada, "p_out": x.preco_saida,
                    "stop": x.stop_inicial, "take": x.take, "r": round(x.r, 2)}
                   for x in t.itertuples()],
    }


def payoff(t: pd.DataFrame) -> dict:
    r = t["r"].dropna()
    g, p = r[r > 0], r[r <= 0]
    return {"n": int(len(r)), "acerto": float((r > 0).mean()),
            "ganho": float(g.mean()) if len(g) else 0.0,
            "perda": float(-p.mean()) if len(p) else 0.0,
            "r": float(r.mean()), "erro": float(r.std() / len(r) ** 0.5)}


def main() -> int:
    df = carregar("M5")
    trades = simular(df, REFERENCIA, CUSTO_ATUAL)
    por_dia = trades.groupby("dia")

    # Um dia de cada tipo, escolhidos pela forma e nao pelo resultado:
    # (1) take no primeiro trade, (2) stop e nova entrada, (3) reversao.
    escolhidos = []
    for dia, g in por_dia:
        motivos = list(g["motivo"])
        if not escolhidos and motivos == ["take"] and g["tipo"].iloc[0] == "continuacao":
            escolhidos.append(dia)
        elif len(escolhidos) == 1 and motivos[:2] == ["stop", "take"]:
            escolhidos.append(dia)
        elif len(escolhidos) == 2 and len(g) >= 3 and "stop" in motivos:
            escolhidos.append(dia)
        if len(escolhidos) == 3:
            break

    variantes = [
        ("Referencia: take 1 nível", {}),
        ("Take 2 níveis", {"take_niveis": 2}),
        ("Sem take", {"take_niveis": 0}),
        ("1 para 1", {"stop_niveis": 1, "take_niveis": 1}),
        ("2 para 2", {"stop_niveis": 2, "take_niveis": 2}),
        ("Stop no toque", {"stop_modo": "toque"}),
        ("Só 50%", {"entrada_continuacao": False, "entrada_reversao": False}),
    ]
    pontos = []
    for rot, kw in variantes:
        p = replace(REFERENCIA, **kw)
        pontos.append({"rotulo": rot,
                       "metodo": payoff(simular(df, p, SEM_CUSTO)),
                       "espelho": payoff(simular(df, replace(p, controle_inverter=True), SEM_CUSTO)),
                       "liquido": payoff(simular(df, p, CUSTO_ATUAL))})

    saida = {"dias": [dia_exemplo(df, trades, d) for d in escolhidos],
             "variantes": pontos,
             "custo_medio": float(trades["custo"].mean()),
             "w_mediano": float(trades["largura"].median()),
             "n_dias": int(df["tempo_ativo"].dt.date.nunique())}
    destino = Path(__file__).resolve().parent.parent / "reports" / "grade_visual.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    print(f"  {destino}  ({destino.stat().st_size / 1024:.0f} KB)")
    for d in saida["dias"]:
        print(f"  {d['dia']}: w={d['w']:.0f}, {len(d['velas'])} velas, "
              f"trades {[ (x['tipo'], x['motivo'], x['r']) for x in d['trades']]}")
    for v in pontos:
        m, e = v["metodo"], v["espelho"]
        print(f"  {v['rotulo']:<22} acerto {m['acerto']:.0%} ganho {m['ganho']:.2f} "
              f"perda {m['perda']:.2f} R {m['r']:+.3f} | espelho {e['acerto']:.0%} {e['r']:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
