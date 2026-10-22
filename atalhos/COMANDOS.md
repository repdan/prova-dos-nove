# Comandos do projeto

Todos os atalhos abaixo funcionam com **duplo clique**. Ficam em
`C:\dev\hk50-bot\atalhos` (se quiser, copie para a Area de Trabalho).

## Robô da conta demo

| Atalho | O que faz |
|---|---|
| **1 - Robo SIMULACAO** | Liga o robô sem enviar ordens. Mostra o que ele faria. |
| **2 - Robo DEMO valendo** | Liga o robô enviando ordens para a conta **demo** (lote 0,01). Pede confirmação. |
| **3 - Parar robo** | Desliga o robô com segurança: ele zera as posições dele e encerra em até 1 minuto. |
| **5 - Abrir diario do robo** | Abre no Excel a lista de ações do robô (preço do backtest × preço executado). |

Antes de ligar o modo demo: MetaTrader aberto, logado na conta demo, com o
botão **Algo Trading** ligado. Deixe o PC sem suspender.

Só um robô por vez: não abra o 1 e o 2 juntos.

## Acompanhamento

| Atalho | O que faz |
|---|---|
| **4 - Placar das pistas** | Mostra quantos trades cada pista fez desde 26/10/2026 e se o resultado está dentro do esperado pelo backtest. |

## Os mesmos comandos, digitados

Abra o PowerShell e entre na pasta do projeto:

```
cd C:\dev\hk50-bot
```

| Para | Comando |
|---|---|
| Robô em simulação | `.venv\Scripts\python.exe -m execucao.robo_demo` |
| Robô na demo | `.venv\Scripts\python.exe -m execucao.robo_demo --valendo` |
| Parar o robô | crie um arquivo vazio `execucao\PARAR` (ou Ctrl+C na janela dele) |
| Placar das pistas | `.venv\Scripts\python.exe -m acompanhamento.acompanhar` |
| Rodar os testes do código | `.venv\Scripts\python.exe -m pytest tests -q` |

## Onde ficam as coisas

| Arquivo | O que é |
|---|---|
| `execucao\robo.log` | Tudo o que o robô decidiu, no mesmo formato da janela dele |
| `execucao\diario.csv` | Cada ação do robô, com o custo real de execução |
| `execucao\LEIA.md` | Guia completo do robô |
| `acompanhamento\regras_congeladas.md` | As regras exatas de cada pista e o que esperar delas |
| `acompanhamento\trades_<pista>.csv` | Trades de cada pista, gerados pelo placar |
