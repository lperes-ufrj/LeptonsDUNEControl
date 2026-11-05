// Aba Projections: total acumulado de cada etapa (degraus) e a reta da projeção até a meta (tracejada).
// Os números vêm prontos do servidor (projecoes.py); aqui só o desenho, a cruz do mouse e a dica.
(function () {
  const G = JSON.parse(document.getElementById("dados-projecao").textContent);
  if (!G) return;
  const NS = "http://www.w3.org/2000/svg";
  const M = { t: 18, r: 14, b: 30, l: 46 };
  const DIA = 86400000;
  const cor = (n) => `var(--serie-${n || 1})`;
  const ms = (iso) => { const [a, m, d] = iso.split("-").map(Number); return Date.UTC(a, m - 1, d); };
  const iso = (t) => new Date(t).toISOString().slice(0, 10);

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
  function passoRedondo(bruto) {
    const base = Math.pow(10, Math.floor(Math.log10(Math.max(bruto, 1e-9))));
    return [1, 2, 2.5, 5, 10].map((m) => m * base).find((v) => v >= bruto);
  }

  // ---------------- dica ----------------
  const dica = document.createElement("div");
  dica.className = "dica-grafico";
  dica.hidden = true;
  document.body.appendChild(dica);
  function mostrar(x, y, titulo, linhas) {
    dica.textContent = "";
    const t = document.createElement("div"); t.className = "dica-titulo"; t.textContent = titulo; dica.appendChild(t);
    for (const l of linhas) {
      const d = document.createElement("div");
      d.className = "dica-linha";
      const k = document.createElement("span"); k.className = "dica-chave" + (l.proj ? " tracejada" : ""); k.style.background = cor(l.cor);
      const b = document.createElement("b"); b.textContent = l.valor;
      const s = document.createElement("span"); s.textContent = l.nome;
      d.append(k, b, s);
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

  // marcas de data: o passo em meses que cabe na largura (rótulo "YYYY" a partir de 1 ano)
  function marcasData(t0, t1, largura) {
    const caber = Math.max(2, Math.floor(largura / 80));
    const meses = (t1 - t0) / DIA / 30.44;
    const passo = [1, 2, 3, 6, 12, 24, 60, 120, 240].find((p) => meses / p <= caber) || 240;
    // primeira marca: o primeiro dia de mês (ou de ano, com passo de anos) depois de t0, múltiplo do passo
    const d = new Date(t0);
    let a = d.getUTCFullYear(), m = d.getUTCMonth() + (d.getUTCDate() > 1 ? 1 : 0);
    if (passo >= 12) {
      const k = passo / 12;
      if (m > 0) { a += Math.ceil(m / 12); m = 0; }
      a = Math.ceil(a / k) * k;
    } else m = Math.ceil(m / passo) * passo;          // Date.UTC aceita m >= 12 (vira o ano seguinte)
    const r = [];
    for (let t = Date.UTC(a, m, 1); t <= t1; ) {
      r.push({ t, rot: passo >= 12 ? String(new Date(t).getUTCFullYear()) : iso(t).slice(0, 7) });
      const n = new Date(t); n.setUTCMonth(n.getUTCMonth() + passo); t = n.getTime();
    }
    return r;
  }

  // valor de uma série numa data: degrau do real; na reta da projeção, interpolado
  function valorEm(s, t, comProjecao) {
    const p = s.pontos;
    if (!p.length || t < ms(p[0][0])) return null;
    const ultimo = ms(p[p.length - 1][0]);
    if (t <= ultimo || !comProjecao || !s.projecao) {
      if (t > ultimo && comProjecao) return null;
      let v = 0;
      for (const [d, n] of p) { if (ms(d) <= t) v = n; else break; }
      return { v, proj: false };
    }
    const [[d0, n0], [d1, n1]] = s.projecao, a = ms(d0), b = ms(d1);
    if (t > b) return null;
    return { v: Math.round(n0 + (n1 - n0) * (t - a) / ((b - a) || 1)), proj: true };
  }

  function desenhar(div, modo, W) {
    const H = div.clientHeight, comProjecao = modo === "projecao";
    const t0 = ms(G.inicio), t1 = ms(comProjecao ? G.fim_projecao : G.fim_real) + DIA;
    const seriesVisiveis = G.series.filter((s) => s.pontos.length);
    const maxReal = Math.max(1, ...seriesVisiveis.map((s) => s.pontos[s.pontos.length - 1][1]));
    const topoBruto = comProjecao ? G.meta : maxReal;
    const passoY = passoRedondo(topoBruto / 5), topo = Math.ceil(topoBruto / passoY) * passoY;
    const comRotulos = W > 560;
    const MR = comRotulos && !comProjecao ? 130 : M.r;
    const svg = el("svg", { width: W, height: H }, div);
    const x = (t) => M.l + (t - t0) / (t1 - t0) * (W - M.l - MR);
    const y = (v) => H - M.b - v / topo * (H - M.t - M.b);
    for (let v = 0; v <= topo + 1e-9; v += passoY) {
      el("line", { x1: M.l, x2: W - MR, y1: y(v), y2: y(v), class: v ? "grade" : "base" }, svg);
      texto(svg, M.l - 6, y(v) + 4, String(v), { class: "eixo", "text-anchor": "end" });
    }
    for (const m of marcasData(t0, t1, W - M.l - MR)) {
      texto(svg, x(m.t), H - M.b + 16, m.rot, { class: "eixo", "text-anchor": "middle" });
    }
    // hoje e a meta
    const th = ms(G.hoje);
    if (th >= t0 && th <= t1) {
      el("line", { x1: x(th), x2: x(th), y1: M.t - 6, y2: y(0), class: "limite hoje" }, svg);
      texto(svg, x(th) + 4, M.t + 2, T("today"), { class: "rotulo-limite" });
    }
    if (comProjecao) texto(svg, W - MR, y(G.meta) - 5, T("target {n}", { n: G.meta }), { class: "rotulo-limite", "text-anchor": "end" });

    const finais = [];
    seriesVisiveis.forEach((s) => {
      let d = "", vAnt = 0;
      s.pontos.forEach(([dt, n], i) => {
        const px = x(ms(dt)).toFixed(1);
        d += i ? `H${px}V${y(n).toFixed(1)}` : `M${px},${y(0).toFixed(1)}V${y(n).toFixed(1)}`;
        vAnt = n;
      });
      const ult = s.pontos[s.pontos.length - 1];
      if (!comProjecao) d += `H${x(Math.min(th, t1)).toFixed(1)}`;        // o total vale até hoje
      el("path", { d, class: "linha", style: `stroke:${cor(s.cor)}` }, svg);
      if (comProjecao && s.projecao) {
        const [[a, na], [b, nb]] = s.projecao;
        el("line", { x1: x(ms(a)), y1: y(na), x2: x(ms(b)), y2: y(nb), class: "linha tracejada", style: `stroke:${cor(s.cor)}` }, svg);
        el("circle", { cx: x(ms(b)), cy: y(nb), r: 4, class: "ponto", style: `fill:${cor(s.cor)}` }, svg);
      } else {
        const xf = comProjecao ? x(ms(ult[0])) : x(Math.min(th, t1));
        el("circle", { cx: xf, cy: y(vAnt), r: 4, class: "ponto", style: `fill:${cor(s.cor)}` }, svg);
        finais.push({ x: xf, y: y(vAnt), texto: `${s.nome} · ${vAnt}` });
      }
    });
    // nomes no fim das linhas (gráfico do real); se ficarem colados, só a legenda e a dica
    finais.sort((a, b) => a.y - b.y);
    if (comRotulos && !comProjecao && finais.every((f, i) => i === 0 || f.y - finais[i - 1].y >= 14)) {
      for (const f of finais) texto(svg, f.x + 8, f.y + 4, f.texto, { class: "rotulo-direto" });
    }

    // cruz: a data sob o mouse e o total de cada etapa nela
    const cruz = el("line", { y1: M.t, y2: H - M.b, class: "cruz", visibility: "hidden" }, svg);
    const pontos = seriesVisiveis.map((s) => el("circle", { r: 4, class: "ponto", visibility: "hidden", style: `fill:${cor(s.cor)}` }, svg));
    const alvo = el("rect", { x: M.l, y: M.t, width: W - M.l - MR, height: H - M.t - M.b, class: "alvo" }, svg);
    alvo.addEventListener("pointermove", (ev) => {
      const px = ev.clientX - svg.getBoundingClientRect().left;
      const t = Math.round((t0 + (px - M.l) / (W - M.l - MR) * (t1 - t0)) / DIA) * DIA;
      cruz.setAttribute("x1", x(t)); cruz.setAttribute("x2", x(t)); cruz.setAttribute("visibility", "visible");
      const linhas = [];
      seriesVisiveis.forEach((s, k) => {
        const r = valorEm(s, Math.min(t, comProjecao ? Infinity : th), comProjecao);
        pontos[k].setAttribute("visibility", r ? "visible" : "hidden");
        if (r) { pontos[k].setAttribute("cx", x(t)); pontos[k].setAttribute("cy", y(r.v)); }
        linhas.push({ cor: s.cor, proj: r && r.proj, nome: s.nome + (r && r.proj ? " (" + T("projected") + ")" : ""),
                      valor: r ? String(r.v) : "–" });
      });
      mostrar(ev.clientX + window.scrollX, ev.clientY + window.scrollY, iso(t), linhas);
    });
    alvo.addEventListener("pointerleave", () => {
      cruz.setAttribute("visibility", "hidden");
      pontos.forEach((p) => p.setAttribute("visibility", "hidden"));
      esconder();
    });
  }

  const larguras = new WeakMap();
  function redesenhar(div) {
    const W = Math.floor(div.clientWidth);
    if (!W || larguras.get(div) === W) return;
    larguras.set(div, W);
    div.textContent = "";
    desenhar(div, div.dataset.g, W);
  }
  const obs = new ResizeObserver((itens) => itens.forEach((i) => redesenhar(i.target)));
  document.querySelectorAll(".grafico[data-g]").forEach((d) => { redesenhar(d); obs.observe(d); });
})();
