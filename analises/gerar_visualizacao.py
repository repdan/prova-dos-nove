"""Monta o HTML da visualizacao, com o trace embutido."""
import json
import pathlib

TRACE = pathlib.Path(r"C:\dev\hk50-bot\reports\trace_estrategia.json")
SAIDA = pathlib.Path(__file__).parent / "estrategia-no-grafico.html"

dados = json.loads(TRACE.read_text(encoding="utf-8"))

HTML = """<title>A Estratégia no Gráfico</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">

<style>
  :root {
    --papel:        #F6F8F6;
    --superficie:   #FFFFFF;
    --superficie-2: #EDF1EE;
    --tinta:        #131C19;
    --tinta-media:  #3D4E48;
    --tinta-fraca:  #6E807A;
    --linha:        #DCE3DF;
    --linha-forte:  #C2CEC8;
    --jade:         #0E6B58;
    --jade-fraco:   #E2F0EB;
    --ambar:        #9C6612;
    --tijolo:       #A33A2C;
    --tijolo-fraco: #F7E7E4;

    /* Cores do grafico: verde/vermelho sao a convencao do terminal e ficam
       fora do sistema de tema - trocar isso confundiria a leitura. */
    --alta:   #1B8A4B;
    --baixa:  #C03A2B;
    --canal:  #131C19;
    --fundo-grafico: #FFFFFF;
    --grade: #EDEFED;

    --sombra: 0 1px 2px rgba(19,28,25,.05), 0 8px 24px -16px rgba(19,28,25,.22);
    --display: "Archivo", "Helvetica Neue", Arial, sans-serif;
    --dado: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  }

  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --papel: #0F1513; --superficie: #161E1B; --superficie-2: #1D2724;
      --tinta: #E3EAE6; --tinta-media: #AFBEB8; --tinta-fraca: #7E8F89;
      --linha: #263230; --linha-forte: #35443F;
      --jade: #4FB79C; --jade-fraco: #16302A;
      --ambar: #D9A251; --tijolo: #E08573; --tijolo-fraco: #331D19;
      --alta: #35C97A; --baixa: #E8604D;
      --canal: #C8D6D0; --fundo-grafico: #101614; --grade: #1D2724;
      --sombra: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px -16px rgba(0,0,0,.7);
    }
  }
  :root[data-theme="dark"] {
    --papel: #0F1513; --superficie: #161E1B; --superficie-2: #1D2724;
    --tinta: #E3EAE6; --tinta-media: #AFBEB8; --tinta-fraca: #7E8F89;
    --linha: #263230; --linha-forte: #35443F;
    --jade: #4FB79C; --jade-fraco: #16302A;
    --ambar: #D9A251; --tijolo: #E08573; --tijolo-fraco: #331D19;
    --alta: #35C97A; --baixa: #E8604D;
    --canal: #C8D6D0; --fundo-grafico: #101614; --grade: #1D2724;
    --sombra: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px -16px rgba(0,0,0,.7);
  }

  * { box-sizing: border-box; }
  body { background: var(--papel); color: var(--tinta); font-family: var(--display); }

  .envelope { max-width: 1280px; margin: 0 auto; padding: 28px 22px 60px; }

  header { display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }
  .eyebrow {
    font-family: var(--dado); font-size: 10px; letter-spacing: .16em;
    text-transform: uppercase; color: var(--jade);
  }
  h1 {
    font-size: clamp(1.7rem, 4vw, 2.5rem); font-weight: 700;
    letter-spacing: -.026em; margin: 0; line-height: 1.05;
  }
  .sub { color: var(--tinta-media); font-size: .98rem; max-width: 74ch; margin: 0; }

  .palco { display: grid; grid-template-columns: 1fr 296px; gap: 16px; align-items: start; }
  @media (max-width: 940px) { .palco { grid-template-columns: 1fr; } }

  .quadro {
    background: var(--fundo-grafico); border: 1px solid var(--linha);
    border-radius: 4px; overflow: hidden; box-shadow: var(--sombra);
  }
  canvas { display: block; width: 100%; height: 460px; }

  .controles {
    display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
    padding: 12px 14px; background: var(--superficie);
    border: 1px solid var(--linha); border-top: 0;
    border-radius: 0 0 4px 4px;
  }
  .quadro + .controles { margin-top: -1px; }

  button {
    font-family: var(--display); font-weight: 600; font-size: .86rem;
    padding: 8px 14px; border-radius: 3px; cursor: pointer;
    border: 1px solid var(--linha-forte); background: var(--superficie-2);
    color: var(--tinta); transition: background .12s, border-color .12s;
  }
  button:hover { background: var(--jade-fraco); border-color: var(--jade); }
  button:focus-visible { outline: 2px solid var(--jade); outline-offset: 2px; }
  button.principal { background: var(--jade); border-color: var(--jade); color: #fff; }
  button.principal:hover { filter: brightness(1.1); }

  input[type=range] { accent-color: var(--jade); flex: 1 1 160px; min-width: 120px; }

  .rotulo-ctrl {
    font-family: var(--dado); font-size: 11px; color: var(--tinta-fraca);
    letter-spacing: .06em; text-transform: uppercase;
  }

  .painel {
    background: var(--superficie); border: 1px solid var(--linha);
    border-radius: 4px; padding: 16px; box-shadow: var(--sombra);
    display: flex; flex-direction: column; gap: 14px;
  }

  .estado {
    font-family: var(--dado); font-size: .82rem;
    display: flex; flex-direction: column; gap: 7px;
  }
  .estado div { display: flex; justify-content: space-between; gap: 10px; }
  .estado span:first-child { color: var(--tinta-fraca); }
  .estado span:last-child { font-weight: 600; font-variant-numeric: tabular-nums; }

  .pos-comprado { color: var(--alta); }
  .pos-vendido  { color: var(--baixa); }
  .pos-nenhuma  { color: var(--tinta-fraca); }

  h2.painel-titulo {
    font-size: .78rem; font-weight: 600; letter-spacing: .13em;
    text-transform: uppercase; color: var(--tinta-fraca);
    margin: 0; padding-bottom: 8px; border-bottom: 1px solid var(--linha);
    font-family: var(--dado);
  }

  .registro { display: flex; flex-direction: column; gap: 5px; max-height: 260px; overflow-y: auto; }
  .registro-item {
    font-family: var(--dado); font-size: .76rem;
    display: flex; justify-content: space-between; gap: 8px;
    padding: 6px 8px; border-radius: 2px; background: var(--superficie-2);
    border-left: 2px solid var(--cor);
    font-variant-numeric: tabular-nums;
  }
  .registro-item.ganho  { --cor: var(--alta); }
  .registro-item.perda  { --cor: var(--baixa); }
  .registro-item b { font-weight: 600; }

  .legenda {
    display: flex; flex-wrap: wrap; gap: 14px; margin-top: 16px;
    font-family: var(--dado); font-size: .76rem; color: var(--tinta-media);
  }
  .legenda i { display: inline-block; width: 22px; height: 3px; vertical-align: middle;
               margin-right: 6px; border-radius: 1px; }

  .explicacao {
    margin-top: 34px; background: var(--superficie);
    border: 1px solid var(--linha); border-left: 3px solid var(--jade);
    border-radius: 4px; padding: 20px 22px;
  }
  .explicacao h3 { font-size: 1rem; margin: 0 0 10px; font-weight: 600; }
  .explicacao p, .explicacao li {
    font-family: var(--display); font-size: .95rem; color: var(--tinta-media);
    line-height: 1.6;
  }
  .explicacao p { margin: 0 0 12px; max-width: 76ch; }
  .explicacao ul { margin: 0 0 12px; padding-left: 20px; }
  .explicacao li { margin-bottom: 7px; }
  .explicacao li::marker { color: var(--jade); }
  .explicacao strong { color: var(--tinta); font-weight: 600; }
  code {
    font-family: var(--dado); font-size: .86em; background: var(--superficie-2);
    padding: 1px 5px; border-radius: 2px;
  }

  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="envelope">
  <header>
    <div class="eyebrow">HK50 · M15 · canal de médias de 20 períodos</div>
    <h1>A Estratégia no Gráfico</h1>
    <p class="sub">
      O que o backtest faz, candle a candle, no trecho de __PERIODO__.
      São __NTRADES__ operações reais do baseline — com o maior ganho de todo o
      estudo e uma sequência de perdas pequenas no mesmo pedaço de mercado.
    </p>
  </header>

  <div class="palco">
    <div>
      <div class="quadro"><canvas id="tela"></canvas></div>
      <div class="controles">
        <button id="tocar" class="principal">▶ Tocar</button>
        <button id="voltar">◀ Passo</button>
        <button id="avancar">Passo ▶</button>
        <button id="reiniciar">↻ Reiniciar</button>
        <span class="rotulo-ctrl">Candle</span>
        <input type="range" id="cursor" min="1" value="1">
        <span class="rotulo-ctrl">Velocidade</span>
        <input type="range" id="velocidade" min="1" max="20" value="9" style="flex:0 1 90px">
      </div>

      <div class="legenda">
        <span><i style="background:var(--canal)"></i>médias de máxima e de mínima (o canal)</span>
        <span><i style="background:var(--alta)"></i>compra</span>
        <span><i style="background:var(--baixa)"></i>venda</span>
      </div>
    </div>

    <aside class="painel">
      <h2 class="painel-titulo">Estado agora</h2>
      <div class="estado">
        <div><span>Data / hora (HK)</span><span id="e-tempo">—</span></div>
        <div><span>Preço</span><span id="e-preco">—</span></div>
        <div><span>Média das máximas</span><span id="e-sup">—</span></div>
        <div><span>Média das mínimas</span><span id="e-inf">—</span></div>
        <div><span>Largura do canal</span><span id="e-larg">—</span></div>
        <div><span>Posição</span><span id="e-pos" class="pos-nenhuma">nenhuma</span></div>
        <div><span>Aberta em</span><span id="e-abertura">—</span></div>
        <div><span>Resultado aberto</span><span id="e-flutuante">—</span></div>
      </div>

      <h2 class="painel-titulo">Acumulado no trecho</h2>
      <div class="estado">
        <div><span>Operações fechadas</span><span id="e-n">0</span></div>
        <div><span>Ganhos / perdas</span><span id="e-gp">0 / 0</span></div>
        <div><span>Resultado líquido</span><span id="e-total">0 pts</span></div>
      </div>

      <h2 class="painel-titulo">Operações</h2>
      <div class="registro" id="registro"></div>
    </aside>
  </div>

  <div class="explicacao">
    <h3>O que você está vendo</h3>
    <p>
      As duas linhas são as médias móveis de 20 períodos — uma calculada sobre as
      <strong>máximas</strong>, outra sobre as <strong>mínimas</strong>. Elas formam o canal.
      O ponto que não dá para ver num gráfico estático: <strong>o canal desenhado em cada
      candle é calculado apenas com os 20 candles ANTERIORES a ele.</strong> O candle que
      rompe nunca entra no cálculo do canal que ele rompe.
    </p>
    <ul>
      <li><strong>Entrada:</strong> o candle anterior fechou dentro do canal e o atual fecha
          fora. Para cima é compra, para baixo é venda. Preço que já vinha de fora não
          gera entrada nova — por isso não há um sinal a cada candle da tendência.</li>
      <li><strong>Saída:</strong> rompimento da média oposta. Comprado sai quando o preço
          fecha abaixo da média das mínimas.</li>
      <li><strong>Inversão:</strong> repare que a saída quase sempre vira uma entrada
          contrária no mesmo candle. É o mesmo evento — o preço estava dentro do canal e
          fechou fora do outro lado. Na prática a estratégia fica
          <strong>sempre posicionada</strong>, virando de lado.</li>
    </ul>
    <p>
      O trecho foi escolhido justamente por conter os dois regimes: a sequência de perdas
      pequenas no vaivém e o movimento longo que paga tudo. É o retrato do sistema
      inteiro — <strong>erra muito, erra barato, acerta pouco e acerta caro.</strong>
    </p>
  </div>
</div>

<script>
const DADOS = __DADOS__;
const C = DADOS.candles, TRADES = DADOS.trades;

const porTempo = {};
TRADES.forEach((t, i) => {
  (porTempo[t.entrada] ||= []).push({tipo: 'entrada', t, i});
  (porTempo[t.saida]   ||= []).push({tipo: 'saida',   t, i});
});

const tela = document.getElementById('tela');
const ctx = tela.getContext('2d');
let indice = 1, tocando = false, ultimoQuadro = 0;

const cor = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt = n => n.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});

function dimensionar() {
  const r = tela.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  tela.width = r.width * dpr; tela.height = r.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return {w: r.width, h: r.height};
}

function desenhar() {
  const {w, h} = dimensionar();
  const padE = 8, padD = 62, padT = 14, padB = 26;
  const JANELA = 90;
  const ini = Math.max(0, indice - JANELA), fim = indice;
  const vis = C.slice(ini, fim);
  if (!vis.length) return;

  ctx.fillStyle = cor('--fundo-grafico');
  ctx.fillRect(0, 0, w, h);

  let lo = Infinity, hi = -Infinity;
  vis.forEach(k => {
    lo = Math.min(lo, k.l, k.inf ?? k.l);
    hi = Math.max(hi, k.h, k.sup ?? k.h);
  });
  const margem = (hi - lo) * 0.08 || 1;
  lo -= margem; hi += margem;

  const larguraArea = w - padE - padD, alturaArea = h - padT - padB;
  const y = p => padT + (hi - p) / (hi - lo) * alturaArea;
  const x = i => padE + (i + 0.5) * (larguraArea / vis.length);
  const larguraVela = Math.max(1.5, larguraArea / vis.length * 0.62);

  // grade e escala
  ctx.strokeStyle = cor('--grade'); ctx.fillStyle = cor('--tinta-fraca');
  ctx.font = '10px "IBM Plex Mono", monospace'; ctx.lineWidth = 1;
  for (let k = 0; k <= 4; k++) {
    const p = lo + (hi - lo) * k / 4, yy = Math.round(y(p)) + .5;
    ctx.beginPath(); ctx.moveTo(padE, yy); ctx.lineTo(w - padD, yy); ctx.stroke();
    ctx.textAlign = 'left'; ctx.fillText(fmt(p), w - padD + 6, yy + 3);
  }

  // velas
  vis.forEach((k, i) => {
    const alta = k.c >= k.o;
    ctx.strokeStyle = ctx.fillStyle = alta ? cor('--alta') : cor('--baixa');
    ctx.lineWidth = 1;
    const cx = Math.round(x(i)) + .5;
    ctx.beginPath(); ctx.moveTo(cx, y(k.h)); ctx.lineTo(cx, y(k.l)); ctx.stroke();
    const topo = y(Math.max(k.o, k.c)), base = y(Math.min(k.o, k.c));
    ctx.fillRect(cx - larguraVela / 2, topo, larguraVela, Math.max(1, base - topo));
  });

  // canal
  [['sup', 0], ['inf', 0]].forEach(([campo]) => {
    ctx.strokeStyle = cor('--canal'); ctx.lineWidth = 1.4;
    ctx.beginPath(); let iniciado = false;
    vis.forEach((k, i) => {
      if (k[campo] == null) { iniciado = false; return; }
      const px = x(i), py = y(k[campo]);
      if (!iniciado) { ctx.moveTo(px, py); iniciado = true; } else ctx.lineTo(px, py);
    });
    ctx.stroke();
  });

  // marcas de operacao
  vis.forEach((k, i) => {
    const eventos = porTempo[k.t]; if (!eventos) return;
    eventos.forEach(ev => {
      const compra = ev.t.lado === 'comprado';
      const entrada = ev.tipo === 'entrada';
      const px = x(i);
      ctx.fillStyle = compra ? cor('--alta') : cor('--baixa');
      if (entrada) {
        const py = compra ? y(k.l) + 13 : y(k.h) - 13, s = 6;
        ctx.beginPath();
        if (compra) { ctx.moveTo(px, py - s); ctx.lineTo(px - s, py + s); ctx.lineTo(px + s, py + s); }
        else        { ctx.moveTo(px, py + s); ctx.lineTo(px - s, py - s); ctx.lineTo(px + s, py - s); }
        ctx.closePath(); ctx.fill();
      } else {
        ctx.globalAlpha = .85;
        ctx.beginPath(); ctx.arc(px, y(ev.t.preco_saida), 3.6, 0, Math.PI * 2);
        ctx.fill(); ctx.globalAlpha = 1;
      }
    });
  });

  // eixo do tempo
  ctx.fillStyle = cor('--tinta-fraca'); ctx.textAlign = 'center';
  [0, Math.floor(vis.length / 2), vis.length - 1].forEach(i => {
    if (vis[i]) ctx.fillText(vis[i].t.slice(5, 16), x(i), h - 9);
  });
}

function atualizarPainel() {
  const k = C[indice - 1];
  document.getElementById('e-tempo').textContent = k.t;
  document.getElementById('e-preco').textContent = fmt(k.c);
  document.getElementById('e-sup').textContent = k.sup ? fmt(k.sup) : '—';
  document.getElementById('e-inf').textContent = k.inf ? fmt(k.inf) : '—';
  document.getElementById('e-larg').textContent =
    (k.sup && k.inf) ? fmt(k.sup - k.inf) + ' pts' : '—';

  const agora = k.t;
  const aberta = TRADES.find(t => t.entrada <= agora && t.saida > agora);
  const elPos = document.getElementById('e-pos');
  if (aberta) {
    const compra = aberta.lado === 'comprado';
    elPos.textContent = compra ? 'COMPRADO' : 'VENDIDO';
    elPos.className = compra ? 'pos-comprado' : 'pos-vendido';
    document.getElementById('e-abertura').textContent = fmt(aberta.preco_entrada);
    const flut = (k.c - aberta.preco_entrada) * (compra ? 1 : -1);
    const el = document.getElementById('e-flutuante');
    el.textContent = (flut >= 0 ? '+' : '') + flut.toFixed(0) + ' pts';
    el.style.color = flut >= 0 ? cor('--alta') : cor('--baixa');
  } else {
    elPos.textContent = 'nenhuma'; elPos.className = 'pos-nenhuma';
    document.getElementById('e-abertura').textContent = '—';
    const el = document.getElementById('e-flutuante');
    el.textContent = '—'; el.style.color = '';
  }

  const fechados = TRADES.filter(t => t.saida <= agora);
  const ganhos = fechados.filter(t => t.pontos > 0).length;
  const total = fechados.reduce((s, t) => s + t.pontos, 0);
  document.getElementById('e-n').textContent = fechados.length;
  document.getElementById('e-gp').textContent = ganhos + ' / ' + (fechados.length - ganhos);
  const elTotal = document.getElementById('e-total');
  elTotal.textContent = (total >= 0 ? '+' : '') + total.toFixed(0) + ' pts';
  elTotal.style.color = total >= 0 ? cor('--alta') : cor('--baixa');

  const reg = document.getElementById('registro');
  reg.innerHTML = fechados.slice().reverse().map(t => `
    <div class="registro-item ${t.pontos > 0 ? 'ganho' : 'perda'}">
      <span>${t.lado === 'comprado' ? '▲' : '▼'} ${t.entrada.slice(5, 16)}</span>
      <b>${t.pontos > 0 ? '+' : ''}${t.pontos.toFixed(0)}</b>
    </div>`).join('');
}

function render() { desenhar(); atualizarPainel(); document.getElementById('cursor').value = indice; }

function passo(n) {
  indice = Math.max(1, Math.min(C.length, indice + n));
  if (indice >= C.length) pausar();
  render();
}

const btTocar = document.getElementById('tocar');
function pausar() { tocando = false; btTocar.textContent = '▶ Tocar'; }
function tocar() {
  if (indice >= C.length) indice = 1;
  tocando = true; btTocar.textContent = '❚❚ Pausar';
  ultimoQuadro = performance.now(); requestAnimationFrame(laco);
}
function laco(agora) {
  if (!tocando) return;
  const vel = +document.getElementById('velocidade').value;
  if (agora - ultimoQuadro >= 620 / vel) { ultimoQuadro = agora; passo(1); }
  requestAnimationFrame(laco);
}

btTocar.onclick = () => tocando ? pausar() : tocar();
document.getElementById('avancar').onclick = () => { pausar(); passo(1); };
document.getElementById('voltar').onclick = () => { pausar(); passo(-1); };
document.getElementById('reiniciar').onclick = () => { pausar(); indice = 1; render(); };
document.getElementById('cursor').oninput = e => { pausar(); indice = +e.target.value; render(); };
document.getElementById('cursor').max = C.length;

window.addEventListener('resize', render);
window.addEventListener('keydown', e => {
  if (e.key === ' ') { e.preventDefault(); tocando ? pausar() : tocar(); }
  if (e.key === 'ArrowRight') { pausar(); passo(1); }
  if (e.key === 'ArrowLeft')  { pausar(); passo(-1); }
});

indice = 25;   // comeca com o canal ja formado
render();
</script>
"""

periodo = f"{dados['periodo'][0][:10]} a {dados['periodo'][1][:10]}"
html = (HTML
        .replace("__DADOS__", json.dumps(dados, ensure_ascii=False))
        .replace("__PERIODO__", periodo)
        .replace("__NTRADES__", str(len(dados["trades"]))))
SAIDA.write_text(html, encoding="utf-8")
print(f"gerado: {SAIDA}  ({SAIDA.stat().st_size/1024:.0f} KB)")
print(f"periodo: {periodo} | trades: {len(dados['trades'])}")
