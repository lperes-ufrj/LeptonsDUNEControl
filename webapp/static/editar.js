// Formulário da tarefa: abas, cálculos ao vivo (mesmas regras do servidor), aviso de alterações não gravadas
// e a janela de escolha de lote (lote OPTO + lote interno, ou lote de limpeza do Leptons).
(function () {
  "use strict";

  const form = document.getElementById("form-tarefa");
  const $ = (sel, raiz) => (raiz || document).querySelector(sel);
  const $$ = (sel, raiz) => Array.from((raiz || document).querySelectorAll(sel));
  const LIMITE_PERDA_PCT = 5.0, LIMITE_EF = 0.75, MIN_AMOSTRAS_EF = 2, AREA_FILTRO_CM2 = 77.0, N_FILTROS = 28;
  const TXT = { approved: "Approved", rejected: "Rejected", partial: T("In progress"), empty: T("Not filled") };

  function numero(v) {
    const t = String(v == null ? "" : v).trim().replace(",", ".");
    if (!t) return null;
    const x = Number(t);
    return Number.isFinite(x) ? x : null;
  }
  const campo = (nome) => form.elements[nome];
  const valor = (nome) => {
    const c = campo(nome);
    if (!c) return "";
    if (c instanceof RadioNodeList) return c.value || "";
    if (c.type === "checkbox") return c.checked ? c.value : "";
    return c.value.trim();
  };
  const hoje = () => {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  };
  function pill(el, estado, texto) {
    el.className = "pill es-" + estado;
    el.textContent = texto;
  }

  // ---------------- abas ----------------
  const abas = $$("nav.abas:not(.pequenas) a");
  function mostrarAba(id) {
    if (!document.getElementById(id)) id = "deposicao";
    abas.forEach((a) => a.classList.toggle("ativo", a.getAttribute("href") === "#" + id));
    $$("section.aba").forEach((s) => (s.hidden = s.id !== id));
  }
  abas.forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    const id = a.getAttribute("href").slice(1);
    history.replaceState(null, "", "#" + id);
    mostrarAba(id);
  }));
  mostrarAba(location.hash.slice(1));

  // ---------------- alterações não gravadas ----------------
  let alterado = false, enviando = false;
  function marcarAlterado() {
    if (alterado) return;
    alterado = true;
    const el = $("#estado-form");
    el.textContent = T("Unsaved changes");
    el.className = "nao";
  }
  form.addEventListener("input", marcarAlterado);
  form.addEventListener("change", marcarAlterado);
  window.addEventListener("beforeunload", (e) => {
    if (alterado && !enviando) { e.preventDefault(); e.returnValue = ""; }
  });
  $$("[data-sair]").forEach((a) => a.addEventListener("click", (e) => {
    if (alterado && !confirm(T("Leave without saving? The changes will be lost."))) e.preventDefault();
    else enviando = true;
  }));
  form.addEventListener("submit", (e) => {
    const revisada = form.dataset.revisada;
    if (revisada && !confirm(T("This sample was signed off (Final QA) by {por}.\n\nSaving changes removes the sign-off: the sample " +
                               "goes back to 'To be reviewed' and needs a new Final QA sign-off. Continue?", { por: revisada }))) {
      e.preventDefault();
      return;
    }
    if (revisada) campo("confirmar_revisao").value = "1";
    enviando = true;
  });

  // botão Today ao lado das datas
  $$("[data-hoje]").forEach((b) => b.addEventListener("click", () => {
    const ent = b.previousElementSibling;
    ent.value = hoje();
    ent.dispatchEvent(new Event("input", { bubbles: true }));
  }));

  // clicar de novo numa opção marcada desmarca (como deixar a célula em branco)
  form.addEventListener("pointerdown", (e) => {
    const r = e.target.closest(".seg label");
    if (r) r.querySelector("input").dataset.estava = r.querySelector("input").checked ? "1" : "";
  });
  form.addEventListener("click", (e) => {
    const inp = e.target.closest(".seg input[type=radio]");
    if (inp && inp.dataset.estava === "1") {
      inp.checked = false;
      inp.dataset.estava = "";
      form.dispatchEvent(new Event("change"));
      recalcular();
    }
  });

  // ---------------- massas por posição ----------------
  function recalcularMassas() {
    $$("tr[data-massa]").forEach((tr) => {
      const [a, d] = $$("input", tr).map((i) => numero(i.value));
      const dens = a != null && d != null ? ((d - a) * 1e6) / AREA_FILTRO_CM2 : null;
      $("[data-dens]", tr).textContent = dens == null ? "–" : dens.toFixed(2);
    });
  }

  // ---------------- inspeção visual ----------------
  const OBRIGATORIOS = ["visual", "uniformity", "stains", "particles", "edge", "finger", "other", "classification"];
  function recalcularVisual() {
    let completos = 0, algum = false;
    const cont = { A: 0, B: 0, C: 0 };
    for (let n = 1; n <= N_FILTROS; n++) {
      const valores = OBRIGATORIOS.map((c) => valor("f" + n + "_" + c));
      if (valores.every(Boolean)) completos++;
      if (valores.some(Boolean) || valor("f" + n + "_comments")) algum = true;
      const cl = valor("f" + n + "_classification");
      if (cl in cont) cont[cl]++;
    }
    $("#resumo-visual-texto").textContent = algum
      ? T("{n}/{total} filters complete", { n: completos, total: N_FILTROS }) + "  ·  A: " + cont.A + "   B: " + cont.B + "   C: " + cont.C
      : T("Not filled");
    pill($("#resumo-visual"), completos === N_FILTROS ? "approved" : algum ? "partial" : "empty", completos + "/" + N_FILTROS);
  }
  function limparLinha(tr) {
    $$("input", tr).forEach((i) => { if (i.type === "radio") i.checked = false; else i.value = ""; });
  }
  $$("[data-limpar-linha]").forEach((b) => b.addEventListener("click", () => {
    limparLinha(b.closest("tr"));
    marcarAlterado();
    recalcular();
  }));
  $("#limpar-tabela").addEventListener("click", () => {
    if (!confirm(T("Clear all {n} rows of the inspection table?", { n: N_FILTROS }))) return;
    $$("tr[data-filtro]").forEach(limparLinha);
    marcarAlterado();
    recalcular();
  });

  // ---------------- imersão criogênica ----------------
  function amostraImersao(a, d) {
    if (a == null || d == null || a <= 0) return null;
    const dif = d - a, pct = (dif / a) * 100;
    return { dif, pct, ok: Math.round(pct * 1e6) / 1e6 >= -LIMITE_PERDA_PCT };
  }
  function recalcularImersao() {
    const valores = [];
    let algum = !!valor("im_obs");
    $$("tr[data-imersao]").forEach((tr) => {
      const [ea, ed] = $$("input", tr);
      if (ea.value.trim() || ed.value.trim()) algum = true;
      const r = amostraImersao(numero(ea.value), numero(ed.value));
      $("[data-dif]", tr).textContent = r ? (r.dif >= 0 ? "+" : "") + r.dif.toFixed(5) + " g (" + (r.pct >= 0 ? "+" : "") + r.pct.toFixed(2) + " %)" : "–";
      const c = $("[data-cond]", tr);
      c.textContent = r ? (r.ok ? "Approved" : "Rejected") : "–";
      c.className = "calc " + (r ? (r.ok ? "sim" : "nao") : "");
      valores.push(r ? (r.ok ? "Yes" : "No") : "");
    });
    const itens = Array.from(new Set($$("input[name^=im_item_]").map((i) => i.name))).map(valor);
    valores.push(...itens);
    const preenchidos = valores.filter(Boolean).length;
    algum = algum || preenchidos > 0;
    const estado = valores.includes("No") ? "rejected" : valores.every((v) => v === "Yes") ? "approved" : algum ? "partial" : "empty";
    const rev = valor("im_revisado") ? T("reviewed") : T("pending supervisor review");
    const textos = {
      approved: T("Overall result: APPROVED ({rev})", { rev }), rejected: T("Overall result: REJECTED ({rev})", { rev }),
      partial: T("Overall result: in progress ({n}/{total} filled)", { n: preenchidos, total: valores.length }),
      empty: T("Overall result: not evaluated"),
    };
    const res = $("#resultado-crio");
    res.textContent = textos[estado];
    res.className = "resultado es-" + estado;
    pill($("#resumo-crio"), estado, TXT[estado]);
  }

  // ---------------- eficiência óptica ----------------
  function recalcularEficiencia() {
    let testadas = 0, medidas = 0, reprovado = false;
    let algum = ["ef_data_teste", "ef_ref_id", "ef_ref_data", "ef_temp", "ef_umid", "ef_operador", "ef_supervisor",
                 "ef_data_revisao", "ef_revisado", "ef_obs"].some((n) => valor(n));
    $$("tr[data-eficiencia]").forEach((tr) => {
      const a = $("b", tr).textContent;
      const ent = (c) => campo("efa_" + a + "_" + c);
      let testada = valor("efa_" + a + "_testada");
      if (!testada && ent("x").value.trim()) {      // eficiência digitada sem responder "Tested?": amostra testada
        $$("input[name=efa_" + a + "_testada]").find((i) => i.value === "Yes").checked = true;
        testada = "Yes";
      }
      // amostra não testada: campos bloqueados (readOnly, não disabled: os valores continuam sendo gravados)
      ["antes", "depois", "area", "x"].forEach((c) => (ent(c).readOnly = testada === "No"));
      const [va, vd, area, x] = ["antes", "depois", "area", "x"].map((c) => numero(ent(c).value));
      if (testada || ["antes", "depois", "area", "x"].some((c) => ent(c).value.trim())) algum = true;
      const dif = va != null && vd != null ? vd - va : null;
      const dens = dif != null && area && area > 0 ? (dif * 1e6) / area : null;
      $("[data-dif]", tr).textContent = dif == null ? "–" : dif.toFixed(5);
      $("[data-dens]", tr).textContent = dens == null ? "–" : dens.toFixed(2);
      const c = $("[data-cond]", tr);
      if (testada === "No") { c.textContent = T("Not tested"); c.className = "calc suave"; }
      else if (x == null) { c.textContent = "–"; c.className = "calc"; }
      else {
        const ok = Math.round(x * 1e6) / 1e6 >= LIMITE_EF;
        c.textContent = ok ? "Approved" : "Rejected";
        c.className = "calc " + (ok ? "sim" : "nao");
      }
      if (testada !== "Yes") return;
      testadas++;
      if (x == null) return;
      medidas++;
      if (Math.round(x * 1e6) / 1e6 < LIMITE_EF) reprovado = true;
    });
    const necessarias = Math.max(MIN_AMOSTRAS_EF, testadas);
    const estado = reprovado ? "rejected" : medidas >= MIN_AMOSTRAS_EF && medidas === testadas ? "approved" : algum ? "partial" : "empty";
    const rev = valor("ef_revisado") ? T("reviewed") : T("pending supervisor review");
    const textos = {
      approved: T("Overall result: APPROVED ({rev})", { rev }), rejected: T("Overall result: REJECTED ({rev})", { rev }),
      partial: T("Overall result: in progress ({n}/{total} samples measured)", { n: medidas, total: necessarias }),
      empty: T("Overall result: not evaluated"),
    };
    const res = $("#resultado-ef");
    res.textContent = textos[estado];
    res.className = "resultado es-" + estado;
    pill($("#resumo-ef"), estado, TXT[estado]);

    // tempo de uso do substrato de referência (máx. 6 meses)
    const aviso = $("#idade-referencia");
    const lerData = (t) => {
      t = (t || "").trim();
      let m = t.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (m) return new Date(+m[1], m[2] - 1, +m[3]);
      m = t.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      return m ? new Date(+m[3], m[2] - 1, +m[1]) : null;
    };
    const inst = lerData(valor("ef_ref_data"));
    if (!inst) { aviso.textContent = ""; return; }
    const teste = lerData(valor("ef_data_teste")) || new Date();
    const dias = Math.floor((teste - inst) / 86400000);
    const limite = +aviso.dataset.limite;
    if (dias < 0) { aviso.textContent = "⚠ " + T("installation date is after the test date"); aviso.className = "aviso-referencia nao"; }
    else if (dias > limite) { aviso.textContent = "⚠ " + T("reference in use for {n} days (limit: 6 months)", { n: dias }); aviso.className = "aviso-referencia nao"; }
    else { aviso.textContent = T("Reference in use for {n} days (limit: 6 months)", { n: dias }); aviso.className = "aviso-referencia sim"; }
  }

  function recalcular() {
    recalcularMassas();
    recalcularVisual();
    recalcularImersao();
    recalcularEficiencia();
  }
  form.addEventListener("input", recalcular);
  form.addEventListener("change", recalcular);

  // ---------------- anexos ----------------
  $$("[data-remover-anexo]").forEach((b) => b.addEventListener("click", () => {
    if (!confirm(T("Remove this file from the sample? (The file itself is not deleted.)"))) return;
    b.closest("li").remove();
    marcarAlterado();
  }));

  // ---------------- lotes escolhidos ----------------
  const entradaLotes = $("#lotes_json");
  let escolhidos = JSON.parse(entradaLotes.value || "[]");
  const chave = (l) => [l.tipo, l.lote_id, l.codigo_lote, l.interno_id].join("|");
  const esc = (t) => String(t == null || t === "" ? "–" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function desenharEscolhidos() {
    entradaLotes.value = JSON.stringify(escolhidos);
    const corpo = $("#lotes-sel");
    corpo.innerHTML = escolhidos.length ? "" : '<tr><td colspan="6" class="vazio-tabela">' + T("No batch selected – add at least one.") + "</td></tr>";
    escolhidos.forEach((l, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td class='mono'>" + esc(l.codigo_lote) + "</td><td class='mono'>" + esc(l.codigo_interno) + "</td><td>" +
        esc(l.chegada) + "</td><td>" + esc(l.empresa) + "</td><td class='num mono'>" + esc(l.filtros) +
        "</td><td><button type='button' class='x' title='" + T("Remove from this deposition") + "'>✕</button></td>";
      $("button", tr).addEventListener("click", () => {
        escolhidos.splice(i, 1);
        marcarAlterado();
        desenharEscolhidos();
      });
      corpo.appendChild(tr);
    });
    const filtros = escolhidos.map((l) => l.filtros).filter((x) => x != null);
    const codigos = escolhidos.map((l) => l.codigo_interno).filter(Boolean);
    const txtInterno = codigos.length
      ? (codigos.length === 1 ? T("Internal lot used: ") : T("Internal lots used: ")) + codigos.slice(0, 4).join(", ") +
        (codigos.length > 4 ? " (+" + (codigos.length - 4) + ")" : "")
      : T("No internal lot selected");
    $("#info-lotes").textContent = escolhidos.length
      ? T("{n} selected", { n: escolhidos.length }) + "   ·   " + txtInterno + "   ·   " + T("Total filters: ") +
        (filtros.length ? filtros.reduce((a, b) => a + b, 0) : "–")
      : T("No batch selected");
    atualizarOrigem();
  }

  // ---------------- origem de cada filtro (mais de uma caixa / lote) ----------------
  const entradaOrigens = $("#origens_json");
  const grade = $("#og-grade");
  const dlgOrigem = $("#dlg-origem");
  let origens = JSON.parse(entradaOrigens.value || "{}");      // {nº do filtro: chave do lote}
  let rascunho = {};

  const rotulo = (l) => l.codigo_interno ? l.codigo_interno + " (" + (l.codigo_lote || "–") + ")" : (l.codigo_lote || "–") + " (" + T("whole batch") + ")";
  const curto = (l) => l.codigo_interno || l.codigo_lote || "–";
  // na grade os códigos não cabem: cada lote ganha uma letra (a mesma da legenda e da cor)
  const letra = (i) => String.fromCharCode(65 + i);
  const minimo = (l) => letra(escolhidos.indexOf(l)) + " · " + (l.codigo_interno ? l.codigo_interno.replace(/^DUNE-/, "") : "batch");
  function faixas(ns) {
    ns = [...ns].sort((a, b) => a - b);
    const partes = [];
    for (let i = 0; i < ns.length; i++) {
      let j = i;
      while (j + 1 < ns.length && ns[j + 1] === ns[j] + 1) j++;
      partes.push(i === j ? String(ns[i]) : ns[i] + "–" + ns[j]);
      i = j;
    }
    return partes.join(", ");
  }
  function porLote(mapa) {
    const grupos = escolhidos.map(() => []);
    const idx = new Map(escolhidos.map((l, i) => [chave(l), i]));
    Object.entries(mapa).forEach(([n, k]) => { if (idx.has(k)) grupos[idx.get(k)].push(+n); });
    return grupos;
  }

  function atualizarOrigem() {
    const varios = escolhidos.length > 1;
    const validas = new Set(escolhidos.map(chave));
    Object.keys(origens).forEach((n) => { if (!varios || !validas.has(origens[n])) delete origens[n]; });
    entradaOrigens.value = JSON.stringify(origens);
    $("#abrir-origem").hidden = !varios;
    const info = $("#info-origem");
    info.hidden = !varios;
    atualizarReuso();
    if (!varios) return;
    const feitos = Object.keys(origens).length;
    const grupos = porLote(origens);
    info.className = "info-origem " + (feitos === N_FILTROS ? "sim" : "nao");
    info.textContent = T("Filter origin: ") + (feitos ? T("{n}/{total} assigned", { n: feitos, total: N_FILTROS }) + "   ·   " +
      escolhidos.map((l, i) => grupos[i].length ? curto(l) + ": " + faixas(grupos[i]) : "").filter(Boolean).join("   ·   ")
      : T("not assigned yet – click Filter origin…"));
  }

  function desenharOrigem() {
    const grupos = porLote(rascunho);
    $("#og-legenda").innerHTML = escolhidos.map((l, i) => {
      const caixa = l.filtros != null ? " " + T("of {n} in the box", { n: l.filtros }) : "";
      const demais = l.filtros != null && grupos[i].length > l.filtros;
      return "<span class='chip-origem cor-" + (i % 6) + "'><b class='letra'>" + letra(i) + "</b> <b>" + esc(rotulo(l)) + "</b> · " +
        T("{n} filter(s)", { n: grupos[i].length }) + caixa + (demais ? " <span class='nao'>– " + T("more than the box had") + "</span>" : "") + "</span>";
    }).join("");
    const opcoes = "<option value=''>–</option>" + escolhidos.map((l, i) => "<option value='" + i + "'>" + esc(minimo(l)) + "</option>").join("");
    const sel = $("#og-lote"), antes = sel.value;
    sel.innerHTML = escolhidos.map((l, i) => "<option value='" + i + "'>" + letra(i) + " · " + esc(rotulo(l)) + "</option>").join("");
    if (antes && +antes < escolhidos.length) sel.value = antes;
    grade.innerHTML = "";
    const idx = new Map(escolhidos.map((l, i) => [chave(l), i]));
    for (let n = 1; n <= N_FILTROS; n++) {
      const i = idx.has(rascunho[n]) ? idx.get(rascunho[n]) : -1;
      const cel = document.createElement("label");
      cel.className = "celula-origem" + (i >= 0 ? " cor-" + (i % 6) : " vazia");
      cel.innerHTML = "<span class='mono'>" + String(n).padStart(2, "0") + "</span><select>" + opcoes + "</select>";
      const s = $("select", cel);
      s.value = i >= 0 ? String(i) : "";
      s.addEventListener("change", () => {
        if (s.value === "") delete rascunho[n];
        else rascunho[n] = chave(escolhidos[+s.value]);
        desenharOrigem();
      });
      grade.appendChild(cel);
    }
    const feitos = Object.keys(rascunho).length;
    $("#og-estado").textContent = T("{n}/{total} filters assigned", { n: feitos, total: N_FILTROS });
    $("#og-estado").className = feitos === N_FILTROS ? "sim" : "nao";
  }

  $("#abrir-origem").addEventListener("click", () => {
    rascunho = { ...origens };
    $("#og-de").value = 1;
    $("#og-ate").value = N_FILTROS;
    desenharOrigem();
    dlgOrigem.showModal();
  });
  $("#og-aplicar").addEventListener("click", () => {
    let de = parseInt($("#og-de").value, 10), ate = parseInt($("#og-ate").value, 10);
    if (!(de >= 1 && ate >= 1)) { alert(T("Enter the first and the last filter (1 to {n}).", { n: N_FILTROS })); return; }
    if (de > ate) [de, ate] = [ate, de];
    const l = escolhidos[+$("#og-lote").value];
    for (let n = Math.max(1, de); n <= Math.min(N_FILTROS, ate); n++) rascunho[n] = chave(l);
    // a próxima faixa começa logo depois desta, já no lote seguinte
    if (ate < N_FILTROS) {
      $("#og-de").value = ate + 1;
      $("#og-ate").value = N_FILTROS;
      $("#og-lote").value = String(Math.min(+$("#og-lote").value + 1, escolhidos.length - 1));
    }
    desenharOrigem();
  });
  $("#og-limpar").addEventListener("click", () => { rascunho = {}; desenharOrigem(); });
  $("#og-ok").addEventListener("click", () => {
    if (JSON.stringify(rascunho) !== JSON.stringify(origens)) marcarAlterado();
    origens = rascunho;
    atualizarOrigem();
    dlgOrigem.close();
  });
  $$("[data-fechar]", dlgOrigem).forEach((b) => b.addEventListener("click", () => dlgOrigem.close()));

  // ---------------- filtros limpos (de um lote de limpeza) em cada posição ----------------
  const entradaReuso = $("#reuso_json");
  const dlgReuso = $("#dlg-reuso");
  let reuso = JSON.parse(entradaReuso.value || "{}");          // {nº do filtro: id do filtro retirado}
  const pecas = JSON.parse($("#pecas_json").value || "{}");    // {id do lote de limpeza: [{id, rotulo, classe}]}
  let rascunhoReuso = {};

  const pecasDe = (l) => (l.tipo === "limpeza" && pecas[l.interno_id]) || [];
  // posições que vêm do lote l: todas, se ele é o único; senão as da janela Filter origin
  function posicoesDe(l) {
    if (escolhidos.length === 1) return escolhidos[0] === l ? Array.from({ length: N_FILTROS }, (_, i) => i + 1) : [];
    return Object.entries(origens).filter(([, k]) => k === chave(l)).map(([n]) => +n).sort((a, b) => a - b);
  }
  const lotesComPecas = () => escolhidos.filter((l) => pecasDe(l).length);
  // o que vale: posição de um lote de limpeza + filtro limpo desse lote, sem repetir
  function podar(mapa) {
    const saida = {}, vistos = new Set();
    for (const l of lotesComPecas()) {
      const ids = new Set(pecasDe(l).map((p) => p.id));
      for (const n of posicoesDe(l)) {
        const id = mapa[n];
        if (id != null && ids.has(+id) && !vistos.has(+id)) { saida[n] = +id; vistos.add(+id); }
      }
    }
    return saida;
  }
  function atualizarReuso() {
    reuso = podar(reuso);
    entradaReuso.value = JSON.stringify(reuso);
    const grupos = lotesComPecas();
    $("#abrir-reuso").hidden = !grupos.length;
    const info = $("#info-reuso");
    info.hidden = !grupos.length;
    if (!grupos.length) return;
    const total = grupos.reduce((s, l) => s + posicoesDe(l).length, 0), feitos = Object.keys(reuso).length;
    info.className = "info-origem " + (total && feitos === total ? "sim" : "nao");
    info.textContent = T("Cleaned filters: ") + (total
      ? T("{n}/{total} slots with a cleaned filter chosen", { n: feitos, total }) + (feitos < total ? " – " + T("click Cleaned filters…") : "")
      : T("assign the slots of the cleaning lot in Filter origin… first"));
  }
  function desenharReuso() {
    const caixa = $("#ru-grupos");
    caixa.innerHTML = "";
    const usados = new Set(Object.values(rascunhoReuso).map(Number));
    let total = 0;
    for (const l of lotesComPecas()) {
      const ps = pecasDe(l), ns = posicoesDe(l);
      total += ns.length;
      const bloco = document.createElement("div");
      bloco.className = "grupo-reuso";
      bloco.innerHTML = "<div class='sub-titulo'><b class='mono'>" + esc(l.codigo_interno) + "</b> · " +
        T("{n} slot(s)", { n: ns.length }) + " · " + T("{n} cleaned filter(s) available", { n: ps.length }) +
        (ns.length > ps.length ? " <span class='nao'>– " + T("not enough for all slots") + "</span>" : "") + "</div>";
      const grade = document.createElement("div");
      grade.className = "grade-reuso";
      if (!ns.length) grade.innerHTML = "<span class='nao pequeno'>" + T("No slot comes from this lot – assign them in Filter origin….") + "</span>";
      for (const n of ns) {
        const cel = document.createElement("label");
        cel.className = "celula-reuso" + (rascunhoReuso[n] != null ? " cheia" : "");
        const sel = document.createElement("select");
        sel.appendChild(new Option("–", ""));
        for (const p of ps) {
          const o = new Option(p.rotulo + (p.classe ? " (" + p.classe + ")" : ""), p.id);
          o.disabled = usados.has(p.id) && +rascunhoReuso[n] !== p.id;
          sel.appendChild(o);
        }
        sel.value = rascunhoReuso[n] != null ? String(rascunhoReuso[n]) : "";
        sel.addEventListener("change", () => {
          if (sel.value === "") delete rascunhoReuso[n]; else rascunhoReuso[n] = +sel.value;
          desenharReuso();
        });
        const num = document.createElement("span");
        num.className = "mono";
        num.textContent = String(n).padStart(2, "0");
        cel.append(num, sel);
        grade.appendChild(cel);
      }
      bloco.appendChild(grade);
      caixa.appendChild(bloco);
    }
    const feitos = Object.keys(rascunhoReuso).length;
    $("#ru-estado").textContent = T("{n}/{total} slots with a cleaned filter chosen", { n: feitos, total });
    $("#ru-estado").className = total && feitos === total ? "sim" : "nao";
  }
  $("#abrir-reuso").addEventListener("click", () => {
    rascunhoReuso = podar(reuso);
    desenharReuso();
    dlgReuso.showModal();
  });
  $("#ru-ordem").addEventListener("click", () => {
    for (const l of lotesComPecas()) {
      const livres = pecasDe(l).map((p) => p.id).filter((id) => !Object.values(rascunhoReuso).map(Number).includes(id));
      for (const n of posicoesDe(l)) if (rascunhoReuso[n] == null && livres.length) rascunhoReuso[n] = livres.shift();
    }
    desenharReuso();
  });
  $("#ru-limpar").addEventListener("click", () => { rascunhoReuso = {}; desenharReuso(); });
  $("#ru-ok").addEventListener("click", () => {
    const novo = podar(rascunhoReuso);
    if (JSON.stringify(novo) !== JSON.stringify(reuso)) marcarAlterado();
    reuso = novo;
    atualizarReuso();
    dlgReuso.close();
  });
  $$("[data-fechar]", dlgReuso).forEach((b) => b.addEventListener("click", () => dlgReuso.close()));

  // ---------------- janela: escolher lote ----------------
  const dlg = $("#seletor-lotes");
  let catalogo = null, loteAtual = null;

  function status(usado, jaEscolhido, tipo) {
    if (jaEscolhido) return "<span class='sim'>" + T("Selected in this deposition") + "</span>";
    return usado.length ? "<span class='nao'>" + T("Used in PID {pid}", { pid: esc(usado.join(", ")) }) + "</span>" : T("Available");
  }
  function desenharLotes() {
    const corpo = $("#sl-lotes");
    corpo.innerHTML = catalogo.opto.length ? "" : '<tr><td colspan="7" class="vazio-tabela">' + T("No OPTO batches registered in lotes.db.") + "</td></tr>";
    catalogo.opto.forEach((l, i) => {
      const tr = document.createElement("tr");
      tr.className = loteAtual === i ? "selecionada" : "";
      tr.innerHTML = "<td class='mono'><b>" + esc(l.lote) + "</b></td><td>" + esc(l.chegada) + "</td><td>" + esc(l.empresa) +
        "</td><td class='mono'>" + esc(l.tracking) + "</td><td class='num'>" + esc(l.filtros) + "</td><td class='num'>" +
        esc(l.caixas) + "</td><td>" + esc(l.inspecao) + "</td>";
      tr.addEventListener("click", () => { loteAtual = i; desenharLotes(); });
      corpo.appendChild(tr);
    });
    const ci = $("#sl-internos");
    if (loteAtual == null) { ci.innerHTML = '<tr><td colspan="6" class="vazio-tabela">Select a batch above.</td></tr>'; return; }
    const lote = catalogo.opto[loteAtual];
    const usados = new Set(escolhidos.map(chave));
    if (!lote.internos.length) {
      ci.innerHTML = '<tr><td colspan="6" class="vazio-tabela nao">' + T("No internal lots are registered for this batch. Register them in " +
        "the Batches tab (Edit batch), or click Add selected to add the batch without an internal lot.") + "</td></tr>";
      return;
    }
    ci.innerHTML = "";
    lote.internos.forEach((it, j) => {
      const tr = document.createElement("tr");
      const ja = usados.has(chave(it.entrada));
      tr.innerHTML = "<td><input type='checkbox' data-j='" + j + "'" + (ja ? " disabled" : "") + "></td><td class='mono'>" +
        (it.caixa == null ? "–" : String(it.caixa).padStart(2, "0")) + "</td><td class='mono'><b>" + esc(it.codigo) +
        "</b></td><td class='num'>" + esc(it.filtros) + "</td><td>" + esc(it.obs || "") + "</td><td>" + status(it.usado, ja) + "</td>";
      tr.addEventListener("dblclick", () => { $("input", tr).checked = true; adicionar(); });
      ci.appendChild(tr);
    });
  }
  function desenharLimpezas() {
    const corpo = $("#sl-limpezas");
    const usados = new Set(escolhidos.map(chave));
    corpo.innerHTML = catalogo.limpeza.length ? "" : '<tr><td colspan="9" class="vazio-tabela nao">' + T("No Leptons cleaning lots are " +
      "registered. Register them in the Cleaning lots tab.") + "</td></tr>";
    catalogo.limpeza.forEach((l, j) => {
      const ja = usados.has(chave(l.entrada));
      const tr = document.createElement("tr");
      tr.innerHTML = "<td><input type='checkbox' data-j='" + j + "'" + (ja ? " disabled" : "") + "></td><td class='mono'><b>" +
        esc(l.codigo) + "</b></td><td>" + esc(l.data) + "</td><td>" + esc(l.responsavel) + "</td><td class='num'>" + esc(l.filtros) +
        (l.disp != null ? "<br><small class='" + (l.disp ? "sim" : "nao") + "'>" + T("{n} available", { n: l.disp }) + "</small>" : "") +
        "</td><td>" + esc(l.origem) + "</td><td>" + esc(l.ptp) + "</td><td>" + esc(l.resultado) + "</td><td>" + status(l.usado, ja) + "</td>";
      tr.addEventListener("dblclick", () => { $("input", tr).checked = true; adicionar(); });
      corpo.appendChild(tr);
    });
  }
  function adicionar() {
    const naOpto = !$("#sl-opto").hidden;
    const aviso = $("#sl-aviso");
    aviso.textContent = "";
    const novos = [];
    if (naOpto) {
      if (loteAtual == null) { aviso.textContent = T("Select a batch first."); return; }
      const lote = catalogo.opto[loteAtual];
      if (!lote.internos.length) novos.push(lote.entrada);
      else {
        const marcados = $$("#sl-internos input:checked").map((i) => lote.internos[+i.dataset.j]);
        if (!marcados.length) { aviso.textContent = T("Select at least one internal lot."); return; }
        marcados.forEach((it) => {
          if (it.usado.length && !confirm(T("Internal lot {codigo} was already used (PID {pid}).\n\nUse it again in this deposition?",
                                            { codigo: it.codigo, pid: it.usado.join(", ") }))) return;
          novos.push(it.entrada);
        });
      }
    } else {
      const marcados = $$("#sl-limpezas input:checked").map((i) => catalogo.limpeza[+i.dataset.j]);
      if (!marcados.length) { aviso.textContent = T("Select at least one cleaning lot."); return; }
      marcados.forEach((l) => {
        const res = (l.resultado || "").trim();
        if (res && res.toLowerCase() !== "approved" &&
            !confirm(T("Cleaning lot {codigo} has result '{res}'.\n\nUse it in this deposition anyway?", { codigo: l.codigo, res }))) return;
        if (l.disp == null && l.usado.length && !confirm(T("Cleaning lot {codigo} was already used (PID {pid}).\n\nUse it again in this deposition?",
                                                           { codigo: l.codigo, pid: l.usado.join(", ") }))) return;
        if (l.disp === 0 && !confirm(T("Cleaning lot {codigo} has no cleaned filter left (all were used).\n\nUse it in this deposition anyway?",
                                       { codigo: l.codigo }))) return;
        pecas[l.id] = l.pecas || [];
        novos.push(l.entrada);
      });
    }
    const existentes = new Set(escolhidos.map(chave));
    novos.forEach((e) => { if (!existentes.has(chave(e))) { escolhidos.push(e); existentes.add(chave(e)); } });
    if (novos.length) marcarAlterado();
    desenharEscolhidos();
    desenharLotes();
    desenharLimpezas();
  }
  $$("nav.abas.pequenas a").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    $$("nav.abas.pequenas a").forEach((x) => x.classList.toggle("ativo", x === a));
    $$(".sl-aba").forEach((s) => (s.hidden = "#" + s.id !== a.getAttribute("href")));
  }));
  $("#abrir-seletor").addEventListener("click", async () => {
    $("#sl-aviso").textContent = T("Loading batches…");
    dlg.showModal();
    try {
      catalogo = await (await fetch(form.dataset.apiLotes)).json();
    } catch (err) {
      $("#sl-aviso").textContent = T("Could not read the batch database: ") + err;
      return;
    }
    $("#sl-aviso").textContent = "";
    // já abre no lote da última entrada escolhida
    const ultimo = escolhidos[escolhidos.length - 1];
    loteAtual = null;
    if (ultimo && ultimo.tipo === "limpeza") $$("nav.abas.pequenas a")[1].click();
    else if (ultimo) {
      const i = catalogo.opto.findIndex((l) => l.id === ultimo.lote_id || l.lote === ultimo.codigo_lote);
      if (i >= 0) loteAtual = i;
    }
    if (loteAtual == null && catalogo.opto.length === 1) loteAtual = 0;
    desenharLotes();
    desenharLimpezas();
  });
  $("#sl-adicionar").addEventListener("click", adicionar);
  $$("[data-fechar]", dlg).forEach((b) => b.addEventListener("click", () => dlg.close()));

  desenharEscolhidos();
  recalcular();
})();
