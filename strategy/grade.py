"""
Grade de niveis do canal de abertura, mecanizada como regras.

O metodo e uma GRADE DE NIVEIS de largura fixa
ancorada no canal de abertura do dia, mais uma maquina de estados sobre ela:

  canal de abertura  topo/fundo das primeiras velas do pregao. Define a
                     largura w e a ancora B. Vale ate o fim do dia.
  grade              niveis B + k*w. Cada nivel de expansao funciona como suporte/resistencia.
  NR / ZR            nivel de referencia = nivel onde o preco fechou; zona de recuo
                     = o nivel atras dele (abaixo em alta, acima em queda).
  entradas           (a) fechou alem do NR      -> continuacao ("rompimento")
                     (b) visitou a ZR e fechou de volta alem do meio do NR
                                                -> "retomada"
                     (c) fechou alem da ZR, contra a tendencia
                                                -> reversao ("dois niveis contra")
  stop               "fora da zona": do outro lado da ZR do sinal.
  take               k niveis a partir da entrada.
  0x0                fechou alem de 1 nivel a favor -> stop vai para a entrada.
  dia                bateu o take -> encerra o dia. Tomou stop -> continua
                     (nova entrada), ate o limite de perdas do dia.

Tudo e decidido no FECHAMENTO do candle (a sombra nao conta).
Onde o metodo deixa margem - largura do canal, stop no toque ou por
fechamento, take de 1 ou 2 niveis - a escolha virou parametro, para ser
testada em plato e nao escolhida a dedo.

"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ParametrosGrade:
    # --- canal de abertura -------------------------------------------------
    # Velas usadas para o canal. Usa 1; se a vela for curta, espera a
    # proxima. Aqui: acumula velas ate a amplitude atingir
    # largura_minima (em multiplos da amplitude mediana das velas do dia
    # anterior) ou ate velas_maximas.
    velas_minimas: int = 1
    velas_maximas: int = 3
    largura_minima: float = 1.5
    # Vela gigante: primeira vela muito grande -> canal = 50% do corpo.
    # Gigante = corpo maior que gigante_mult x amplitude mediana do dia anterior.
    usar_vela_gigante: bool = True
    gigante_mult: float = 6.0
    # "velas": regra acima (1a vela, ou mais se for curta).
    # "alvo": como o autor marcava - entre as 4 primeiras velas (pavio e
    # corpo), o par topo/fundo cuja largura fica mais perto de canal_alvo
    # pontos, dentro de canal_faixa. Decidido so depois da 4a vela fechar.
    canal_modo: str = "velas"
    canal_velas: int = 4
    canal_alvo: float = 50.0
    canal_faixa: tuple[float, float] = (40.0, 60.0)
    # Sem par dentro da faixa: "mais_proximo" usa o melhor que houver;
    # "nao_opera" trata o dia como lateral e nao opera.
    canal_fora_da_faixa: str = "mais_proximo"
    # Prefere canais que tenham o primeiro preco do dia como uma das bordas.
    canal_primeiro_preco: bool = False
    # Alvo do canal em % do preco de abertura (faixa = alvo +-20%). Para
    # ativos cujo preco mudou de patamar (ouro: 1.270 em 2017, 4.560 em 2026),
    # um alvo fixo em pontos mediria coisas diferentes em cada ano.
    canal_alvo_pct: float | None = None

    # --- tendencia do dia ---------------------------------------------------
    # "gap": direcao do gap de abertura define a tendencia inicial.
    # "neutra": comeca sem vies; a primeira saida da caixa define.
    # "dia_anterior": direcao do dia anterior (fechamento contra abertura).
    tendencia: str = "gap"

    # --- entradas -----------------------------------------------------------
    entrada_continuacao: bool = True     # (a) rompeu o nivel do NR
    entrada_50: bool = True              # (b) volta pelo meio do NR
    entrada_reversao: bool = True        # (c) dois niveis contra

    # --- stop / take / 0x0 ---------------------------------------------------
    # "fechamento": sai quando uma vela FECHA alem do stop.
    # "toque": ordem no nivel, executada no toque.
    stop_modo: str = "fechamento"
    take_niveis: float = 1.0             # 0 = sem take (sai por stop/0x0/fim do dia)
    # None = fora da zona (padrao). Numero = stop a k niveis da entrada,
    # a variante simetrica de referencia (take 1 + stop 1, take 2 + stop 2).
    stop_niveis: float | None = None
    # Alvo em multiplos do RISCO do trade (1.5 = take a 1,5R). Quando definido,
    # substitui take_niveis.
    take_r: float | None = None
    # Gatilho do 0x0 em multiplos do risco. None = fechou 1 nivel (w) a favor.
    gatilho_0x0_r: float | None = None
    usar_0x0: bool = True

    # --- gestao do dia -------------------------------------------------------
    parar_no_take: bool = True           # "bateu o alvo, encerra o dia"
    max_stops_dia: int = 3               # 1% por trade, 3% no dia
    # Minutos antes do fim de cada sessao em que nao se abre ordem
    # (nada de ordem perto do fechamento).
    sem_entrada_antes_do_fim_min: int = 30
    # Quantos sinais validos do dia sao deixados passar antes da primeira
    # entrada ("evitar a primeira ordem do dia"). A grade segue normalmente.
    pular_sinais: int = 0
    # Gestao semanal: o canal continua diario, mas os limites valem para a
    # semana - 1 gain encerra a semana; stops_semana stops tambem. dias_semana:
    # weekday() dos dias operados (0 = segunda); None = todos.
    gestao_semanal: bool = False
    stops_semana: int = 2
    dias_semana: tuple[int, ...] | None = None
    # O que fazer com a posicao aberta no fim do dia:
    #   "nao"     fecha no fim do dia (padrao de referencia no HK50);
    #   "semana"  carrega para o dia seguinte, mas fecha na sexta;
    #   "sempre"  carrega ate stop / alvo / 0x0, inclusive no fim de semana.
    # Stop, alvo e 0x0 continuam nos precos do dia da entrada.
    carregar_posicao: str = "nao"
    # "Surfar a cada nivel" (A4 23:46): depois do 0x0, cada vez que uma vela
    # FECHA k niveis alem da entrada, o stop sobe para k-1 niveis.
    surfar: bool = False

    # --- controle -----------------------------------------------------------
    # Mesmas entradas, sentido oposto, mesmo risco e mesmo take. Nao e uma
    # estrategia: e a regua. Se o sinal tem informacao, o espelho perde.
    controle_inverter: bool = False


@dataclass
class TradeGrade:
    dia: object
    direcao: int                 # +1 comprado, -1 vendido
    tipo: str                    # continuacao | cinquenta | reversao
    tempo_entrada: pd.Timestamp
    tempo_saida: pd.Timestamp
    preco_entrada: float         # bruto (preco de tela)
    preco_saida: float
    stop_inicial: float
    take: float | None
    largura: float               # w do dia
    motivo: str
    custo: float                 # spread + derrapagem + comissao, em pontos
    resultado_bruto: float       # pontos, antes de custo
    resultado: float             # pontos, depois de custo
    risco: float                 # distancia ate o stop inicial, em pontos
    foi_0x0: bool

    @property
    def r(self) -> float:
        """Resultado em multiplos do risco: 1R = perda se o stop inicial bater."""
        return self.resultado / self.risco if self.risco > 0 else float("nan")


@dataclass
class Custos:
    slippage: float = 0.5           # pontos de indice por ponta
    comissao_pontos: float = 0.78   # pontos por giro (0.1 USD / 0.1275 USD/pt)
    spread_forcado: float | None = None
    # Swap por noite em unidades de preco (negativo = paga). So importa quando
    # a posicao atravessa dias (operacao semanal). dia_triplo: weekday() do
    # Python (0 = segunda) em que a corretora cobra 3 noites.
    swap_compra: float = 0.0
    swap_venda: float = 0.0
    dia_triplo: int = 2


# --------------------------------------------------------------- canal de abertura

def canal_de_abertura(dia: pd.DataFrame, amp_ref: float,
                      p: ParametrosGrade) -> tuple[float, float, int] | None:
    """(ancora B, largura w, indice da ultima vela usada). None se nao formou.

    B e o FUNDO do canal; a grade e B + k*w para todo k inteiro.
    """
    if dia.empty or not amp_ref or amp_ref <= 0:
        return None
    a, mx, mn, f = (dia["abertura"].to_numpy(), dia["maxima"].to_numpy(),
                    dia["minima"].to_numpy(), dia["fechamento"].to_numpy())

    if p.canal_modo == "alvo":
        return _canal_por_alvo(a, mx, mn, f, p)

    if p.usar_vela_gigante:
        corpo = abs(f[0] - a[0])
        if corpo >= p.gigante_mult * amp_ref:
            # Canal = do extremo de onde a vela partiu ate 50% do corpo.
            w = corpo / 2
            base = min(a[0], f[0]) if f[0] > a[0] else max(a[0], f[0]) - w
            return float(base), float(w), 0

    for n in range(p.velas_minimas, p.velas_maximas + 1):
        if n > len(dia):
            return None
        topo, fundo = float(mx[:n].max()), float(mn[:n].min())
        if topo - fundo >= p.largura_minima * amp_ref or n == p.velas_maximas:
            if topo - fundo <= 0:
                return None
            return fundo, topo - fundo, n - 1
    return None


def _canal_por_alvo(a, mx, mn, f, p: ParametrosGrade) -> tuple[float, float, int] | None:
    """Canal "de 45, 50 pontos" montado com pavios e corpos das primeiras velas."""
    k = p.canal_velas
    if len(a) < k:
        return None
    topos = set(mx[:k]) | set(np.maximum(a[:k], f[:k]))
    fundos = set(mn[:k]) | set(np.minimum(a[:k], f[:k]))
    primeiro = float(a[0])
    topos.add(primeiro)
    fundos.add(primeiro)
    lo, hi = p.canal_faixa
    alvo = p.canal_alvo
    if p.canal_alvo_pct is not None:
        alvo = p.canal_alvo_pct / 100 * primeiro
        lo, hi = 0.8 * alvo, 1.2 * alvo
    pares = [(float(t), float(b)) for t in topos for b in fundos if t > b]
    if not pares:
        return None

    def nota(par):
        t, b = par
        w = t - b
        fora = 0 if lo <= w <= hi else 1
        sem_primeiro = 0 if (not p.canal_primeiro_preco
                             or primeiro in (t, b)) else 1
        return (fora, sem_primeiro, abs(w - alvo))

    t, b = min(pares, key=nota)
    if not (lo <= t - b <= hi) and p.canal_fora_da_faixa == "nao_opera":
        return None
    return b, t - b, k - 1


# ------------------------------------------------------------------ simulacao

@dataclass
class _Estado:
    vies: int = 0            # +1 alta, -1 queda, 0 neutro
    cr: int = 0              # indice do nivel de referencia
    visitou_zn: bool = False
    pulados: int = 0
    stops: int = 0
    encerrado: bool = False


def _nivel(x: float, base: float, w: float) -> int:
    return math.floor((x - base) / w + 1e-9)


def simular_dia(dia: pd.DataFrame, fechamento_anterior: float | None,
                amp_ref: float, p: ParametrosGrade, custos: Custos,
                ponto: float = 0.01, rastro: list | None = None,
                vies_inicial: int | None = None, pos_herdada: dict | None = None,
                sem_entradas: bool = False, saida: dict | None = None,
                em_andamento: bool = False, fim_previsto=None) -> list[TradeGrade]:
    """Roda um pregao. `dia` precisa estar em ordem e conter so este dia.

    amp_ref: amplitude mediana das velas do dia ANTERIOR - escala do "canal
    curto/largo" sem olhar o futuro.

    rastro: se for uma lista, recebe o estado da maquina a cada vela (para o
    replay visual). Nao altera nenhuma decisao.

    pos_herdada / saida: posicao que veio aberta do dia anterior, e o dict que
    recebe ("pos") a que fica aberta no fim deste dia (p.carregar_posicao).
    sem_entradas: so administra a posicao herdada, sem abrir nada novo.

    em_andamento / fim_previsto: uso AO VIVO. A ultima vela e "agora", nao o
    fim do dia: nada fecha por fim de dia, entradas na ultima vela sao
    permitidas, o corte de horario usa fim_previsto, e a posicao que deve
    estar aberta agora vai para saida["pos"].
    """
    canal = canal_de_abertura(dia, amp_ref, p)
    if canal is None and pos_herdada is None:
        return []
    if canal is None:
        # Dia sem canal, mas com posicao herdada: so administra.
        base, w, ultima_do_canal = 0.0, pos_herdada["w"], len(dia) - 1
        sem_entradas = True
    else:
        base, w, ultima_do_canal = canal

    a = dia["abertura"].to_numpy(float)
    mx = dia["maxima"].to_numpy(float)
    mn = dia["minima"].to_numpy(float)
    f = dia["fechamento"].to_numpy(float)
    tempos = dia["tempo_ativo"].to_numpy()
    if custos.spread_forcado is not None:
        spreads = np.full(len(dia), custos.spread_forcado)
    else:
        spreads = dia["spread_pontos"].to_numpy(float) * ponto
    sessao = dia["sessao_id"].to_numpy()
    tempos_ts = pd.DatetimeIndex(dia["tempo_ativo"])
    # Ultima vela de cada sessao (manha / tarde): referencia do "fim do pregao".
    fim_sessao = dia.groupby("sessao_id")["tempo_ativo"].transform("max")
    minutos_ate_fim = ((pd.DatetimeIndex(fim_sessao) - tempos_ts)
                       .total_seconds().to_numpy() / 60)
    if fim_previsto is not None:
        minutos_ate_fim = (pd.Timestamp(fim_previsto) - tempos_ts).total_seconds().to_numpy() / 60
        # Se a vela atual ja e a ultima do dia, o dia acabou: fecha como no backtest.
        if em_andamento and tempos_ts[-1] >= pd.Timestamp(fim_previsto):
            em_andamento = False
            if saida is not None:
                saida["pos"] = None

    est = _Estado()
    if p.tendencia == "gap" and fechamento_anterior is not None:
        est.vies = 1 if a[0] > fechamento_anterior else -1 if a[0] < fechamento_anterior else 0
    if vies_inicial is not None:
        est.vies = vies_inicial
    # NR inicial: o proprio canal de abertura (nivel 0).
    est.cr = 0

    trades: list[TradeGrade] = []
    pos: dict | None = pos_herdada
    n = len(dia)
    sexta = tempos_ts[0].weekday() == 4
    carregar = p.carregar_posicao == "sempre" or (p.carregar_posicao == "semana" and not sexta)

    def custo_ponta(i: int) -> float:
        return spreads[i] / 2 + custos.slippage

    def fechar(i: int, preco: float, motivo: str) -> None:
        nonlocal pos
        d = pos["dir"]
        bruto = (preco - pos["entrada"]) * d
        custo = pos["custo_entrada"] + custo_ponta(i) + custos.comissao_pontos
        taxa = custos.swap_compra if d > 0 else custos.swap_venda
        if taxa:
            # Uma rolagem por dia util entre a entrada e a saida; a do dia
            # triplo vale 3 (cobre o fim de semana). Sabado e domingo: zero.
            d0, d1 = pos["t"].date(), tempos_ts[i].date()
            dias_ = [d0 + pd.Timedelta(days=k) for k in range((d1 - d0).days)]
            noites = sum(3 if x.weekday() == custos.dia_triplo else 1
                         for x in dias_ if x.weekday() < 5)
            custo -= taxa * noites      # swap negativo vira custo; positivo, credito
        trades.append(TradeGrade(
            dia=pos.get("dia", tempos_ts[0].date()), direcao=d, tipo=pos["tipo"],
            tempo_entrada=pos["t"], tempo_saida=tempos_ts[i],
            preco_entrada=pos["entrada"], preco_saida=preco,
            stop_inicial=pos["stop0"], take=pos["take"], largura=pos.get("w", w),
            motivo=motivo, custo=custo, resultado_bruto=bruto,
            resultado=bruto - custo, risco=pos["risco"], foi_0x0=pos["be"]))
        eventos.append({"tipo": "saida", "motivo": motivo, "preco": float(preco),
                        "r": float(trades[-1].r), "be": pos["be"]})
        if motivo == "take" and p.parar_no_take:
            est.encerrado = True
        if motivo == "stop" and not pos["be"]:
            est.stops += 1
            if est.stops >= p.max_stops_dia:
                est.encerrado = True
        pos = None

    eventos: list[dict] = []

    def registrar(i: int, sinal: int, tipo: str, bloqueio: str = "") -> None:
        if rastro is None:
            return
        rastro.append({
            "i": i, "vies": est.vies, "cr": est.cr, "visitou_zn": est.visitou_zn,
            "sinal": sinal, "tipo": tipo, "bloqueio": bloqueio,
            "stops": est.stops, "encerrado": est.encerrado,
            "pos": None if pos is None else {
                "dir": pos["dir"], "entrada": float(pos["entrada"]),
                "stop": float(pos["stop"]), "stop0": float(pos["stop0"]),
                "take": None if pos["take"] is None else float(pos["take"]),
                "be": pos["be"], "tipo": pos["tipo"]},
            "eventos": list(eventos)})

    if rastro is not None:
        rastro.append({"canal": {"base": float(base), "w": float(w),
                                 "ultima": int(ultima_do_canal), "vies": est.vies}})

    def gerir(i: int) -> None:
        """Stop, take, 0x0 e fim do dia da posicao aberta, na vela i."""
        if pos is not None:
            d = pos["dir"]
            # Dentro da vela, sem saber a ordem dos eventos, assume-se o pior:
            # stop antes do take.
            if p.stop_modo == "toque" or pos["be"]:
                tocou = mn[i] <= pos["stop"] if d > 0 else mx[i] >= pos["stop"]
                if tocou:
                    # Stop garante execucao, nao preco: gap sai na abertura.
                    preco = min(pos["stop"], a[i]) if d > 0 else max(pos["stop"], a[i])
                    fechar(i, preco, "stop")
            elif (f[i] < pos["stop"]) if d > 0 else (f[i] > pos["stop"]):
                fechar(i, f[i], "stop")
            if pos is not None and pos["take"] is not None:
                bateu = mx[i] >= pos["take"] if d > 0 else mn[i] <= pos["take"]
                if bateu:
                    fechar(i, pos["take"], "take")
            gatilho = (0 if pos is None
                       else pos.get("w", w) if p.gatilho_0x0_r is None
                       else p.gatilho_0x0_r * pos["risco"])
            if (pos is not None and p.usar_0x0 and not pos["be"]
                    and (f[i] - pos["entrada"]) * d >= gatilho):
                pos["be"] = True
                pos["stop"] = pos["entrada"]
                eventos.append({"tipo": "0x0"})
            if pos is not None and p.surfar and pos["be"]:
                wp = pos.get("w", w)
                k = math.floor((f[i] - pos["entrada"]) * d / wp + 1e-9)
                novo = pos["entrada"] + d * max(k - 1, 0) * wp
                if (novo - pos["stop"]) * d > 0:
                    pos["stop"] = novo
            if pos is not None and i == n - 1 and not em_andamento:
                if carregar and saida is not None:
                    saida["pos"] = pos
                else:
                    fechar(i, f[i], "fim_do_dia")

    # Posicao herdada: administrada tambem enquanto o canal do dia se forma.
    if pos is not None:
        for i in range(0, ultima_do_canal + 1):
            gerir(i)
    if canal is None:
        if em_andamento and saida is not None:
            saida["pos"] = pos
        return trades

    for i in range(ultima_do_canal + 1, n):
        eventos.clear()
        # ---------------- 1. posicao aberta: take, stop, 0x0, fim do dia ----
        # Fechar NAO pula o candle: ele ainda passa pela grade no passo 2, que
        # e como a nova entrada acontece - tomou o stop, o mesmo fechamento ja pode
        # ser o sinal do outro lado.
        gerir(i)

        # ---------------- 2. maquina de estados sobre a grade --------------
        sinal, tipo, _ = passo_da_grade(est, f[i], base, w, p)

        # ---------------- 3. abrir ------------------------------------------
        if (sinal == 0 or pos is not None or est.encerrado or sem_entradas
                or (i == n - 1 and not em_andamento)
                or minutos_ate_fim[i] < p.sem_entrada_antes_do_fim_min):
            bloqueio = ("" if sinal == 0 else "posicionado" if pos is not None
                        else "dia encerrado" if est.encerrado
                        else "dia sem operacao" if sem_entradas else "fim da sessao")
            registrar(i, sinal, tipo, bloqueio)
            continue

        entrada = f[i]
        # Stop fora da zona: lado de fora da ZR do NR onde o preco fechou.
        # Em alta NR = [B+cr*w, B+(cr+1)*w], ZR logo abaixo -> stop em B+(cr-1)*w.
        # E tambem a regra da vela gigante: sobe a grade ate a vela, stop
        # dois niveis abaixo - o stop nao "fica caro" por causa da vela grande.
        if p.stop_niveis is not None:
            stop = entrada - sinal * p.stop_niveis * w
        else:
            stop = stop_fora_da_zona(est, sinal, base, w)
        risco = (entrada - stop) * sinal
        if risco <= 0:
            registrar(i, sinal, tipo, "risco invalido")
            continue
        if est.pulados < p.pular_sinais:
            est.pulados += 1
            registrar(i, sinal, tipo, "primeiro sinal evitado")
            continue
        if p.controle_inverter:
            sinal = -sinal
            stop = entrada - sinal * risco
        if p.take_r is not None:
            take = entrada + sinal * p.take_r * risco
        else:
            take = (entrada + sinal * p.take_niveis * w) if p.take_niveis > 0 else None
        pos = {"dir": sinal, "tipo": tipo, "t": tempos_ts[i], "entrada": entrada,
               "stop": stop, "stop0": stop, "take": take, "risco": risco,
               "be": False, "custo_entrada": custo_ponta(i),
               "w": w, "dia": tempos_ts[0].date()}
        eventos.append({"tipo": "entrada"})
        registrar(i, sinal, tipo)

    if em_andamento and saida is not None:
        saida["pos"] = pos
    return trades


def stop_fora_da_zona(est: _Estado, sinal: int, base: float, w: float) -> float:
    """Lado de fora da ZR do NR atual: abaixo dela na compra, acima na venda."""
    return base + (est.cr - 1) * w if sinal > 0 else base + (est.cr + 2) * w


def passo_da_grade(est: _Estado, fi: float, base: float, w: float,
                   p: ParametrosGrade) -> tuple[int, str, bool]:
    """Avanca a maquina de estados com o fechamento `fi`.

    Devolve (sinal, tipo, entrou_na_zn). entrou_na_zn marca a vela em que o
    preco fechou dentro da zona de recuo vindo do NR - a entrada "agressiva" do
    trade de fechamento de gap.
    """
    r = _nivel(fi, base, w)
    sinal, tipo, entrou_zn = 0, "", False
    if est.vies >= 0 and r > est.cr:
        # Fechou acima do NR: o canal de cima passa a ser NR.
        if est.vies > 0 and p.entrada_continuacao:
            sinal, tipo = 1, "continuacao"
        if est.vies == 0 and r >= est.cr + 1:
            est.vies, sinal, tipo = 1, (1 if p.entrada_continuacao else 0), "continuacao"
        est.cr, est.visitou_zn = r, False
    elif est.vies <= 0 and r < est.cr:
        if est.vies < 0 and p.entrada_continuacao:
            sinal, tipo = -1, "continuacao"
        if est.vies == 0:
            est.vies, sinal, tipo = -1, (-1 if p.entrada_continuacao else 0), "continuacao"
        est.cr, est.visitou_zn = r, False
    elif est.vies > 0:
        if r == est.cr - 1:
            entrou_zn = not est.visitou_zn
            est.visitou_zn = True
        elif r <= est.cr - 2:
            # Perdeu NR e ZR: reversao. O nivel onde fechou vira o NR de queda.
            est.vies, est.cr, est.visitou_zn = -1, r, False
            if p.entrada_reversao:
                sinal, tipo = -1, "reversao"
        elif r == est.cr and est.visitou_zn and fi > base + (est.cr + 0.5) * w:
            est.visitou_zn = False
            if p.entrada_50:
                sinal, tipo = 1, "cinquenta"
    elif est.vies < 0:
        if r == est.cr + 1:
            entrou_zn = not est.visitou_zn
            est.visitou_zn = True
        elif r >= est.cr + 2:
            est.vies, est.cr, est.visitou_zn = 1, r, False
            if p.entrada_reversao:
                sinal, tipo = 1, "reversao"
        elif r == est.cr and est.visitou_zn and fi < base + (est.cr + 0.5) * w:
            est.visitou_zn = False
            if p.entrada_50:
                sinal, tipo = -1, "cinquenta"
    return sinal, tipo, entrou_zn


# ------------------------------------------------------------------- historico

def simular(df: pd.DataFrame, p: ParametrosGrade, custos: Custos,
            ponto: float = 0.01, periodo: str = "dia", ao_vivo: dict | None = None) -> pd.DataFrame:
    """Roda todos os dias de um historico intradiario e devolve os trades.

    periodo="semana": o "dia" do metodo vira a semana - canal nas primeiras
    velas da semana, grade valida ate sexta, limites de gain/stop semanais.

    ao_vivo: dict com "fim_previsto" (fim do dia corrente, no relogio de
    tempo_ativo). O ULTIMO dia e tratado como em andamento, e a posicao que
    deve estar aberta agora volta em ao_vivo["pos"] (None = fora).
    """
    df = df.sort_values("tempo_ativo").reset_index(drop=True)
    dias = df["tempo_ativo"].dt.date
    if periodo == "semana":
        dias = df["tempo_ativo"].dt.to_period("W").dt.start_time.dt.date
    ultimo_dia = dias.iloc[-1] if len(dias) else None
    if ao_vivo is not None:
        ao_vivo["pos"] = None
    linhas = []
    anterior = None
    semana, ganhou, stops = None, False, 0
    herdada = None          # posicao que atravessou a virada do dia
    for dia, bloco in df.groupby(dias, sort=True):
        pula = False
        if p.gestao_semanal:
            sem = pd.Timestamp(dia).to_period("W")
            if sem != semana:
                semana, ganhou, stops = sem, False, 0
            pula = (ganhou or stops >= p.stops_semana
                    or (p.dias_semana is not None and pd.Timestamp(dia).weekday() not in p.dias_semana))
        if anterior is not None and (not pula or herdada is not None):
            pd_ = p
            if p.gestao_semanal:
                pd_ = replace(p, max_stops_dia=max(p.stops_semana - stops, 1), parar_no_take=True)
            amp_ref = float((anterior["maxima"] - anterior["minima"]).median())
            fech_ant = float(anterior["fechamento"].iloc[-1])
            vies = None
            if p.tendencia == "dia_anterior":
                vies = int(np.sign(fech_ant - float(anterior["abertura"].iloc[0])))
            saida: dict = {}
            vivo = ao_vivo is not None and dia == ultimo_dia
            trades_dia = simular_dia(bloco.reset_index(drop=True), fech_ant, amp_ref, pd_,
                                     custos, ponto, vies_inicial=vies, pos_herdada=herdada,
                                     sem_entradas=pula, saida=saida, em_andamento=vivo,
                                     fim_previsto=ao_vivo.get("fim_previsto") if vivo else None)
            herdada = saida.get("pos")
            if vivo:
                ao_vivo["pos"] = herdada
            for t in trades_dia:
                linhas.append({**t.__dict__, "r": t.r})
                ganhou = ganhou or t.motivo == "take"
                stops += int(t.motivo == "stop" and not t.foi_0x0)
        anterior = bloco
    return pd.DataFrame(linhas)
