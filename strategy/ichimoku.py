"""
Ichimoku classico: so a nuvem.

So a nuvem (o "cumo"), parametros padrao 9 / 26 / 52:
  cumo superior = max(senkou A, senkou B), cumo inferior = min(...),
  ambos projetados 26 velas a frente - a nuvem da vela t foi calculada com
  dados ate t-26, entao nao ha olhar no futuro.

Entrada (no FECHAMENTO): compra quando fecha acima do cumo superior vindo de
dentro ou de baixo; venda quando fecha abaixo do cumo inferior.
  forte  atravessou a nuvem: o ultimo lado em que o preco esteve FORA dela era
         o oposto (veio de fora da nuvem, do outro lado);
  fraca  so entrou na nuvem e saiu de volta pelo mesmo lado.

Saida, duas versoes de referencia:
  "nuvem"    Ichimoku classico: sai quando fecha alem do OUTRO lado da nuvem e ja
             vira a mao (uma operacao emenda na outra).
  "grade"  adaptacao: entrada pelo Ichimoku, canal das ultimas velas perto da
             entrada, alvo de 1 ou 2 niveis, 0x0 ao fechar 1 nivel a favor. Stop no outro lado da nuvem na entrada.

Nao carrega posicao no fechamento do dia (risco de gap contra).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.grade import Custos


@dataclass(frozen=True)
class ParametrosIchimoku:
    tenkan: int = 9
    kijun: int = 26
    senkou_b: int = 52
    deslocamento: int = 26
    so_fortes: bool = False
    # Nuvem fina ("estreitamento"): so entra se a espessura da nuvem for menor
    # que nuvem_fina x amplitude media das ultimas 14 velas. None = sem filtro.
    nuvem_fina: float | None = None
    # "nuvem": sai ao fechar alem do OUTRO lado da nuvem (classico, vira a mao).
    # "reentrada": sai assim que fecha de volta DENTRO da nuvem.
    # "grade": alvo pelo canal das ultimas velas, 0x0, stop no outro lado.
    saida: str = "nuvem"
    take_niveis: float = 1.0
    canal_velas: int = 4
    usar_0x0: bool = True
    sem_entrada_antes_do_fim_min: int = 30
    controle_inverter: bool = False
    # Stop minimo em multiplos da amplitude media das ultimas 14 velas. Com a
    # nuvem fina, "o outro lado da nuvem" pode ficar a uma fracao de pip da
    # entrada - risco ~0, e qualquer movimento vira milhares de R.
    risco_minimo_amp: float = 1.0


def nuvem(df: pd.DataFrame, p: ParametrosIchimoku) -> tuple[np.ndarray, np.ndarray]:
    """(cumo superior, cumo inferior) de cada vela, ja projetados."""
    h, l = df["maxima"], df["minima"]
    meio = lambda n: (h.rolling(n).max() + l.rolling(n).min()) / 2   # noqa: E731
    a = ((meio(p.tenkan) + meio(p.kijun)) / 2).shift(p.deslocamento)
    b = meio(p.senkou_b).shift(p.deslocamento)
    return np.fmax(a, b).to_numpy(), np.fmin(a, b).to_numpy()


def simular_ichimoku(df: pd.DataFrame, p: ParametrosIchimoku, custos: Custos,
                     ponto: float = 0.01, ao_vivo: dict | None = None,
                     permitir_compra=None, permitir_venda=None) -> pd.DataFrame:
    """df: velas em ordem com coluna 'dia' (posicao fecha na ultima vela do dia).

    ao_vivo: dict com "fim_previsto" (fim do dia corrente). A ultima vela e
    "agora": o dia corrente nao fecha, e a posicao que deve estar aberta volta
    em ao_vivo["pos"].

    permitir_compra / permitir_venda: arrays booleanos alinhados com df (filtros
    de entrada). Calculados so com dados ate cada vela; bloqueiam ENTRADAS, nunca
    saidas - um trade filtrado muda os seguintes, como na pratica.
    """
    df = df.reset_index(drop=True)
    sup, inf = nuvem(df, p)
    a, mx, mn, f = (df[c].to_numpy(float) for c in ("abertura", "maxima", "minima", "fechamento"))
    spreads = (np.full(len(df), custos.spread_forcado) if custos.spread_forcado is not None
               else df["spread_pontos"].to_numpy(float) * ponto)
    t = pd.DatetimeIndex(df["tempo_ativo"])
    dia = df["dia"].to_numpy()
    ultimo_do_dia = np.r_[dia[1:] != dia[:-1], True]
    fim = df.groupby("dia")["tempo_ativo"].transform("max")
    min_ate_fim = (pd.DatetimeIndex(fim) - t).total_seconds().to_numpy() / 60
    if ao_vivo is not None:
        # Se a vela atual ja e a ultima do dia, o dia acabou: fecha como no backtest.
        ultimo_do_dia[-1] = t[-1] >= pd.Timestamp(ao_vivo["fim_previsto"])
        hoje = dia == dia[-1]
        min_ate_fim[hoje] = (pd.Timestamp(ao_vivo["fim_previsto"]) - t[hoje]).total_seconds() / 60
    amp = pd.Series(mx - mn).rolling(14).mean().to_numpy()

    trades, pos = [], None
    lado_fora = 0        # ultimo lado em que o preco fechou FORA da nuvem

    def ponta(i):
        return spreads[i] / 2 + custos.slippage

    def fechar(i, preco, motivo):
        nonlocal pos
        d = pos["dir"]
        bruto = (preco - pos["entrada"]) * d
        custo = pos["c0"] + ponta(i) + custos.comissao_pontos
        trades.append({"dia": dia[i], "direcao": d, "tipo": pos["tipo"],
                       "tempo_entrada": pos["t"], "tempo_saida": t[i],
                       "preco_entrada": pos["entrada"], "preco_saida": preco,
                       "motivo": motivo, "custo": custo, "resultado_bruto": bruto,
                       "resultado": bruto - custo, "risco": pos["risco"],
                       "largura": pos["w"], "r": (bruto - custo) / pos["risco"]})
        pos = None

    for i in range(1, len(df)):
        if np.isnan(sup[i]) or np.isnan(sup[i - 1]):
            continue
        # ---- posicao aberta -------------------------------------------------
        if pos is not None:
            d = pos["dir"]
            if p.saida == "nuvem":
                # Classico: sai ao fechar alem do OUTRO lado da nuvem atual. A
                # condicao segue o lado do SINAL, para o espelho sair junto.
                s = pos["sinal"]
                if (f[i] < inf[i]) if s > 0 else (f[i] > sup[i]):
                    fechar(i, f[i], "nuvem")
            elif p.saida == "reentrada":
                # Voltou para dentro da nuvem (ou atravessou): sai.
                s = pos["sinal"]
                if (f[i] <= sup[i]) if s > 0 else (f[i] >= inf[i]):
                    fechar(i, f[i], "reentrou")
            elif pos["be"] and ((mn[i] <= pos["entrada"]) if d > 0 else (mx[i] >= pos["entrada"])):
                fechar(i, pos["entrada"], "0x0")
            elif not pos["be"] and ((f[i] < pos["stop"]) if d > 0 else (f[i] > pos["stop"])):
                fechar(i, f[i], "stop")
            elif pos["take"] is not None and (mx[i] >= pos["take"] if d > 0 else mn[i] <= pos["take"]):
                fechar(i, pos["take"], "take")
            elif p.usar_0x0 and (f[i] - pos["entrada"]) * d >= pos["w"]:
                pos["be"] = True
            if pos is not None and ultimo_do_dia[i]:
                fechar(i, f[i], "fim_do_dia")

        # ---- sinal ---------------------------------------------------------
        sinal, forte = 0, False
        if f[i] > sup[i] and f[i - 1] <= sup[i - 1]:
            sinal, forte = 1, lado_fora <= 0
        elif f[i] < inf[i] and f[i - 1] >= inf[i - 1]:
            sinal, forte = -1, lado_fora >= 0
        if f[i] > sup[i]:
            lado_fora = 1
        elif f[i] < inf[i]:
            lado_fora = -1

        if (sinal == 0 or pos is not None or ultimo_do_dia[i]
                or min_ate_fim[i] < p.sem_entrada_antes_do_fim_min):
            continue
        if p.so_fortes and not forte:
            continue
        if sinal > 0 and permitir_compra is not None and not permitir_compra[i]:
            continue
        if sinal < 0 and permitir_venda is not None and not permitir_venda[i]:
            continue
        if p.nuvem_fina is not None and not (sup[i] - inf[i] < p.nuvem_fina * amp[i]):
            continue
        entrada = f[i]
        stop = inf[i] if sinal > 0 else sup[i]
        risco = max((entrada - stop) * sinal, p.risco_minimo_amp * amp[i])
        k = p.canal_velas
        w = float(mx[max(0, i - k + 1):i + 1].max() - mn[max(0, i - k + 1):i + 1].min())
        if risco <= 0 or w <= 0:
            continue
        d = -sinal if p.controle_inverter else sinal
        stop = entrada - d * risco
        take = entrada + d * p.take_niveis * w if p.saida == "grade" and p.take_niveis > 0 else None
        pos = {"dir": d, "sinal": sinal, "tipo": "forte" if forte else "fraca", "t": t[i],
               "entrada": entrada, "stop": stop, "take": take, "risco": risco, "w": w,
               "be": False, "c0": ponta(i)}
    if ao_vivo is not None:
        ao_vivo["pos"] = pos
    return pd.DataFrame(trades)
