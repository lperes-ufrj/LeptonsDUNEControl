// Aba Statistics: desenha os gráficos (SVG) com os números já contados no servidor (estatisticas.py).
// Cada gráfico tem também a sua tabela na página; aqui o desenho, a dica do mouse/teclado e a janela com as samples
// de uma linha da tabela ou de uma barra (os "membros" que o servidor manda junto).
(function () {
  const G = JSON.parse(document.getElementById("dados-graficos").textContent);
  const AM = JSON.parse(document.getElementById("dados-amostras").textContent);   // id -> [run, PID, data, status]
  const NS = "http://www.w3.org/2000/svg";
  const M = { t: 16, r: 14, b: 30, l: 42 };          // margens do desenho
  const cor = (n) => `var(--serie-${n || 1})`;

  function el(nome, attrs, pai) {
    const e = document.createElementNS(NS, nome);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "style") e.style.cssText = v; else e.setAttribute(k, v);
    }
    if (pai) pai.appendChild(e);
    return e;
  }
  function texto(pai, x, y, s, attrs) {
    const e = el("text", Object.assign({ x, y }, attrs), pai);
    e.textContent = s;
    return e;
  }
  const fmt = (x, casas) => (x == null || isNaN(x)) ? "–" : Number(x).toFixed(casas);

  // marcas de eixo "redondas" (1, 2, 2.5, 5 x 10^k)
  function passoRedondo(bruto) {
    if (bruto <= 0) return 1;
    const base = Math.pow(10, Math.floor(Math.log10(bruto)));
    return [1, 2, 2.5, 5, 10].map((m) => m * base).find((v) => v >= bruto);
  }
  function marcas(lo, hi, n, inteiro) {
    let passo = passoRedondo((hi - lo) / n);
    if (inteiro) passo = Math.max(1, Math.ceil(passo));
    const ini = Math.floor(lo / passo) * passo, fim = Math.ceil(hi / passo) * passo;
    const r = [];
    for (let v = ini; v <= fim + passo / 1e6; v += passo) r.push(+v.toFixed(10));
    return r;
  }
  const casasDe = (passo) => passo >= 1 ? 0 : Math.min(4, Math.ceil(-Math.log10(passo) - 1e-9));

  // ---------------- dica (tooltip): o valor em destaque, o nome depois ----------------
  const dica = document.createElement("div");
  dica.className = "dica-grafico";
  dica.hidden = true;
  document.body.appendChild(dica);
  function mostrar(x, y, titulo, linhas) {
    dica.textContent = "";
    if (titulo) { const t = document.createElement("div"); t.className = "dica-titulo"; t.textContent = titulo; dica.appendChild(t); }
    for (const l of linhas) {
      const d = document.createElement("div");
      d.className = "dica-linha";
      if (l.cor) { const k = document.createElement("span"); k.className = "dica-chave"; k.style.background = cor(l.cor); d.appendChild(k); }
      const b = document.createElement("b"); b.textContent = l.valor; d.appendChild(b);
      if (l.nome) { const s = document.createElement("span"); s.textContent = l.nome; d.appendChild(s); }
      dica.appendChild(d);
    }
    dica.hidden = false;
    const w = dica.offsetWidth, h = dica.offsetHeight;
    let px = x + 14, py = y - h - 10;
    if (px + w > window.scrollX + document.documentElement.clientWidth - 8) px = x - w - 14;
    if (py < window.scrollY + 4) py = y + 16;
    dica.style.left = px + "px";
    dica.style.top = py + "px";
  }
  const esconder = () => { dica.hidden = true; };

  // ---------------- janela com as samples de uma linha / barra ----------------
  const dlg = document.getElementById("dlg-membros");
  dlg.querySelectorAll("[data-fechar]").forEach((b) => b.addEventListener("click", () => dlg.close()));
  const temMembros = (g, i) => !!(g.membros && g.membros[i] && g.membros[i].length);
  function rotuloLinha(g, i) {
    if (g.tipo === "histograma") return `${fmt(g.bordas[i], g.casas)} – ${fmt(g.bordas[i + 1], g.casas)} ${g.unidade}`;
    if (g.tipo === "colunas") return g.dicas[i];
    if (g.tipo === "linhas") return "Run " + g.x[i];
    return g.itens[i].nome;
  }
  function abrir(chave, i) {
    const g = G[chave];
    if (!temMembros(g, i)) return;
    esconder();
    const m = g.membros[i], n = new Set(m.map((r) => r[0])).size;
    const fig = document.querySelector(`.grafico[data-g="${chave}"]`).closest(".grafico-bloco");
    document.getElementById("membros-titulo").textContent = fig.dataset.titulo;
    const faixa = document.getElementById("membros-faixa");
    faixa.textContent = rotuloLinha(g, i);
    faixa.classList.toggle("mono", g.tipo === "histograma" || g.tipo === "colunas");
    const contados = g.tipo === "barras" ? g.itens[i].valor : g.tipo === "histograma" ? g.series[0].contagens[i] : m.length;
    const oque = g.tipo === "barras" ? g.unidade : T("values");
    document.getElementById("membros-contagem").textContent = contados !== n
      ? T(n === 1 ? "{v} {what} in 1 sample" : "{v} {what} in {n} samples", { v: contados, what: oque, n })
      : (n === 1 ? T("1 sample") : T("{n} samples", { n }));
    const corpo = document.getElementById("membros-linhas");
    corpo.textContent = "";
    for (const [id, detalhe] of m) {
      const [run, pid, data, st] = AM[id] || ["", "", "", ""];
      const url = dlg.dataset.url + id;
      const tr = document.createElement("tr");
      const td = (txt, cls) => { const c = document.createElement("td"); if (cls) c.className = cls; c.textContent = txt || "–"; tr.appendChild(c); return c; };
      const cRun = td("", "id");
      const a = document.createElement("a"); a.href = url; a.textContent = run || "–"; cRun.textContent = ""; cRun.appendChild(a);
      td(pid, "mono"); td(data, "mono");
      const cSt = td(""); cSt.textContent = "";
      const pill = document.createElement("span"); pill.className = "pill st-" + st.toLowerCase().replace(/ /g, "-"); pill.textContent = st;
      cSt.appendChild(pill);
      td(detalhe, "mono");
      tr.addEventListener("click", (ev) => { if (!ev.target.closest("a")) location.href = url; });
      corpo.appendChild(tr);
    }
    dlg.showModal();
  }
  // linhas das tabelas: clique ou Enter
  document.querySelectorAll(".grafico-bloco").forEach((fig) => {
    const div = fig.querySelector(".grafico[data-g]");
    if (!div) return;
    fig.querySelectorAll(".ver-tabela tr[data-linha]").forEach((tr) => {
      const i = +tr.dataset.linha;
      tr.addEventListener("click", () => abrir(div.dataset.g, i));
      tr.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abrir(div.dataset.g, i); } });
    });
  });

  // hover e foco de uma marca (barra ou faixa): a área sensível é a faixa inteira, não só a parte pintada
  function sensivel(svg, alvo, marca, conteudo, abre) {
    alvo.setAttribute("tabindex", "0");
    if (abre) {
      alvo.classList.add("clicavel");
      alvo.addEventListener("click", abre);
      alvo.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abre(); } });
    }
    const liga = (x, y) => { marca.classList.add("realce"); mostrar(x, y, ...conteudo()); };
    const desliga = () => { marca.classList.remove("realce"); esconder(); };
    alvo.addEventListener("pointermove", (ev) => liga(ev.clientX + window.scrollX, ev.clientY + window.scrollY));
    alvo.addEventListener("pointerleave", desliga);
    alvo.addEventListener("focus", () => {
      const r = alvo.getBoundingClientRect();
      liga(r.left + window.scrollX + r.width / 2, r.top + window.scrollY);
    });
    alvo.addEventListener("blur", desliga);
  }

  const abreSe = (div, g, i) => temMembros(g, i) ? () => abrir(div.dataset.g, i) : null;

  // barra com o canto de cima arredondado (4px) e a base reta, crescendo da linha de base
  function colunaPath(x, y, w, h) {
    const r = Math.min(4, w / 2, h);
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
  function barraPath(x, y, w, h) {          // horizontal: ponta direita arredondada
    const r = Math.min(4, h / 2, w);
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  }

  function eixoY(svg, W, H, ticks, y, casas) {
    for (const v of ticks) {
      el("line", { x1: M.l, x2: W - M.r, y1: y(v), y2: y(v), class: "grade" }, svg);
      texto(svg, M.l - 6, y(v) + 4, fmt(v, casas), { class: "eixo", "text-anchor": "end" });
    }
  }

  // ---------------- colunas no tempo (samples por semana/mês) ----------------
  function colunas(div, g, W) {
    const H = div.clientHeight, n = g.valores.length;
    const svg = el("svg", { width: W, height: H }, div);
    const max = Math.max(1, ...g.valores), ticks = marcas(0, max, 4, true), topo = ticks[ticks.length - 1];
    const y = (v) => H - M.b - (v / topo) * (H - M.t - M.b);
    eixoY(svg, W, H, ticks, y, 0);
    const banda = (W - M.l - M.r) / n, larg = Math.max(2, Math.min(24, banda - 2));
    const pulo = Math.ceil(n * 46 / (W - M.l - M.r));     // rótulos sem encostar
    g.valores.forEach((v, i) => {
      const x0 = M.l + i * banda;
      const marca = v ? el("path", { d: colunaPath(x0 + (banda - larg) / 2, y(v), larg, y(0) - y(v)), class: "marca", style: `fill:${cor(1)}` }, svg) : el("g", {}, svg);
      const alvo = el("rect", { x: x0, y: M.t, width: banda, height: H - M.t - M.b, class: "alvo" }, svg);
      sensivel(svg, alvo, marca, () => [g.dicas[i], [{ valor: String(v), nome: v === 1 ? T("sample") : T("samples") }]], abreSe(div, g, i));
      if (i % pulo === 0) texto(svg, x0 + banda / 2, H - M.b + 16, g.rotulos[i], { class: "eixo", "text-anchor": "middle" });
    });
    el("line", { x1: M.l, x2: W - M.r, y1: y(0), y2: y(0), class: "base" }, svg);
  }

  // ---------------- histograma (faixas iguais; linhas de limite de aceitação) ----------------
  function histograma(div, g, W) {
    const H = div.clientHeight, b = g.bordas, s = g.series[0], nb = b.length - 1;
    const svg = el("svg", { width: W, height: H }, div);
    const max = Math.max(1, ...s.contagens), ticks = marcas(0, max, 4, true), topo = ticks[ticks.length - 1];
    const y = (v) => H - M.b - (v / topo) * (H - M.t - M.b);
    const x = (v) => M.l + (v - b[0]) / (b[nb] - b[0]) * (W - M.l - M.r);
    eixoY(svg, W, H, ticks, y, 0);
    const passo = b[1] - b[0], casasEixo = casasDe(passo);
    const pulo = Math.ceil((nb + 1) * 52 / (W - M.l - M.r));
    s.contagens.forEach((c, i) => {
      const x0 = x(b[i]), w = x(b[i + 1]) - x0;
      const marca = c ? el("path", { d: colunaPath(x0 + 1, y(c), Math.max(1, w - 2), y(0) - y(c)), class: "marca", style: `fill:${cor(s.cor)}` }, svg) : el("g", {}, svg);
      const alvo = el("rect", { x: x0, y: M.t, width: w, height: H - M.t - M.b, class: "alvo" }, svg);
      sensivel(svg, alvo, marca, () => [`${fmt(b[i], g.casas)} – ${fmt(b[i + 1], g.casas)} ${g.unidade}`,
        [{ valor: String(c), nome: s.nome }]], abreSe(div, g, i));
    });
    b.forEach((v, i) => {
      if (i % pulo === 0) texto(svg, x(v), H - M.b + 16, fmt(v, casasEixo), { class: "eixo", "text-anchor": "middle" });
    });
    el("line", { x1: M.l, x2: W - M.r, y1: y(0), y2: y(0), class: "base" }, svg);
    for (const lim of g.limites) {
      if (lim.valor < b[0] || lim.valor > b[nb]) continue;          // limite longe dos dados: só no subtítulo
      const xl = x(lim.valor);
      el("line", { x1: xl, x2: xl, y1: M.t - 4, y2: y(0), class: "limite" }, svg);
      const ancora = xl > W - M.r - 60 ? "end" : "start";
      texto(svg, xl + (ancora === "end" ? -4 : 4), M.t + 6, lim.rotulo, { class: "rotulo-limite", "text-anchor": ancora });
    }
  }

  // ---------------- linhas por run (uma por posição), com a cruz do mouse ----------------
  function linhas(div, g, W) {
    const H = div.clientHeight, xs = g.x, n = xs.length;
    const temRotulos = W > 520;
    const MR = temRotulos ? 108 : M.r;
    const svg = el("svg", { width: W, height: H }, div);
    const todos = g.series.flatMap((s) => s.valores).filter((v) => v != null);
    const ticks = marcas(Math.min(...todos), Math.max(...todos), 5, false);
    const lo = ticks[0], hi = ticks[ticks.length - 1];
    const y = (v) => H - M.b - (v - lo) / ((hi - lo) || 1) * (H - M.t - M.b);
    const x0 = xs[0], x1 = xs[n - 1];
    const x = (v) => M.l + (n === 1 ? 0.5 : (v - x0) / (x1 - x0)) * (W - M.l - MR);
    for (const v of ticks) {
      el("line", { x1: M.l, x2: W - MR, y1: y(v), y2: y(v), class: "grade" }, svg);
      texto(svg, M.l - 6, y(v) + 4, fmt(v, casasDe(ticks[1] - ticks[0])), { class: "eixo", "text-anchor": "end" });
    }
    for (const v of marcas(x0, x1, Math.max(2, Math.floor((W - M.l - MR) / 60)), true)) {
      if (v >= x0 && v <= x1) texto(svg, x(v), H - M.b + 16, String(v), { class: "eixo", "text-anchor": "middle" });
    }
    texto(svg, M.l - 6, H - M.b + 16, "run", { class: "eixo", "text-anchor": "end" });
    const finais = [];
    g.series.forEach((s) => {
      let d = "", novo = true;
      s.valores.forEach((v, i) => {
        if (v == null) { novo = true; return; }
        d += (novo ? "M" : "L") + x(xs[i]).toFixed(1) + "," + y(v).toFixed(1);
        novo = false;
      });
      el("path", { d, class: "linha", style: `stroke:${cor(s.cor)}` }, svg);
      const ult = s.valores.map((v, i) => [v, i]).filter(([v]) => v != null).pop();
      if (ult) {
        el("circle", { cx: x(xs[ult[1]]), cy: y(ult[0]), r: 4, class: "ponto", style: `fill:${cor(s.cor)}` }, svg);
        finais.push({ y: y(ult[0]), x: x(xs[ult[1]]), nome: s.nome, valor: ult[0] });
      }
    });
    // nomes no fim das linhas; se ficarem colados, ficam só a legenda e a dica
    finais.sort((a, b) => a.y - b.y);
    if (temRotulos && finais.every((f, i) => i === 0 || f.y - finais[i - 1].y >= 14)) {
      for (const f of finais) texto(svg, f.x + 8, f.y + 4, f.nome, { class: "rotulo-direto" });
    }
    // cruz: acha a run mais perto do mouse e mostra as três posições
    const cruz = el("line", { y1: M.t, y2: H - M.b, class: "cruz", visibility: "hidden" }, svg);
    const pontos = g.series.map((s) => el("circle", { r: 4, class: "ponto", visibility: "hidden", style: `fill:${cor(s.cor)}` }, svg));
    const alvo = el("rect", { x: M.l - 6, y: M.t, width: W - M.l - MR + 12, height: H - M.t - M.b, class: "alvo" }, svg);
    const maisPerto = (ev) => {
      const px = ev.clientX - svg.getBoundingClientRect().left;
      let i = 0;
      xs.forEach((v, j) => { if (Math.abs(x(v) - px) < Math.abs(x(xs[i]) - px)) i = j; });
      return i;
    };
    if (g.membros) {
      alvo.classList.add("clicavel");
      alvo.addEventListener("click", (ev) => abrir(div.dataset.g, maisPerto(ev)));
    }
    alvo.addEventListener("pointermove", (ev) => {
      const i = maisPerto(ev);
      cruz.setAttribute("x1", x(xs[i])); cruz.setAttribute("x2", x(xs[i])); cruz.setAttribute("visibility", "visible");
      g.series.forEach((s, k) => {
        const v = s.valores[i];
        pontos[k].setAttribute("visibility", v == null ? "hidden" : "visible");
        if (v != null) { pontos[k].setAttribute("cx", x(xs[i])); pontos[k].setAttribute("cy", y(v)); }
      });
      mostrar(ev.clientX + window.scrollX, ev.clientY + window.scrollY, "Run " + xs[i],
        g.series.map((s) => ({ cor: s.cor, valor: fmt(s.valores[i], 1) + " " + g.unidade, nome: s.nome })));
    });
    alvo.addEventListener("pointerleave", () => {
      cruz.setAttribute("visibility", "hidden");
      pontos.forEach((p) => p.setAttribute("visibility", "hidden"));
      esconder();
    });
  }

  // ---------------- barras horizontais (classes, defeitos, internal lots) ----------------
  function barras(div, g, W) {
    const ALT = 30, ESP = 16, n = g.itens.length;
    const H = n * ALT + 8;
    div.style.height = H + "px";
    const svg = el("svg", { width: W, height: H }, div);
    const NOME = Math.min(150, W * 0.36), VAL = 84;
    const max = Math.max(1, ...g.itens.map((i) => i.valor));
    const w = (v) => v / max * (W - NOME - VAL);
    const rotulo = (v) => g.total ? `${v} (${(100 * v / g.total).toFixed(1)}%)` : String(v);
    g.itens.forEach((it, i) => {
      const y0 = 4 + i * ALT, yb = y0 + (ALT - ESP) / 2;
      texto(svg, NOME - 10, y0 + ALT / 2 + 4, it.nome, { class: "eixo-nome", "text-anchor": "end" });
      const marca = it.valor ? el("path", { d: barraPath(NOME, yb, Math.max(2, w(it.valor)), ESP), class: "marca", style: `fill:${cor(1)}` }, svg) : el("g", {}, svg);
      texto(svg, NOME + w(it.valor) + 6, y0 + ALT / 2 + 4, rotulo(it.valor), { class: "valor" });
      const alvo = el("rect", { x: 0, y: y0, width: W, height: ALT, class: "alvo" }, svg);
      sensivel(svg, alvo, marca, () => [it.nome, [{ valor: rotulo(it.valor), nome: g.unidade }]], abreSe(div, g, i));
    });
    el("line", { x1: NOME, x2: NOME, y1: 2, y2: H - 2, class: "base" }, svg);
  }

  const DESENHOS = { colunas, histograma, linhas, barras };
  const larguras = new WeakMap();
  function desenhar(div) {
    const g = G[div.dataset.g], W = Math.floor(div.clientWidth);
    if (!g || !W || larguras.get(div) === W) return;
    larguras.set(div, W);
    div.textContent = "";
    DESENHOS[g.tipo](div, g, W);
  }
  const obs = new ResizeObserver((itens) => itens.forEach((i) => desenhar(i.target)));
  document.querySelectorAll(".grafico[data-g]").forEach((d) => { desenhar(d); obs.observe(d); });
})();
