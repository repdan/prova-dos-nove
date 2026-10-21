"""
Robo que opera as pistas congeladas NA CONTA DEMO.

    .venv/Scripts/python.exe -m execucao.robo_demo            # SIMULACAO: so mostra o que faria
    .venv/Scripts/python.exe -m execucao.robo_demo --valendo  # envia ordens para a conta DEMO

Nao ha logica de trading aqui. A cada vela fechada, o robo roda as estrategias
congeladas (acompanhamento/acompanhar.py) no modo ao vivo - o mesmo codigo do
backtest, conferido vela a vela em tests/test_ao_vivo.py - e alinha as
posicoes da conta com o que elas mandam ter aberto agora.

Travas de seguranca (nenhuma e opcional):
  - so roda em conta DEMO: em conta real, recusa e sai;
  - lote fixo de 0,01, verificado antes de cada ordem;
  - toda ordem sai com stop de protecao (2x o risco da estrategia), para nada
    ficar sem stop se o PC ou o script cair;
  - sem --valendo, nao envia nada;
  - o botao "Algo Trading" do MetaTrader precisa estar ligado (decisao sua);
  - arquivo execucao/PARAR: zera as posicoes do robo e encerra;
  - perda de 3% no dia: zera tudo e pausa ate o dia seguinte.

Cada acao vai para execucao/diario.csv com o preco que o backtest usaria e o
preco realmente executado - a diferenca e o custo real que o backtest so estima.
"""
from __future__ import annotations

import csv
import json
import math
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from acompanhamento.acompanhar import PISTAS, TFS, preparar             # noqa: E402
from analises.coletar_m1_indices import montar_dias                      # noqa: E402
from configuracao import Config                                          # noqa: E402
from data import coleta                                                  # noqa: E402
from data.mt5_conexao import conectar, desconectar                       # noqa: E402
from strategy.grade import canal_de_abertura, simular                  # noqa: E402
from strategy.ichimoku import simular_ichimoku                           # noqa: E402

PASTA = Path(__file__).resolve().parent
DIARIO, LOG, PARAR, ESTADO = (PASTA / "diario.csv", PASTA / "robo.log",
                              PASTA / "PARAR", PASTA / "estado.json")
MAGIC = {"P1-A": 51001, "P1-B": 51002, "P2-USDJPY": 52001, "P2-ouro": 52002}
LOTE = 0.01
LOTE_MAXIMO = 0.01
STOP_PROTECAO_R = 2.0          # stop de protecao a 2x o risco da estrategia
FECHAR_AS = (23, 57)           # fechamento compulsorio do dia (servidor)
PERDA_MAXIMA_DIA = 0.03


def log(msg: str) -> None:
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(linha, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


class Robo:
    def __init__(self, valendo: bool):
        self.valendo = valendo
        self.virtual: dict[str, dict | None] = {p.nome: None for p in PISTAS}  # so na simulacao
        self.ultima_barra: dict[str, pd.Timestamp] = {}
        self.estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {"entradas": {}}
        self.dia_corrente, self.patrimonio_inicio_dia, self.pausado_ate = None, None, None
        self.fechou_dia: str | None = None
        self.offset = pd.Timedelta(0)     # relogio da estrategia - relogio do servidor
        self.canais_anunciados: set[str] = set()

    # ------------------------------------------------------------- seguranca
    def checar_conta(self) -> None:
        conta = mt5.account_info()
        if conta is None or conta.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise SystemExit("RECUSADO: a conta conectada NAO e demo. O robo so opera conta demo.")
        log(f"Conta demo {conta.login}, saldo {conta.balance:.2f} {conta.currency}, "
            f"modo {'ENVIANDO ORDENS (demo)' if self.valendo else 'SIMULACAO (nada e enviado)'}")
        if self.valendo and not mt5.terminal_info().trade_allowed:
            log("ATENCAO: o botao 'Algo Trading' do MetaTrader esta DESLIGADO. "
                "Sem ele as ordens sao recusadas. Ligue no terminal para operar.")

    def salvar_estado(self) -> None:
        ESTADO.write_text(json.dumps(self.estado, indent=1, default=str))

    # ---------------------------------------------------------------- dados
    @staticmethod
    def agora_servidor(simbolo: str) -> datetime:
        return datetime.fromtimestamp(mt5.symbol_info_tick(simbolo).time, tz=timezone.utc).replace(tzinfo=None)

    @staticmethod
    def m1_recente(simbolo: str) -> pd.DataFrame:
        desde = (datetime.now() - timedelta(days=45)).date().isoformat()
        bruto = coleta.coletar_candles(simbolo, "M1", desde)
        return montar_dias(bruto, pausa_h=0.75, quantil_tipico=0.9, manter_ultimo=True)

    def avaliar(self, pista, m1: pd.DataFrame, agora: datetime):
        """(posicao que deve estar aberta agora, inicio da ultima vela fechada, fechamento dela)."""
        tf = TFS[pista.tf]
        offset = m1["tempo_ativo"].iloc[-1] - m1["tempo_servidor"].iloc[-1]
        self.offset = offset
        d = preparar(pista, m1)
        if d.empty:
            return None, None, None
        # A vela em formacao ainda nao existe para a estrategia.
        if d["tempo_ativo"].iloc[-1] - offset + pd.Timedelta(minutes=tf) > pd.Timestamp(agora):
            d = d.iloc[:-1]
        ultima = d["tempo_ativo"].iloc[-1]
        # Ultima vela do dia, no relogio da estrategia: o dia termina as 23:59 do servidor.
        ultimo_min = 23 * 60 + 59 + offset.total_seconds() / 60
        fim = pd.Timestamp(ultima.date()) + pd.Timedelta(minutes=math.floor(ultimo_min / tf) * tf)
        vivo = {"fim_previsto": fim}
        if pista.tipo == "grade":
            self.anunciar_canal(pista, d, ultima)
            simular(d, pista.params, pista.custos, pista.ponto, ao_vivo=vivo)
        else:
            simular_ichimoku(d, pista.params, pista.custos, pista.ponto, ao_vivo=vivo)
        return vivo["pos"], ultima, float(d["fechamento"].iloc[-1])

    def anunciar_canal(self, pista, d: pd.DataFrame, ultima) -> None:
        """Uma vez por dia: o canal e a grade da grade, para tracar no grafico."""
        chave = f"{pista.nome}|{ultima.date()}"
        if chave in self.canais_anunciados:
            return
        dias = sorted(d["tempo_ativo"].dt.date.unique())
        if len(dias) < 2 or dias[-1] != ultima.date():
            return
        hoje = d[d["tempo_ativo"].dt.date == dias[-1]].reset_index(drop=True)
        ontem = d[d["tempo_ativo"].dt.date == dias[-2]]
        canal = canal_de_abertura(hoje, float((ontem["maxima"] - ontem["minima"]).median()), pista.params)
        if canal is None:
            return
        base, w, _ = canal
        self.canais_anunciados.add(chave)
        grade = "  ".join(f"{base + k * w:.2f}" for k in range(-4, 6))
        log(f"{pista.nome} ({pista.tf}): canal de hoje {base:.2f} a {base + w:.2f} (largura {w:.2f}). "
            f"Niveis da grade: {grade}")

    # -------------------------------------------------------------- ordens
    def posicoes(self, pista) -> list:
        if not self.valendo:
            v = self.virtual[pista.nome]
            return [v] if v else []
        return [p for p in (mt5.positions_get(symbol=pista.mercado) or ()) if p.magic == MAGIC[pista.nome]]

    def registrar(self, pista, acao, preco_sim, preco_exec, retcode, comentario) -> None:
        novo = not DIARIO.exists()
        tick = mt5.symbol_info_tick(pista.mercado)
        with DIARIO.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if novo:
                w.writerow(["hora_local", "pista", "acao", "preco_backtest", "preco_executado",
                            "diferenca", "spread_agora", "lote", "retcode", "modo", "comentario"])
            dif = "" if preco_exec in (None, "") or preco_sim is None else round(preco_exec - preco_sim, 5)
            w.writerow([f"{datetime.now():%Y-%m-%d %H:%M:%S}", pista.nome, acao, preco_sim, preco_exec,
                        dif, round(tick.ask - tick.bid, 5), LOTE, retcode,
                        "demo" if self.valendo else "simulacao", comentario])

    def enviar(self, pedido: dict):
        if pedido.get("volume", 0) > LOTE_MAXIMO:
            raise SystemExit(f"RECUSADO: lote {pedido['volume']} acima da trava de {LOTE_MAXIMO}.")
        r = mt5.order_send(pedido)
        return (r.retcode, r.price, r.comment) if r is not None else (None, None, str(mt5.last_error()))

    def abrir(self, pista, desejado, preco_sim) -> None:
        d, info = desejado["dir"], mt5.symbol_info(pista.mercado)
        risco = abs(desejado["entrada"] - desejado["stop"])
        sl = round(desejado["entrada"] - d * STOP_PROTECAO_R * risco, info.digits)
        tp = round(desejado["take"], info.digits) if desejado.get("take") else 0.0
        lado = "COMPRA" if d > 0 else "VENDA"
        if not self.valendo:
            self.virtual[pista.nome] = {"dir": d, "t": desejado["t"]}
            log(f"[simulacao] {pista.nome}: {lado} 0,01 a ~{preco_sim} (stop de protecao {sl}, alvo {tp or '-'})")
            self.registrar(pista, f"abre {lado}", preco_sim, "", "", f"sl {sl} tp {tp}")
            return
        tick = mt5.symbol_info_tick(pista.mercado)
        pedido = {"action": mt5.TRADE_ACTION_DEAL, "symbol": pista.mercado, "volume": LOTE,
                  "type": mt5.ORDER_TYPE_BUY if d > 0 else mt5.ORDER_TYPE_SELL,
                  "price": tick.ask if d > 0 else tick.bid, "sl": sl, "tp": tp, "deviation": 30,
                  "magic": MAGIC[pista.nome], "comment": pista.nome,
                  "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
        ret, preco, coment = self.enviar(pedido)
        log(f"{pista.nome}: {lado} 0,01 -> retcode {ret}, preco {preco} ({coment})")
        self.registrar(pista, f"abre {lado}", preco_sim, preco, ret, coment)

    def fechar(self, pista, posicao, motivo: str, preco_sim) -> None:
        if not self.valendo:
            self.virtual[pista.nome] = None
            log(f"[simulacao] {pista.nome}: zera a ~{preco_sim} ({motivo})")
            self.registrar(pista, "zera", preco_sim, "", "", motivo)
            return
        tick = mt5.symbol_info_tick(pista.mercado)
        comprado = posicao.type == mt5.POSITION_TYPE_BUY
        pedido = {"action": mt5.TRADE_ACTION_DEAL, "symbol": pista.mercado, "volume": posicao.volume,
                  "type": mt5.ORDER_TYPE_SELL if comprado else mt5.ORDER_TYPE_BUY,
                  "position": posicao.ticket, "price": tick.bid if comprado else tick.ask,
                  "deviation": 30, "magic": MAGIC[pista.nome], "comment": f"{pista.nome} {motivo}"[:30],
                  "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
        ret, preco, coment = self.enviar(pedido)
        log(f"{pista.nome}: zera ({motivo}) -> retcode {ret}, preco {preco}")
        self.registrar(pista, "zera", preco_sim, preco, ret, motivo)

    def mover_stop(self, pista, posicao, novo_sl: float) -> None:
        info = mt5.symbol_info(pista.mercado)
        novo_sl = round(novo_sl, info.digits)
        if not self.valendo or abs(posicao.sl - novo_sl) < info.point:
            return
        r = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": pista.mercado,
                            "position": posicao.ticket, "sl": novo_sl, "tp": posicao.tp})
        log(f"{pista.nome}: stop para {novo_sl} (0x0) -> retcode {getattr(r, 'retcode', None)}")
        self.registrar(pista, "stop no 0x0", None, novo_sl, getattr(r, "retcode", None), "")

    # ------------------------------------------------------------ alinhar
    def alinhar(self, pista, desejado, ultima, preco_sim) -> None:
        abertas = self.posicoes(pista)
        lado_aberto = None
        if abertas:
            p0 = abertas[0]
            lado_aberto = p0["dir"] if isinstance(p0, dict) else (1 if p0.type == mt5.POSITION_TYPE_BUY else -1)
        if desejado is None or (lado_aberto is not None and lado_aberto != desejado["dir"]):
            for pos in abertas:
                self.fechar(pista, pos, "estrategia saiu", preco_sim)
            abertas = []
        if desejado is None:
            return
        chave = f"{pista.nome}|{desejado['t']}"
        if not abertas:
            if desejado["t"] == ultima and chave not in self.estado["entradas"]:
                self.abrir(pista, desejado, preco_sim)
                self.estado["entradas"][chave] = datetime.now().isoformat()
                self.salvar_estado()
            elif chave not in self.estado["entradas"]:
                desde = pd.Timestamp(desejado["t"]) - self.offset
                log(f"{pista.nome}: a estrategia esta posicionada desde {desde:%d/%m %H:%M} (servidor), "
                    f"mas a entrada ja passou - nao entra atrasado.")
                self.estado["entradas"][chave] = "perdida"
                self.salvar_estado()
            return
        if desejado.get("be") and self.valendo:
            self.mover_stop(pista, abertas[0], desejado["entrada"])

    def zerar_tudo(self, motivo: str) -> None:
        for pista in PISTAS:
            for pos in self.posicoes(pista):
                self.fechar(pista, pos, motivo, None)

    # --------------------------------------------------------------- ciclo
    def ciclo(self) -> None:
        agora = self.agora_servidor("XAUUSD")
        hoje = agora.date().isoformat()
        if hoje != self.dia_corrente:
            self.dia_corrente = hoje
            self.patrimonio_inicio_dia = mt5.account_info().equity
            self.pausado_ate = None if self.pausado_ate and self.pausado_ate <= hoje else self.pausado_ate
        if self.valendo and mt5.account_info().equity < self.patrimonio_inicio_dia * (1 - PERDA_MAXIMA_DIA):
            if self.pausado_ate != hoje:
                log("Perda do dia passou de 3%: zera tudo e pausa ate amanha.")
                self.zerar_tudo("perda maxima do dia")
                self.pausado_ate = hoje
            return
        if (agora.hour, agora.minute) >= FECHAR_AS:
            if self.fechou_dia != hoje:
                self.zerar_tudo("fim do dia")
                self.fechou_dia = hoje
            return

        dados, status, houve_vela = {}, [], False
        for pista in PISTAS:
            if pista.mercado not in dados:
                dados[pista.mercado] = self.m1_recente(pista.mercado)
            desejado, ultima, preco = self.avaliar(pista, dados[pista.mercado], agora)
            status.append(self.descrever(pista, desejado, preco))
            if ultima is None or self.ultima_barra.get(pista.nome) == ultima:
                continue
            houve_vela = True
            self.ultima_barra[pista.nome] = ultima
            self.alinhar(pista, desejado, ultima, preco)
        if houve_vela:
            log(f"status {agora:%H:%M} servidor | " + " | ".join(status))

    def descrever(self, pista, desejado, preco) -> str:
        """Uma linha curta: o que a estrategia manda e o que o robo tem."""
        if pista.nome == "P1-A" and self.agora_servidor("XAUUSD").weekday() > 2:
            return f"{pista.nome}: fora (so opera dom-qua)"
        tem = "com posicao" if self.posicoes(pista) else "sem posicao"
        if desejado is None:
            return f"{pista.nome}: estrategia fora, robo {tem}"
        lado = "comprada" if desejado["dir"] > 0 else "vendida"
        desde = pd.Timestamp(desejado["t"]) - self.offset
        return f"{pista.nome}: estrategia {lado} desde {desde:%H:%M}, robo {tem}"

    def rodar(self) -> None:
        self.checar_conta()
        log("Robo ligado. Para desligar com seguranca, crie o arquivo execucao/PARAR (ou Ctrl+C).")
        minuto = None
        while True:
            if PARAR.exists():
                log("Arquivo PARAR encontrado: zerando as posicoes do robo e encerrando.")
                self.zerar_tudo("PARAR")
                PARAR.unlink()
                return
            agora = self.agora_servidor("XAUUSD")
            # Uma avaliacao por minuto, alguns segundos depois de a vela fechar.
            if agora.minute != minuto and agora.second >= 3:
                minuto = agora.minute
                try:
                    self.ciclo()
                except Exception as erro:  # noqa: BLE001 - o robo nao pode morrer por um erro de rede
                    log(f"ERRO no ciclo: {erro!r}")
            time.sleep(2)


def main() -> int:
    valendo = "--valendo" in sys.argv
    conectar(Config.carregar(mercado="XAUUSD"))
    try:
        robo = Robo(valendo)
        if "--uma-vez" in sys.argv:
            robo.checar_conta()
            robo.ciclo()
        else:
            robo.rodar()
    except KeyboardInterrupt:
        log("Interrompido pelo teclado. As posicoes abertas continuam com o stop de protecao.")
    finally:
        desconectar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
