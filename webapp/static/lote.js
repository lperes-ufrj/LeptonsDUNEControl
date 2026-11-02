// Formulário do lote OPTO: uma linha por caixa menor, total de filtros calculado e aviso de alterações não gravadas.
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const form = $("#form-lote");
  const el = form.elements;
  const corpo = $("#caixas tbody");
  const PREFIXO = form.dataset.prefixo;
  const DIGITOS = +form.dataset.digitos || 4;

  const inteiro = (v) => (/^\d+$/.test(String(v).trim()) && +v > 0 ? +v : null);
  const linhas = () => $$("tr", corpo).filter((tr) => !tr.hidden);
  const campo = (tr, tipo) => tr.querySelector(`input[name^="cx_${tipo}_"]`);

  function novaLinha(i) {
    const tr = document.createElement("tr");
    const n = String(i).padStart(2, "0");
    tr.innerHTML = `<td class="mono"><b>${n}</b></td><td class="mono suave" data-opto></td>
      <td><span class="codigo-caixa"><span class="mono"></span><input name="cx_num_${i}" class="mono" inputmode="numeric"><input type="hidden" name="cx_orig_${i}"></span></td>
      <td><input name="cx_filtros_${i}" class="num" inputmode="numeric"></td>
      <td><input name="cx_obs_${i}" class="obs-caixa"></td>`;
    tr.querySelector(".codigo-caixa .mono").textContent = PREFIXO;
    return tr;
  }

  // (capacidade, nº de caixas) do último cálculo: se mudar, os filtros de cada caixa voltam à capacidade
  let ultimo = [inteiro(el.capacidade_caixa_menor.value), inteiro(el.numero_caixas_menores.value)].join("x");

  function calcular(refazer) {
    const cap = inteiro(el.capacidade_caixa_menor.value);
    const n = inteiro(el.numero_caixas_menores.value) || 0;
    const todas = $$("tr", corpo);
    for (let i = todas.length + 1; i <= n; i++) corpo.appendChild(novaLinha(i));
    $$("tr", corpo).forEach((tr, k) => (tr.hidden = k >= n));     // as de fora ficam guardadas, mas não são gravadas
    $("#sem-caixas").hidden = n > 0 && cap != null;
    $("#caixas").hidden = !(n > 0 && cap != null);

    const chave = [cap, n].join("x");
    if (refazer || chave !== ultimo) {
      linhas().forEach((tr) => (campo(tr, "filtros").value = cap ?? ""));
      ultimo = chave;
    }
    linhas().forEach((tr) => {
      const f = campo(tr, "filtros");
      if (!f.value.trim() && cap != null) f.value = cap;
    });

    const calc = $("#calculo");
    if (cap == null || n === 0) {
      el.total_filtros.value = "";
      calc.textContent = "Enter the capacity and the number of small boxes.";
    } else {
      let total = 0, iguais = true;
      linhas().forEach((tr) => {
        const v = campo(tr, "filtros").value.trim();
        total += /^\d+$/.test(v) ? +v : cap;
        if (v !== String(cap)) iguais = false;
      });
      el.total_filtros.value = total;
      calc.textContent = iguais ? `${n} small box(es) × ${cap} filters = ${total} filters.`
                                : `${n} small box(es), ${total} filters (custom count in some boxes).`;
    }
    estadoInternos();
  }

  function estadoInternos() {
    const n = linhas().length;
    const feitos = linhas().filter((tr) => campo(tr, "num").value.trim()).length;
    const e = $("#estado-internos");
    e.textContent = n ? `Internal lots: ${feitos}/${n} registered` : "Internal lots: –";
    e.className = !n ? "suave" : feitos === n ? "sim" : "nao";
    const opto = el.lote_geral.value.trim();
    $$("[data-opto]", corpo).forEach((td) => (td.textContent = opto || "–"));
  }

  el.capacidade_caixa_menor.addEventListener("input", () => calcular(false));
  el.numero_caixas_menores.addEventListener("input", () => calcular(false));
  el.lote_geral.addEventListener("input", estadoInternos);
  corpo.addEventListener("input", (e) => {
    if (e.target.name.startsWith("cx_filtros_")) calcular(false);
    else estadoInternos();
  });
  $("#recalcular").addEventListener("click", () => calcular(true));
  $("#preencher").addEventListener("click", () => {
    linhas().forEach((tr, k) => {
      const num = campo(tr, "num");
      if (!num.value.trim()) num.value = String(k + 1).padStart(DIGITOS, "0");
    });
    estadoInternos();
    sujo(true);
  });
  $("#limpar-codigos").addEventListener("click", () => {
    linhas().forEach((tr) => (campo(tr, "num").value = ""));
    estadoInternos();
    sujo(true);
  });

  $$("[data-hoje]").forEach((b) => b.addEventListener("click", () => {
    const d = new Date(), p = (x) => String(x).padStart(2, "0");
    b.previousElementSibling.value = `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
    sujo(true);
  }));

  // aviso de alterações não gravadas
  let alterado = false;
  function sujo(v) {
    alterado = v;
    $("#estado-form").textContent = v ? "Unsaved changes" : "No unsaved changes";
    $("#estado-form").className = v ? "nao" : "suave";
  }
  form.addEventListener("input", () => sujo(true));
  form.addEventListener("change", () => sujo(true));
  form.addEventListener("submit", (e) => {
    const n = inteiro(el.numero_caixas_menores.value);
    if (!el.lote_geral.value.trim()) { e.preventDefault(); alert("Enter the OPTO batch first."); el.lote_geral.focus(); return; }
    if (!n) { e.preventDefault(); alert("Enter the number of small boxes."); el.numero_caixas_menores.focus(); return; }
    alterado = false;
  });
  window.addEventListener("beforeunload", (e) => { if (alterado) { e.preventDefault(); e.returnValue = ""; } });
  $$("[data-sair]").forEach((a) => a.addEventListener("click", (e) => {
    if (alterado && !confirm("Leave without saving? The changes will be lost.")) e.preventDefault();
    else alterado = false;
  }));

  calcular(false);
  // a página voltou com erro: o que foi enviado ainda não está gravado
  if (document.querySelector(".aviso-flash.erro, .aviso-flash.aviso")) sujo(true);
})();
