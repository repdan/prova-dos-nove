"""
Grade "so gap" - a variante do autor que opera o dia em torno do gap.

L = fechamento do dia anterior, G = abertura - L (o gap). O dia tem fases:

  gap        o preco ainda nao voltou a L. So se opera NA DIRECAO DE L
             (fechamento do gap), e so com sinal da grade: reversao (fechou
             alem da ZR) ou, mais agressivo, fechou dentro da ZR vindo do NR.
             Alvo = L. So entra se houver espaco ate L (>= espaco_min_r x risco).
             Vale mesmo sendo a primeira ordem do dia.
  rompeu     uma vela FECHOU alem de L: continuacao. "Ele tende a buscar o
             movimento que fez antes" - alvo a |G| pontos depois de L, stop a
             stop_canais canais do outro lado da linha. Uma vez por dia.
  grade    tocou L e voltou: dali em diante, Grade cru com qualquer sinal.

Gap que nunca chega em L: so o trade de fechamento. A gestao (0x0, limite de
stops, parada no take, stop por fechamento) e a do ParametrosGrade.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.grade import (Custos, ParametrosGrade, TradeGrade, _Estado,
                              canal_de_abertura, passo_da_grade,
                              stop_fora_da_zona)


@dataclass(frozen=True)
class ParametrosGap:
    gap_minimo: float = 0.0          # pontos; abaixo disso o dia nao e operado
    espaco_min_r: float = 1.0        # caminho ate L, em multiplos do risco
    entrar_na_zn: bool = True        # entrada agressiva: fechou na ZR vindo do NR
    operar_preenchimento: bool = True
    operar_continuacao: bool = True
    operar_grade: bool = True      # depois de tocar L e voltar
    stop_canais: float = 1.0         # stop da continuacao: canais alem de L
    alvo_gap: float = 1.0            # alvo da continuacao: fracao de |G| alem de L


def simular_dia_gap(dia: pd.DataFrame, fech_ant: float, amp_ref: float,
                    p: ParametrosGrade, g: ParametrosGap, custos: Custos,
                    ponto: float = 0.01) -> list[TradeGrade]:
    canal = canal_de_abertura(dia, amp_ref, p)
    if canal is None:
        return []
    base, w, ultima = canal
    a = dia["abertura"].to_numpy(float)
    mx = dia["maxima"].to_numpy(float)
    mn = dia["minima"].to_numpy(float)
    f = dia["fechamento"].to_numpy(float)
    L = float(fech_ant)
    G = a[0] - L
    if G == 0 or abs(G) < g.gap_minimo:
        return []
    dg = 1 if G > 0 else -1          # lado do gap
    para_l = -dg                     # direcao do fechamento do gap
    if custos.spread_forcado is not None:
        spreads = np.full(len(dia), custos.spread_forcado)
    else:
        spreads = dia["spread_pontos"].to_numpy(float) * ponto
    tempos = pd.DatetimeIndex(dia["tempo_ativo"])
    fim_sessao = dia.groupby("sessao_id")["tempo_ativo"].transform("max")
    min_ate_fim = (pd.DatetimeIndex(fim_sessao) - tempos).total_seconds().to_numpy() / 60

    def toca(i: int) -> bool:
        return mn[i] <= L if dg > 0 else mx[i] >= L

    def rompeu(i: int) -> bool:
        return f[i] < L if dg > 0 else f[i] > L

    est = _Estado(vies=dg, cr=0)
    fase = "gap"
    # A linha pode ter sido tocada enquanto o canal se formava.
    if any(toca(i) for i in range(ultima + 1)) and not rompeu(ultima):
        fase = "grade"
    continuacao_feita = False

    trades: list[TradeGrade] = []
    pos: dict | None = None
    n = len(dia)

    def custo_ponta(i: int) -> float:
        return spreads[i] / 2 + custos.slippage

    def fechar(i: int, preco: float, motivo: str) -> None:
        nonlocal pos
        d = pos["dir"]
        bruto = (preco - pos["entrada"]) * d
        custo = pos["custo_entrada"] + custo_ponta(i) + custos.comissao_pontos
        trades.append(TradeGrade(
            dia=tempos[0].date(), direcao=d, tipo=pos["tipo"], tempo_entrada=pos["t"],
            tempo_saida=tempos[i], preco_entrada=pos["entrada"], preco_saida=preco,
            stop_inicial=pos["stop0"], take=pos["take"], largura=w, motivo=motivo,
            custo=custo, resultado_bruto=bruto, resultado=bruto - custo,
            risco=pos["risco"], foi_0x0=pos["be"]))
        if motivo == "take" and p.parar_no_take:
            est.encerrado = True
        if motivo == "stop" and not pos["be"]:
            est.stops += 1
            if est.stops >= p.max_stops_dia:
                est.encerrado = True
        pos = None

    for i in range(ultima + 1, n):
        # ---- 1. posicao aberta (mesma gestao da grade) -------------------
        if pos is not None:
            d = pos["dir"]
            if p.stop_modo == "toque" or pos["be"]:
                if mn[i] <= pos["stop"] if d > 0 else mx[i] >= pos["stop"]:
                    fechar(i, min(pos["stop"], a[i]) if d > 0 else max(pos["stop"], a[i]), "stop")
            elif (f[i] < pos["stop"]) if d > 0 else (f[i] > pos["stop"]):
                fechar(i, f[i], "stop")
            if pos is not None and pos["take"] is not None:
                if mx[i] >= pos["take"] if d > 0 else mn[i] <= pos["take"]:
                    fechar(i, pos["take"], "take")
            if (pos is not None and p.usar_0x0 and not pos["be"]
                    and (f[i] - pos["entrada"]) * d >= w):
                pos["be"], pos["stop"] = True, pos["entrada"]
            if pos is not None and i == n - 1:
                fechar(i, f[i], "fim_do_dia")

        # ---- 2. grade e fase ------------------------------------------------
        sinal, tipo, entrou_zn = passo_da_grade(est, f[i], base, w, p)
        cand = None   # (direcao, tipo, stop, take)
        if fase == "gap":
            if rompeu(i):
                fase = "rompeu"
                if g.operar_continuacao and not continuacao_feita:
                    continuacao_feita = True
                    cand = (para_l, "continuacao_gap", L + dg * g.stop_canais * w,
                            L + para_l * g.alvo_gap * abs(G))
            elif toca(i):
                fase = "grade"
            elif g.operar_preenchimento:
                if sinal == para_l:
                    cand = (para_l, "fecha_gap", stop_fora_da_zona(est, sinal, base, w), L)
                elif g.entrar_na_zn and entrou_zn and est.vies == dg:
                    # Fechou na ZR vindo do NR: stop logo alem do NR.
                    stop = base + (est.cr + 1) * w if dg > 0 else base + est.cr * w
                    cand = (para_l, "fecha_gap_zn", stop, L)
        elif fase == "grade" and g.operar_grade and sinal != 0:
            cand = (sinal, tipo, stop_fora_da_zona(est, sinal, base, w),
                    f[i] + sinal * p.take_niveis * w)

        # ---- 3. abrir ----------------------------------------------------------
        if (cand is None or pos is not None or est.encerrado or i == n - 1
                or min_ate_fim[i] < p.sem_entrada_antes_do_fim_min):
            continue
        d, tp, stop, take = cand
        entrada = f[i]
        risco = (entrada - stop) * d
        if risco <= 0 or (take - entrada) * d <= 0:
            continue
        if tp.startswith("fecha_gap") and (take - entrada) * d < g.espaco_min_r * risco:
            continue
        if p.controle_inverter:
            d, stop, take = -d, entrada + d * risco, entrada - (take - entrada)
        pos = {"dir": d, "tipo": tp, "t": tempos[i], "entrada": entrada, "stop": stop,
               "stop0": stop, "take": take, "risco": risco, "be": False,
               "custo_entrada": custo_ponta(i)}
    return trades


def simular_gap(df: pd.DataFrame, p: ParametrosGrade, g: ParametrosGap,
                custos: Custos, ponto: float = 0.01) -> pd.DataFrame:
    df = df.sort_values("tempo_ativo").reset_index(drop=True)
    linhas, anterior = [], None
    for _, bloco in df.groupby(df["tempo_ativo"].dt.date, sort=True):
        if anterior is not None:
            amp = float((anterior["maxima"] - anterior["minima"]).median())
            gap = bloco["abertura"].iloc[0] - anterior["fechamento"].iloc[-1]
            for t in simular_dia_gap(bloco.reset_index(drop=True),
                                     float(anterior["fechamento"].iloc[-1]),
                                     amp, p, g, custos, ponto):
                linhas.append({**t.__dict__, "r": t.r, "gap": float(gap)})
        anterior = bloco
    return pd.DataFrame(linhas)
