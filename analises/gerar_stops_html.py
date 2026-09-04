"""Monta o HTML explicativo dos stops, com o trade real embutido."""
import json, pathlib

TRACE = pathlib.Path(r"C:\dev\hk50-bot\reports\trace_stops.json")
SAIDA = pathlib.Path(__file__).parent / "onde-fica-o-stop.html"
dados = json.loads(TRACE.read_text(encoding="utf-8"))

HTML = r"""<title>Onde Fica o Stop</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">

<style>
  :root {
    --papel:#F6F8F6; --superficie:#FFF; --superficie-2:#EDF1EE;
    --tinta:#131C19; --tinta-media:#3D4E48; --tinta-fraca:#6E807A;
    --linha:#DCE3DF; --linha-forte:#C2CEC8;
    --jade:#0E6B58; --jade-fraco:#E2F0EB;
    --ambar:#9C6612; --ambar-fraco:#F7EEDC;
    --tijolo:#A33A2C; --tijolo-fraco:#F7E7E4;
    --alta:#1B8A4B; --baixa:#C03A2B; --canal:#131C19;
    --fundo-grafico:#FFF; --grade:#EDEFED;
    --sombra:0 1px 2px rgba(19,28,25,.05),0 8px 24px -16px rgba(19,28,25,.22);
    --display:"Archivo","Helvetica Neue",Arial,sans-serif;
    --texto:"Source Serif 4",Georgia,serif;
    --dado:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  }
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
    --papel:#0F1513; --superficie:#161E1B; --superficie-2:#1D2724;
    --tinta:#E3EAE6; --tinta-media:#AFBEB8; --tinta-fraca:#7E8F89;
    --linha:#263230; --linha-forte:#35443F;
    --jade:#4FB79C; --jade-fraco:#16302A;
    --ambar:#D9A251; --ambar-fraco:#322616;
    --tijolo:#E08573; --tijolo-fraco:#331D19;
    --alta:#35C97A; --baixa:#E8604D; --canal:#C8D6D0;
    --fundo-grafico:#101614; --grade:#1D2724;
    --sombra:0 1px 2px rgba(0,0,0,.3),0 8px 24px -16px rgba(0,0,0,.7);
  }}
  :root[data-theme="dark"]{
    --papel:#0F1513; --superficie:#161E1B; --superficie-2:#1D2724;
    --tinta:#E3EAE6; --tinta-media:#AFBEB8; --tinta-fraca:#7E8F89;
    --linha:#263230; --linha-forte:#35443F;
    --jade:#4FB79C; --jade-fraco:#16302A;
    --ambar:#D9A251; --ambar-fraco:#322616;
    --tijolo:#E08573; --tijolo-fraco:#331D19;
    --alta:#35C97A; --baixa:#E8604D; --canal:#C8D6D0;
    --fundo-grafico:#101614; --grade:#1D2724;
    --sombra:0 1px 2px rgba(0,0,0,.3),0 8px 24px -16px rgba(0,0,0,.7);
  }

  *{box-sizing:border-box}
  body{background:var(--papel);color:var(--tinta);font-family:var(--texto);
       font-size:17px;line-height:1.62;-webkit-font-smoothing:antialiased}
  .envelope{max-width:1060px;margin:0 auto;padding:0 26px 90px}

  header{padding:64px 0 32px;border-bottom:2px solid var(--tinta);
         display:flex;flex-direction:column;gap:15px}
  .eyebrow{font-family:var(--dado);font-size:10px;letter-spacing:.16em;
           text-transform:uppercase;color:var(--jade)}
  h1{font-family:var(--display);font-weight:700;
     font-size:clamp(2.1rem,5.2vw,3.4rem);line-height:1.04;
     letter-spacing:-.028em;margin:0;text-wrap:balance}
  .resumo{font-size:1.12rem;color:var(--tinta-media);max-width:64ch;margin:0}

  section{margin-top:56px}
  h2{font-family:var(--display);font-weight:700;font-size:1.5rem;
     letter-spacing:-.021em;margin:0 0 6px;padding-bottom:10px;
     border-bottom:1px solid var(--linha-forte);text-wrap:balance}
  h3{font-family:var(--display);font-weight:600;font-size:1.02rem;
     margin:28px 0 10px;letter-spacing:-.008em}
  section>p{max-width:68ch}
  p{margin:0 0 15px}
  strong{font-weight:600}

  .quadro{background:var(--fundo-grafico);border:1px solid var(--linha);
          border-radius:4px;overflow:hidden;box-shadow:var(--sombra);margin:20px 0 6px}
  canvas{display:block;width:100%;height:420px}
  .legenda-graf{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:22px;
                font-family:var(--dado);font-size:.76rem;color:var(--tinta-media)}
  .legenda-graf span{display:flex;align-items:center;gap:7px}
  .legenda-graf i{width:20px;height:0;border-top:2px solid var(--c);display:inline-block}
  .legenda-graf i.tracejado{border-top-style:dashed}

  .rolagem{overflow-x:auto;margin:18px 0 8px;border:1px solid var(--linha);
           border-radius:3px;background:var(--superficie)}
  table{width:100%;border-collapse:collapse;font-family:var(--dado);
        font-size:.85rem;font-variant-numeric:tabular-nums}
  caption{caption-side:top;text-align:left;padding:13px 16px;font-family:var(--dado);
          font-size:10px;letter-spacing:.13em;text-transform:uppercase;
          color:var(--tinta-fraca);border-bottom:1px solid var(--linha);
          background:var(--superficie-2)}
  th,td{padding:8px 14px;text-align:right;border-bottom:1px solid var(--linha)}
  th{font-weight:600;color:var(--tinta-media);font-size:.76rem;white-space:nowrap}
  th:first-child,td:first-child{text-align:left;font-family:var(--texto);
                                font-size:.93rem;white-space:nowrap}
  tbody tr:last-child td{border-bottom:0}
  tr.vencedor td{background:var(--jade-fraco)}
  tr.perdedor td{background:var(--tijolo-fraco)}
  td.forte{color:var(--jade);font-weight:600}
  td.fraco{color:var(--tijolo);font-weight:600}
  td.neutro{color:var(--tinta-fraca)}

  .nota{background:var(--superficie);border:1px solid var(--linha);
        border-left:3px solid var(--jade);border-radius:3px;padding:19px 21px;margin:24px 0}
  .nota.alerta{border-left-color:var(--ambar)}
  .nota.contra{border-left-color:var(--tijolo)}
  .nota h4{font-family:var(--display);font-weight:600;font-size:.95rem;margin:0 0 8px}
  .nota p{margin:0 0 10px;font-size:.96rem;color:var(--tinta-media)}
  .nota p:last-child{margin-bottom:0}

  ul{margin:0 0 15px;padding-left:20px;max-width:68ch}
  li{margin-bottom:8px}
  li::marker{color:var(--jade)}
  code{font-family:var(--dado);font-size:.87em;background:var(--superficie-2);
       padding:1px 5px;border-radius:2px}

  .atr-svg{background:var(--superficie);border:1px solid var(--linha);
           border-radius:4px;padding:18px;margin:20px 0}
  .atr-svg svg{width:100%;height:auto;display:block}

  footer{margin-top:64px;padding-top:20px;border-top:1px solid var(--linha-forte);
         font-family:var(--dado);font-size:.84rem;color:var(--tinta-fraca)}
  footer p{max-width:76ch;margin-bottom:8px}
</style>

<div class="envelope">

<header>
  <div class="eyebrow">HK50 · M15 · 604 operações · filtro de volume ligado</div>
  <h1>Onde Fica o Stop</h1>
  <p class="resumo">
    O que é o ATR, onde cada tipo de stop coloca a ordem na mesa, e por que as
    duas ideias que parecem mais prudentes — trailing e breakeven — são as que
    destroem a estratégia.
  </p>
</header>

<section>
  <h2>O que é o ATR</h2>
  <p>
    <strong>Average True Range</strong> é a amplitude média que o preço percorre por
    candle, nos últimos 14 candles. O “True Range” de um candle é o maior entre três
    distâncias:
  </p>

  <div class="atr-svg">
    <svg viewBox="0 0 720 200" role="img" aria-label="As tres medidas do True Range">
      <line x1="30" y1="52" x2="690" y2="52" stroke="currentColor" stroke-width="1" opacity=".18" stroke-dasharray="3 4"/>
      <text x="34" y="46" font-family="IBM Plex Mono,monospace" font-size="10" fill="currentColor" opacity=".6">fechamento do candle anterior</text>

      <!-- candle anterior -->
      <line x1="110" y1="40" x2="110" y2="70" stroke="currentColor" stroke-width="1.2"/>
      <rect x="102" y="44" width="16" height="8" fill="var(--baixa)"/>
      <text x="110" y="92" font-family="IBM Plex Mono,monospace" font-size="10" fill="currentColor" opacity=".6" text-anchor="middle">anterior</text>

      <!-- candle atual, com gap -->
      <line x1="300" y1="98" x2="300" y2="170" stroke="currentColor" stroke-width="1.4"/>
      <rect x="290" y="112" width="20" height="42" fill="var(--alta)"/>
      <text x="300" y="188" font-family="IBM Plex Mono,monospace" font-size="10" fill="currentColor" opacity=".6" text-anchor="middle">atual</text>

      <!-- medida 1 -->
      <line x1="360" y1="98" x2="360" y2="170" stroke="var(--jade)" stroke-width="2"/>
      <line x1="354" y1="98" x2="366" y2="98" stroke="var(--jade)" stroke-width="2"/>
      <line x1="354" y1="170" x2="366" y2="170" stroke="var(--jade)" stroke-width="2"/>
      <text x="374" y="130" font-family="IBM Plex Mono,monospace" font-size="11" fill="var(--jade)">1 · máxima − mínima</text>
      <text x="374" y="146" font-family="IBM Plex Mono,monospace" font-size="9.5" fill="currentColor" opacity=".55">a amplitude do próprio candle</text>

      <!-- medida 2 -->
      <line x1="520" y1="52" x2="520" y2="98" stroke="var(--ambar)" stroke-width="2"/>
      <line x1="514" y1="52" x2="526" y2="52" stroke="var(--ambar)" stroke-width="2"/>
      <line x1="514" y1="98" x2="526" y2="98" stroke="var(--ambar)" stroke-width="2"/>
      <text x="534" y="70" font-family="IBM Plex Mono,monospace" font-size="11" fill="var(--ambar)">2 · |máxima − fech. anterior|</text>

      <!-- medida 3 -->
      <line x1="520" y1="52" x2="520" y2="170" stroke="var(--tijolo)" stroke-width="2" stroke-dasharray="4 3" opacity=".8"/>
      <text x="534" y="164" font-family="IBM Plex Mono,monospace" font-size="11" fill="var(--tijolo)">3 · |mínima − fech. anterior|</text>
      <text x="534" y="180" font-family="IBM Plex Mono,monospace" font-size="9.5" fill="currentColor" opacity=".55">é a maior das três aqui: o gap conta</text>
    </svg>
  </div>

  <p>
    As duas últimas medidas existem para que <strong>um gap conte como movimento</strong>,
    e não como calmaria. Sem elas, um candle pequeno que abriu 200 pontos acima do
    fechamento anterior pareceria um momento tranquilo.
  </p>

  <div class="nota">
    <h4>Por que isso importa para o stop</h4>
    <p>
      No HK50 em M15 o ATR fica em torno de <strong>60 pontos</strong>, mas varia muito
      ao longo do dia: cerca de <strong>135 às 09:30</strong> e <strong>35 às 16:00</strong>
      (hora de Hong Kong).
    </p>
    <p>
      Um stop de <strong>2× ATR</strong> vira 270 pontos na abertura e 70 no fim da
      tarde. Ele se ajusta sozinho. Um stop fixo de 150 pontos seria apertado demais
      cedo e frouxo demais tarde — que é exatamente o problema que te fez operar com
      stop visual em vez de deixar na mesa.
    </p>
  </div>
</section>

<section>
  <h2>Onde cada stop fica, num trade de verdade</h2>
  <p id="descricao-trade"></p>

  <div class="quadro"><canvas id="tela"></canvas></div>
  <div class="legenda-graf">
    <span style="--c:var(--canal)"><i></i>canal de médias</span>
    <span style="--c:var(--jade)"><i></i>entrada</span>
    <span style="--c:var(--tijolo)"><i class="tracejado"></i>stop atingido</span>
    <span style="--c:var(--ambar)"><i class="tracejado"></i>stop que sobreviveu</span>
  </div>

  <div class="rolagem">
    <table>
      <caption>Os quatro stops nesta operação</caption>
      <thead>
        <tr><th>Tipo de stop</th><th>Nível</th><th>Distância</th><th>Em ATR</th><th>Sobreviveu?</th></tr>
      </thead>
      <tbody id="tabela-niveis"></tbody>
    </table>
  </div>

  <div class="nota alerta">
    <h4>A lição deste trade</h4>
    <p>
      O preço andou <strong id="recuo-txt"></strong> contra a posição antes de virar e
      entregar <strong id="ganho-txt"></strong>. Os stops mais apertados morrem nesse
      recuo — e o trade que teria pago vira prejuízo.
    </p>
    <p>
      É o dilema inteiro numa imagem: <strong>stop apertado transforma vencedor em
      perdedor; stop largo deixa a perda crescer.</strong> O que os dados dizem sobre
      onde fica o ponto certo está na próxima seção.
    </p>
  </div>
</section>

<section>
  <h2>O que cada stop rendeu</h2>
  <p>
    Período de teste (a partir de março de 2023, fora dos 12 meses iniciais), com o
    filtro de volume ligado e todos os custos aplicados.
  </p>

  <div class="rolagem">
    <table>
      <caption>Comparativo dos tipos de stop · 474 a 552 operações conforme o tipo</caption>
      <thead>
        <tr><th>Stop</th><th>Trades</th><th>Pontos</th><th>Por trade</th><th>Fator</th><th>Sharpe</th></tr>
      </thead>
      <tbody>
        <tr><td>Nenhum (regra base)</td><td>474</td><td>+5.786</td><td>+12,2</td><td class="neutro">1,14</td><td>0,78</td></tr>
        <tr class="vencedor"><td><strong>ATR 1,5×</strong></td><td>494</td><td class="forte">+8.059</td><td>+16,3</td><td class="forte">1,23</td><td>1,15</td></tr>
        <tr class="vencedor"><td><strong>ATR 1,75×</strong></td><td>488</td><td class="forte">+8.449</td><td>+17,3</td><td class="forte">1,23</td><td>1,18</td></tr>
        <tr class="vencedor"><td><strong>ATR 2,0× — escolhido</strong></td><td>482</td><td class="forte">+7.705</td><td>+16,0</td><td class="forte">1,21</td><td>1,07</td></tr>
        <tr><td>ATR 2,5×</td><td>476</td><td>+7.787</td><td>+16,4</td><td>1,20</td><td>1,08</td></tr>
        <tr><td>Canal externo (folga 0,25)</td><td>480</td><td>+7.487</td><td>+15,6</td><td>1,19</td><td>1,03</td></tr>
        <tr><td>ATR 4,0×</td><td>474</td><td>+7.330</td><td>+15,5</td><td>1,18</td><td>0,99</td></tr>
        <tr><td>Candle de entrada (folga 1,0)</td><td>487</td><td>+6.350</td><td>+13,0</td><td>1,17</td><td>0,91</td></tr>
        <tr><td>ATR 1,0×</td><td>536</td><td>+1.022</td><td>+1,9</td><td class="neutro">1,03</td><td>0,22</td></tr>
        <tr class="perdedor"><td>Candle de entrada (folga 0,25)</td><td>533</td><td>+716</td><td>+1,3</td><td class="neutro">1,02</td><td>0,17</td></tr>
        <tr class="perdedor"><td>Trailing 4,0× ATR</td><td>504</td><td class="fraco">−2.186</td><td>−4,3</td><td class="fraco">0,95</td><td>−0,30</td></tr>
        <tr class="perdedor"><td>Breakeven em 1 ATR</td><td>512</td><td class="fraco">−5.641</td><td>−11,0</td><td class="fraco">0,84</td><td>−0,78</td></tr>
        <tr class="perdedor"><td>Trailing 2,5× ATR</td><td>552</td><td class="fraco">−10.367</td><td>−18,8</td><td class="fraco">0,73</td><td>−1,86</td></tr>
      </tbody>
    </table>
  </div>

  <p>
    O platô entre <strong>1,5× e 2,5× ATR</strong> é largo e suave — todos entre 1,20 e
    1,23. Escolhi <strong>2,0×</strong>, que é o meio, não o pico. Abaixo de 1,5 a curva
    desaba: o stop passa a ser atingido pelo ruído normal do preço.
  </p>
</section>

<section>
  <h2>Por que trailing e breakeven destroem a estratégia</h2>
  <p>
    As duas ideias que mais parecem prudentes — “vai subindo o stop” e “depois de um
    tanto de lucro não perco mais” — são as duas piores da tabela. A anatomia mostra
    exatamente onde elas quebram.
  </p>

  <div class="rolagem">
    <table>
      <caption>Anatomia: o que cada stop faz com ganhos e perdas</caption>
      <thead>
        <tr><th>Configuração</th><th>Vencedores</th><th>Ganho médio</th><th>Perdedores</th><th>Perda média</th><th>Top 10 trades</th></tr>
      </thead>
      <tbody>
        <tr><td>Sem stop</td><td>228</td><td>257</td><td>366</td><td>−145</td><td class="neutro">11.240</td></tr>
        <tr class="vencedor"><td><strong>ATR 1,5×</strong></td><td>210</td><td class="forte">256</td><td>406</td><td class="forte">−111</td><td class="forte">11.240 (=)</td></tr>
        <tr class="perdedor"><td>Trailing 2,5×</td><td>220</td><td class="fraco">156</td><td>465</td><td>−103</td><td class="fraco">6.643 (−41%)</td></tr>
        <tr class="perdedor"><td>Breakeven em 1 ATR</td><td class="fraco">130</td><td>287</td><td>514</td><td>−90</td><td>10.804</td></tr>
      </tbody>
    </table>
  </div>

  <div class="nota contra">
    <h4>Trailing corta a cauda que paga tudo</h4>
    <p>
      O ganho médio despenca de <strong>257 para 156</strong> e os dez melhores trades
      encolhem <strong>41%</strong>. Ele realmente reduz a perda média — mas cobra por
      isso um pedaço muito maior do lucro.
    </p>
    <p>
      Lembre do que o estudo anterior mostrou: sem os 10 melhores trades a estratégia
      perde 5.618 pontos. <strong>É uma estratégia que vive da cauda.</strong> Qualquer
      regra que aperte o ganho ataca justamente o que a sustenta.
    </p>
  </div>

  <div class="nota contra">
    <h4>Breakeven mata a taxa de acerto</h4>
    <p>
      Os vencedores caem de <strong>228 para 130</strong> — quase pela metade. O stop
      colocado no preço de entrada é atingido pelo recuo normal <em>antes</em> de o
      movimento se desenvolver, e cada um desses vira uma pequena perda (o custo de
      transação continua lá).
    </p>
    <p>
      O ganho médio até sobe, para 287 — mas é sobrevivência: só os trades que nunca
      recuaram chegam ao fim. E eles são poucos demais para pagar os 514 perdedores.
    </p>
  </div>

  <div class="nota">
    <h4>O ATR fixo é cirúrgico</h4>
    <p>
      Ganho médio <strong>256</strong> contra 257 sem stop. Top 10 trades
      <strong>idênticos</strong>. E a perda média cai de <strong>−145 para −111</strong>.
    </p>
    <p>
      Ele corta a perda sem encostar no ganho — que é exatamente o que você pediu.
      A diferença em relação ao trailing é que o stop fixo <em>não sobe</em>: ele aceita
      o recuo dentro de um movimento que ainda está vivo.
    </p>
  </div>
</section>

<section>
  <h2>Onde isso deixa a estratégia</h2>
  <div class="rolagem">
    <table>
      <caption>Evolução do baseline · base completa, todos os custos</caption>
      <thead>
        <tr><th>Configuração</th><th>Trades</th><th>Acerto</th><th>Pontos</th><th>Fator</th><th>Sharpe</th></tr>
      </thead>
      <tbody>
        <tr><td>Original (sem filtro, sem stop)</td><td>1.211</td><td>35%</td><td class="fraco">−1.926</td><td class="fraco">0,98</td><td>−0,10</td></tr>
        <tr><td>+ filtro de volume 0,70</td><td>594</td><td>38%</td><td>+5.568</td><td>1,10</td><td>0,59</td></tr>
        <tr class="vencedor"><td><strong>+ stop ATR 2,0×</strong></td><td>604</td><td>36%</td><td class="forte">+7.481</td><td class="forte">1,15</td><td class="forte">0,81</td></tr>
      </tbody>
    </table>
  </div>
  <p>
    O custo de transação, que consumia <strong>108% do lucro bruto</strong> na versão
    original, agora consome <strong>49%</strong>. Não porque ficou mais barato — porque
    a estratégia parou de operar metade das vezes em que não deveria.
  </p>
</section>

<footer>
  <p>
    Gerado por <code>analises/exportar_stops.py</code> sobre 27.099 candles M15 do HK50.
    Stops implementados em <code>strategy/stops.py</code> e cobertos por 47 testes.
    Custos: spread real de cada candle, derrapagem de 0,5 ponto por ponta, comissão de
    0,1 USD por lote e swap de 5,50 pontos por noite comprado, triplo às sextas.
  </p>
  <p>
    O stop é executado no <strong>pior</strong> entre o nível e a abertura do candle —
    stop garante execução, não preço. Assumir preenchimento no nível exato inflava o
    resultado de fator 1,12 para 1,39.
  </p>
</footer>
</div>

<script>
const D = __DADOS__;
const C = D.candles, N = D.niveis, T = D.trade;
const comprado = T.lado === 'comprado';
const recuo = T.excursao_contraria;

const rotulos = {
  atr_2:          "ATR 2,0×",
  atr_1_5:        "ATR 1,5×",
  candle_entrada: "Candle de entrada (folga 0,25 ATR)",
  canal_externo:  "Canal externo (folga 0,25 ATR)",
};

document.getElementById('descricao-trade').innerHTML =
  `Operação <strong>${comprado ? 'de compra' : 'de venda'}</strong> em ${T.entrada}, ` +
  `encerrada em ${T.saida} com <strong>${T.pontos > 0 ? '+' : ''}${T.pontos} pontos</strong>. ` +
  `O ATR no momento da entrada era de <strong>${T.atr} pontos</strong>.`;
document.getElementById('recuo-txt').textContent = recuo.toFixed(0) + ' pontos';
document.getElementById('ganho-txt').textContent = '+' + T.pontos + ' pontos';

const corpoTabela = document.getElementById('tabela-niveis');
corpoTabela.innerHTML = Object.entries(N).map(([k, v]) => {
  const dist = Math.abs(T.preco_entrada - v);
  const sobreviveu = dist > recuo;
  return `<tr class="${sobreviveu ? 'vencedor' : 'perdedor'}">
    <td>${rotulos[k]}</td>
    <td>${v.toLocaleString('pt-BR',{minimumFractionDigits:2})}</td>
    <td>${dist.toFixed(0)} pts</td>
    <td>${(dist / T.atr).toFixed(2)} ATR</td>
    <td class="${sobreviveu ? 'forte' : 'fraco'}">${sobreviveu ? 'sim' : 'não — trade morreria'}</td>
  </tr>`;
}).join('');

const tela = document.getElementById('tela'), ctx = tela.getContext('2d');
const cor = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function desenhar() {
  const r = tela.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  tela.width = r.width * dpr; tela.height = r.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = r.width, h = r.height, padE = 8, padD = 200, padT = 16, padB = 26;

  ctx.fillStyle = cor('--fundo-grafico'); ctx.fillRect(0, 0, w, h);

  let lo = Infinity, hi = -Infinity;
  C.forEach(k => { lo = Math.min(lo, k.l, k.inf ?? k.l); hi = Math.max(hi, k.h, k.sup ?? k.h); });
  Object.values(N).forEach(v => { lo = Math.min(lo, v); hi = Math.max(hi, v); });
  const marg = (hi - lo) * .07 || 1; lo -= marg; hi += marg;

  const areaL = w - padE - padD, areaA = h - padT - padB;
  const y = p => padT + (hi - p) / (hi - lo) * areaA;
  const x = i => padE + (i + .5) * (areaL / C.length);
  const larg = Math.max(2, areaL / C.length * .62);

  ctx.strokeStyle = cor('--grade'); ctx.lineWidth = 1;
  for (let k = 0; k <= 4; k++) {
    const yy = Math.round(padT + areaA * k / 4) + .5;
    ctx.beginPath(); ctx.moveTo(padE, yy); ctx.lineTo(w - padD, yy); ctx.stroke();
  }

  C.forEach((k, i) => {
    const alta = k.c >= k.o;
    ctx.strokeStyle = ctx.fillStyle = alta ? cor('--alta') : cor('--baixa');
    const cx = Math.round(x(i)) + .5;
    ctx.beginPath(); ctx.moveTo(cx, y(k.h)); ctx.lineTo(cx, y(k.l)); ctx.stroke();
    const t0 = y(Math.max(k.o, k.c)), b0 = y(Math.min(k.o, k.c));
    ctx.fillRect(cx - larg / 2, t0, larg, Math.max(1, b0 - t0));
  });

  ['sup', 'inf'].forEach(campo => {
    ctx.strokeStyle = cor('--canal'); ctx.lineWidth = 1.4;
    ctx.beginPath(); let started = false;
    C.forEach((k, i) => {
      if (k[campo] == null) { started = false; return; }
      const px = x(i), py = y(k[campo]);
      started ? ctx.lineTo(px, py) : (ctx.moveTo(px, py), started = true);
    });
    ctx.stroke();
  });

  // entrada
  const xe = x(D.indice_entrada);
  ctx.strokeStyle = cor('--jade'); ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.moveTo(padE, y(T.preco_entrada)); ctx.lineTo(w - padD, y(T.preco_entrada)); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(xe, padT); ctx.lineTo(xe, h - padB); ctx.stroke();
  ctx.fillStyle = cor('--jade');
  ctx.font = '600 11px "IBM Plex Mono",monospace'; ctx.textAlign = 'left';
  ctx.fillText(`entrada  ${T.preco_entrada.toFixed(2)}`, w - padD + 8, y(T.preco_entrada) + 4);

  // niveis de stop
  ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5;
  Object.entries(N).forEach(([k, v]) => {
    const dist = Math.abs(T.preco_entrada - v);
    const sobreviveu = dist > recuo;
    ctx.strokeStyle = sobreviveu ? cor('--ambar') : cor('--tijolo');
    ctx.beginPath(); ctx.moveTo(padE, y(v)); ctx.lineTo(w - padD, y(v)); ctx.stroke();
    ctx.fillStyle = ctx.strokeStyle;
    ctx.font = '500 10.5px "IBM Plex Mono",monospace';
    ctx.fillText(`${rotulos[k]}  ${(dist / T.atr).toFixed(2)} ATR`, w - padD + 8, y(v) + 4);
  });
  ctx.setLineDash([]);

  ctx.fillStyle = cor('--tinta-fraca'); ctx.textAlign = 'center';
  ctx.font = '10px "IBM Plex Mono",monospace';
  [0, C.length - 1].forEach(i => ctx.fillText(C[i].t.slice(5), x(i), h - 8));
}

desenhar();
window.addEventListener('resize', desenhar);
</script>
"""

SAIDA.write_text(HTML.replace("__DADOS__", json.dumps(dados, ensure_ascii=False)),
                 encoding="utf-8")
print(f"gerado: {SAIDA.name} ({SAIDA.stat().st_size/1024:.0f} KB)")
