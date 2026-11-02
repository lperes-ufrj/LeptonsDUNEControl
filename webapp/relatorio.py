"""Relatório da tarefa em HTML (página de opções do QR code e as páginas de cada seção), a imagem do QR code e o
servidor leve que deixa celulares da mesma rede abrirem o link do QR.

O conteúdo das páginas é o mesmo do programa de mesa (mesmos links /t/<id>/<código>/...: QR codes já impressos
continuam funcionando).
"""
import base64
import hmac
import html
import os
import re
import socket
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import qrcode
from PIL import Image, ImageDraw, ImageFont

from . import banco, dados, lotes

# Modo 1 (padrão): URL_BASE_RELATORIO vazio -> o servidor leve na porta abaixo atende o link do QR para
#                  celulares/computadores na mesma rede, enquanto o programa estiver aberto.
# Modo 2: URL_BASE_RELATORIO = endereço onde a pasta de relatórios será publicada; as páginas são gravadas em
#         PASTA_RELATORIOS e basta copiá-las para esse endereço.
SERVIDOR_PORTA = 8765
URL_BASE_RELATORIO = ""
PASTA_RELATORIOS = dados.PASTA / "relatorios"
servidor_http = None

N_FILTROS = dados.N_FILTROS
AMOSTRAS_IMERSAO = AMOSTRAS_EFICIENCIA = dados.AMOSTRAS
ITENS_IMERSAO = dados.ITENS_IMERSAO
LIMITE_PERDA_PCT = dados.LIMITE_PERDA_PCT
LIMITE_EFICIENCIA = dados.LIMITE_EFICIENCIA
MIN_AMOSTRAS_EFICIENCIA = dados.MIN_AMOSTRAS_EFICIENCIA
CORES_CLASSE = {"A": "#c62828", "B": "#ef6c00", "C": "#2e7d32"}
token_tarefa = banco.token_tarefa
area_amostra_ef = dados.area_amostra_ef
resumo_visual_dados = dados.resumo_visual
estado_imersao_dados = dados.estado_imersao
estado_eficiencia_dados = dados.estado_eficiencia


def decisao_lote(estado_im, estado_ef):
    return dados.decisao_lote(estado_im, estado_ef).upper()


def diferenca_massas_ef(r):
    """Massa depois - massa antes (g) de uma amostra gravada; '' se faltar algum valor."""
    a, d = dados.numero(r.get("massa_antes")), dados.numero(r.get("massa_depois"))
    return "" if a is None or d is None else format(d - a, ".5f")


def coletar_dados_relatorio(tarefa_id):
    """Tudo o que entra no relatório, no formato das funções abaixo (vindas do programa de mesa)."""
    d = dados.ler_tarefa(tarefa_id)
    if d is None:
        return None
    t = d["tarefa"]
    con = dados._conectar(dados.DB_TAREFAS)
    try:
        linhas = [dict(r) for r in con.execute("SELECT * FROM tarefa_lotes WHERE id_tarefa = ? ORDER BY id", (tarefa_id,))]
    finally:
        con.close()
    # as duas listas vêm de tarefa_lotes na mesma ordem: a origem dos filtros segue pela posição
    origem = [l.get("filtros_origem") or [] for l in d["lotes"]]
    entradas = lotes.entradas_gravadas(linhas, t.get("lote_entrada_id"), t.get("codigo_lote"))
    if len(origem) != len(entradas):
        origem = [[] for _ in entradas]
    d["lotes"] = [{"interno": e["codigo_lote"], "chegada": e["chegada"], "empresa": e["empresa"], "lote_empresa": "",
                   "lote_interno": e["codigo_interno"], "filtros": "" if e["filtros"] is None else e["filtros"],
                   "tipo": e["tipo"], "posicoes": lotes.faixas(o)}
                  for e, o in zip(entradas, origem)]
    d["massas"] = [{"posicao": p, "massa_antes": m.get("massa_antes"), "massa_depois": m.get("massa_depois"),
                    "densidade_massa_ug_cm2": m.get("densidade_massa_ug_cm2")} for p, m in sorted(d["massas"].items())]
    d["im_obs"] = t.get("imersao_observacoes") or ""
    return d


def _signoff_dados(t):
    return (t.get("qa_signoff_por") or "").strip(), (t.get("qa_signoff_data") or "").strip()


CSS_RELATORIO = """
body{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#e9edf1;color:#222;font-size:14px}
.pagina{max-width:1100px;margin:0 auto;background:#fff;padding:16px 20px 28px}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #9aa7b5;padding:4px 6px;text-align:center;vertical-align:middle;font-size:12.5px}
th{background:#1f3a5f;color:#fff}
td.l{text-align:left}
.zebra tr:nth-child(even) td{background:#eef3f9}
.topo{border-bottom:3px solid #1f3a5f;margin-bottom:12px}
.topo td{border:0;padding:4px}
.topo img{height:46px}
.topo h1{margin:0;font-size:18px;color:#1f3a5f}
.topo p{margin:2px 0 0;font-size:12px;color:#555}
h2{background:#1f3a5f;color:#fff;font-size:14px;margin:18px 0 8px;padding:6px 10px}
h3{font-size:13px;color:#1f3a5f;margin:14px 0 6px}
.scroll{overflow-x:auto}
.campos td{border:0;border-bottom:1px solid #cfd6de;text-align:left;font-size:13px;padding:5px 6px}
.campos b{color:#1f3a5f}
.ok{color:#2e7d32;font-weight:700}
.ruim{color:#c62828;font-weight:700}
.neutro{color:#888}
.caixa{border:2px solid #1f3a5f;padding:10px 14px;margin:12px 0}
.caixa .titulo{font-size:12px;color:#555}
.caixa .valor{font-size:24px;font-weight:700}
.resumo td{text-align:left;font-size:13px}
.sel{display:inline-block;border:2px solid;border-radius:10px;padding:0 6px;font-weight:700}
.nota{font-size:11.5px;color:#555;margin:6px 0}
.botao{display:block;border:1px solid #1f3a5f;border-left:8px solid #1f3a5f;padding:12px 14px;margin:10px 0;
       text-decoration:none;color:#1f3a5f;background:#f4f6f8}
.botao b{font-size:15px;display:block}
.botao span{font-size:12px;color:#555}
.acoes{margin:10px 0}
.acoes a,.acoes button{font-size:12px;margin-right:8px;padding:5px 10px;border:1px solid #1f3a5f;background:#fff;
       color:#1f3a5f;text-decoration:none;cursor:pointer}
.rodape{margin-top:22px;font-size:11px;color:#777;border-top:1px solid #ccc;padding-top:6px}
@media (max-width:600px){.topo td.logo{display:none}.topo h1{font-size:15px}.pagina{padding:12px}}
@media print{
  body{background:#fff}.pagina{max-width:none;padding:0}.acoes{display:none}
  th,h2{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  tr{page-break-inside:avoid}
}
"""

PAGINAS_RELATORIO = ("index", "completo", "visual", "crio", "eficiencia")
_cache_logos = {}


def _esc(v):
    return html.escape("" if v is None else str(v))


def _logo_b64(nome):
    if nome not in _cache_logos:
        try:
            with open(dados.BASE / nome, "rb") as f:
                _cache_logos[nome] = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
        except Exception:
            _cache_logos[nome] = ""
    return _cache_logos[nome]


TXT_ESTADO = {"approved": "APPROVED", "rejected": "REJECTED", "partial": "IN PROGRESS", "empty": "NOT FILLED"}
CLS_ESTADO = {"approved": "ok", "rejected": "ruim", "partial": "neutro", "empty": "neutro"}


# ---------------- blocos HTML ----------------
def _cx(opcoes, escolhido):
    """Caixas de seleção no estilo do formulário."""
    partes = []
    for o in opcoes:
        marca = "&#9745; <b>" + _esc(o) + "</b>" if o == escolhido else "&#9744; " + _esc(o)
        partes.append(marca)
    return "<br>".join(partes)


def _cabecalho_pagina(subtitulo):
    esq = _logo_b64("esquerda.png")
    dir_ = _logo_b64("direita.png")
    img_esq = '<img src="' + esq + '" alt="">' if esq else ""
    img_dir = '<img src="' + dir_ + '" alt="">' if dir_ else ""
    return (
        '<table class="topo"><tr>'
        '<td class="logo" style="width:120px">' + img_esq + '</td>'
        '<td style="text-align:center"><h1>DUNE HD – X-ARAPUCA PTP FILMS<br>DEPOSITION INSPECTION RECORD</h1>'
        '<p>' + _esc(subtitulo) + '</p></td>'
        '<td class="logo" style="width:120px;text-align:right">' + img_dir + '</td>'
        '</tr></table>'
    )


def _linha_proc(data, quem):
    return ("<p><b>Date:</b> " + (_esc(data) or "-") + " &nbsp;|&nbsp; <b>Performed by:</b> " + (_esc(quem) or "-") + "</p>")


def _linha_rev(supervisor, data, revisado):
    if revisado == "Yes":
        return ("<p><b>Technical Supervisor review:</b> signed by " + (_esc(supervisor) or "-")
                + " on " + (_esc(data) or "-") + "</p>")
    return "<p><b>Technical Supervisor review:</b> <span class='neutro'>pending</span></p>"


def _celula_campo(rotulo, valor):
    return "<b>" + _esc(rotulo) + ":</b> " + (_esc(valor) if valor not in (None, "") else "-")


def _bloco_info(d):
    t = d["tarefa"]
    c = d["cab"]
    inspetor = c.get("inspector") or t.get("responsavel")
    lotes_txt = "<br>".join(
        _esc(l["interno"])
        + (" &nbsp;|&nbsp; internal lot <b>" + _esc(l.get("lote_interno")) + "</b>" if l.get("lote_interno") else "")
        + (" &nbsp;|&nbsp; " + ("cleaned on " if l.get("tipo") == "limpeza" else "arrival ") + _esc(l["chegada"])
           if l["chegada"] else "")
        + (" &nbsp;|&nbsp; " + _esc(l["filtros"]) + " filters" if l["filtros"] not in ("", None) else "")
        + (" &nbsp;|&nbsp; <b>used for filters " + _esc(l["posicoes"]) + "</b>" if l.get("posicoes") else "")
        for l in d["lotes"]
    ) or "-"
    if d.get("sem_origem"):
        lotes_txt += "<br><i>" + str(d["sem_origem"]) + " filter(s) without origin</i>"

    linhas = [
        (_celula_campo("BOX PID", t.get("codigo_tarefa")), _celula_campo("DEPOSITION DATE", t.get("data_inicio"))),
        (_celula_campo("RUN EVAPORATION", c.get("run_evaporation")), _celula_campo("POSITION FILTERS", t.get("position_range"))),
        (_celula_campo("PTP MASS (g)", t.get("massa_ptp_g")), _celula_campo("INSPECTOR NAME", inspetor)),
        (_celula_campo("FILTER TYPE", t.get("descricao")), _celula_campo("RECORDED", t.get("data_hora_registro"))),
        (_celula_campo("PTP BATCH", t.get("lote_ptp")), ""),
    ]
    tab = "".join("<tr><td>" + a + "</td><td>" + b + "</td></tr>" for a, b in linhas)
    tab += "<tr><td colspan='2'><b>BATCHES:</b><br>" + lotes_txt + "</td></tr>"
    tab += ("<tr><td colspan='2'><b>CHILDREN PID&#39;S:</b> &nbsp; P02: " + _esc(c.get("pid_p02") or "-")
            + " &nbsp; P03: " + _esc(c.get("pid_p03") or "-") + " &nbsp; P14: " + _esc(c.get("pid_p14") or "-") + "</td></tr>")
    tab += "<tr><td colspan='2'><b>NOTES:</b> " + (_esc(t.get("observacoes")) or "-") + "</td></tr>"

    massas = ""
    if d["massas"]:
        linhas_m = "".join(
            "<tr><td>" + _esc(m["posicao"]) + "</td><td>" + _esc(m["massa_antes"]) + "</td><td>"
            + _esc(m["massa_depois"]) + "</td><td>" + _esc(m["densidade_massa_ug_cm2"]) + "</td></tr>"
            for m in d["massas"])
        massas = ("<h3>Mass control by position</h3><div class='scroll'><table class='zebra'><tr><th>Position</th>"
                  "<th>Mass before (g)</th><th>Mass after (g)</th><th>Mass density (&micro;g/cm&sup2;)</th></tr>"
                  + linhas_m + "</table></div>")
    return ("<h2>1. SHIPMENT CONTAINER INFORMATION</h2><table class='campos'>" + tab + "</table>" + massas)



def _bloco_signoff(d):
    """Último tópico do relatório completo: aval final do QA."""
    por, data = _signoff_dados(d["tarefa"])
    return ("<h2 id='signoff'>5. FINAL QA SIGN-OFF</h2><table class='campos'><tr>"
            "<td><b>Final QA Sign-Off by:</b> " + (_esc(por) or "______________________________") + "</td>"
            "<td><b>Date:</b> " + (_esc(data) or "____ / ____ / ________") + "</td></tr></table>")


def _bloco_decisao(d):
    ei = estado_imersao_dados(d)
    ee = estado_eficiencia_dados(d)
    dec = decisao_lote(ei, ee)
    cor = {"APPROVED": "#2e7d32", "REJECTED": "#c62828"}.get(dec, "#1f3a5f")
    completos, cont, algum = resumo_visual_dados(d)
    rev = d["ef_teste"]
    if rev.get("revisado") == "Yes":
        assinatura = "Signed by " + _esc(rev.get("supervisor") or "-") + " on " + _esc(rev.get("data_revisao") or "-")
    else:
        assinatura = "Pending Technical Supervisor review"
    visual_txt = (str(completos) + "/" + str(N_FILTROS) + " substrates classified &nbsp;|&nbsp; A: " + str(cont["A"])
                  + " (reject) &nbsp; B: " + str(cont["B"]) + " (QA/QC review) &nbsp; C: " + str(cont["C"]) + " (accept)")
    por_so, data_so = _signoff_dados(d["tarefa"])
    if por_so:
        signoff_html = "<b>" + _esc(por_so) + "</b> &nbsp;|&nbsp; Date: " + (_esc(data_so) or "-")
    else:
        signoff_html = "<span class='neutro'>Pending final QA sign-off</span>"
    signoff_row = '<tr><td><b>QA Sign-off by</b></td><td>' + signoff_html + '</td></tr>'
    return (
        '<div class="caixa" style="border-color:' + cor + '">'
        '<div class="titulo">BATCH DECISION (cryogenic immersion + optical efficiency)</div>'
        '<div class="valor" style="color:' + cor + '">' + dec + '</div>'
        '<table class="resumo">'
        '<tr><td><b>Visual inspection</b></td><td>' + visual_txt + '</td></tr>'
        '<tr><td><b>Cryogenic immersion</b></td><td class="' + CLS_ESTADO[ei] + '">' + TXT_ESTADO[ei] + '</td></tr>'
        '<tr><td><b>Optical efficiency</b></td><td class="' + CLS_ESTADO[ee] + '">' + TXT_ESTADO[ee] + '</td></tr>'
        + signoff_row +
        '</table></div>'
    )


def _bloco_visual(d):
    linhas = []
    for n in range(1, N_FILTROS + 1):
        f = d["filtros"].get(n, {})

        def v(k, f=f):
            return f.get(k) or ""

        classes = []
        for cl in ("A", "B", "C"):
            if v("classification") == cl:
                classes.append('<span class="sel" style="color:' + CORES_CLASSE[cl] + '">' + cl + '</span>')
            else:
                classes.append(cl)
        linhas.append(
            "<tr><td><b>" + format(n, "02d") + "</b></td>"
            "<td class='l'>" + _cx(["Pass", "Fail"], v("visual_status")) + "</td>"
            "<td class='l'>" + _cx(["OK", "Minor", "Major"], v("uniformity")) + "</td>"
            + "".join("<td class='l'>" + _cx(["Yes", "No"], v(k)) + "</td>"
                      for k in ("stains", "particles", "edge_defects", "finger_defects", "other_defects"))
            + "<td class='l'>" + _esc(v("comments")) + "</td>"
            "<td>" + " / ".join(classes) + "</td></tr>"
        )
    cab = "".join("<th>" + h + "</th>" for h in (
        "Filter n&ordm;", "Visual Status", "Uniformity", "Stains", "Particles", "Edge Defects",
        "Finger Defects", "Other Defects", "Comments", "Classification"))
    legenda = (
        "<h3>Classification</h3><table><tr><th>Class</th><th>Description</th><th>Disposition</th></tr>"
        "<tr><td><b>A</b></td><td class='l'>Defects affecting coating integrity, adhesion, or optical performance.</td><td>Reject glass substrate</td></tr>"
        "<tr><td><b>B</b></td><td class='l'>Localized defects with limited impact requiring evaluation.</td><td>QA/QC review</td></tr>"
        "<tr><td><b>C</b></td><td class='l'>Minor cosmetic defects with no expected impact on performance.</td><td>Accept</td></tr></table>"
    )
    return ("<h2 id='visual'>2. VISUAL INSPECTION TABLE</h2>" + _linha_proc(d["cab"].get("data_inspecao"), d["cab"].get("operador"))
            + "<div class='scroll'><table class='zebra'><tr>" + cab + "</tr>"
            + "".join(linhas) + "</table></div>" + legenda
            + _linha_rev(d["cab"].get("supervisor"), d["cab"].get("data_revisao"), d["cab"].get("revisado")))


def _bloco_crio(d):
    linhas = ""
    for amostra in AMOSTRAS_IMERSAO:
        r = d["im_massas"].get(amostra) or {}
        if r.get("diferenca_g"):
            dif = _esc(r["diferenca_g"]) + " g (" + _esc(r.get("diferenca_pct")) + " %)"
        else:
            dif = "-"
        ap = r.get("aprovado") or ""
        cond = '<span class="ok">Approved</span>' if ap == "Yes" else ('<span class="ruim">Rejected</span>' if ap == "No" else "-")
        linhas += ("<tr><td><b>" + amostra + "</b></td><td>" + (_esc(r.get("massa_antes")) or "-") + "</td><td>"
                   + (_esc(r.get("massa_depois")) or "-") + "</td><td>" + dif + "</td><td>" + cond + "</td></tr>")
    massas = ("<div class='scroll'><table class='zebra'><tr><th>Sample Control</th><th>Mass Before (g)</th><th>Mass After (g)</th>"
              "<th>Difference (after &minus; before)</th><th>Condition (loss &le; " + format(LIMITE_PERDA_PCT, "g") + " %)</th></tr>"
              + linhas + "</table></div>")
    nota = ("<p class='nota'>Accept criteria: a maximum mass loss of " + format(LIMITE_PERDA_PCT, "g")
            + "% is acceptable. Any control substrate with a mass loss greater than "
            + format(LIMITE_PERDA_PCT, "g") + "% is non-conforming.</p>")

    itens = ""
    for chave, titulo, aceite, rejeitado in ITENS_IMERSAO:
        itens += ("<tr><td><b>" + _esc(titulo) + "</b></td><td class='l'>" + _esc(aceite) + "</td><td class='l'>"
                  + _esc(rejeitado) + "</td><td class='l'>" + _cx(["Yes", "No"], d["im_itens"].get(chave) or "") + "</td></tr>")
    criterios = ("<h3>Post-immersion inspection</h3><div class='scroll'><table class='zebra'><tr><th>Inspection Item</th>"
                 "<th>Acceptance Criteria</th><th>Rejected Condition</th><th>Approved?</th></tr>" + itens + "</table></div>")
    obs = "<p><b>Notes:</b> " + (_esc(d["im_obs"]) or "-") + "</p>"
    est = estado_imersao_dados(d)
    res = "<p><b>Result:</b> <span class='" + CLS_ESTADO[est] + "'>" + TXT_ESTADO[est] + "</span></p>"
    proc = _linha_proc(d["tarefa"].get("imersao_data"), d["tarefa"].get("imersao_operador"))
    rev = _linha_rev(d["tarefa"].get("imersao_supervisor"), d["tarefa"].get("imersao_data_revisao"),
                     d["tarefa"].get("imersao_revisado"))
    return "<h2 id='crio'>3. CRYOGENIC IMMERSION</h2>" + proc + massas + nota + criterios + obs + res + rev


def _bloco_ef(d):
    te = d["ef_teste"]
    campos = [
        (_celula_campo("TEST DATE", te.get("data_teste")), _celula_campo("REFERENCE SUBSTRATE ID", te.get("ref_id"))),
        (_celula_campo("REFERENCE INSTALLATION DATE", te.get("ref_data")),
         _celula_campo("MEAN ROOM TEMPERATURE (°C)", te.get("temperatura_c"))),
        (_celula_campo("MEAN RELATIVE HUMIDITY (%)", te.get("umidade_pct")),
         _celula_campo("PERFORMED BY (OPERATOR)", te.get("operador"))),
    ]
    tab_t = "<table class='campos'>" + "".join("<tr><td>" + a + "</td><td>" + b + "</td></tr>" for a, b in campos) + "</table>"

    l_c = ""
    l_e = ""
    for amostra in AMOSTRAS_EFICIENCIA:
        r = d["ef_amostras"].get(amostra) or {}
        testada = r.get("testada") or ""
        dens = r.get("densidade_ug_cm2") or "-"
        l_c += ("<tr><td><b>" + amostra + "</b></td><td class='l'>" + _cx(["Yes", "No"], testada) + "</td><td>"
                + (_esc(r.get("massa_antes")) or "-") + "</td><td>" + (_esc(r.get("massa_depois")) or "-") + "</td><td>"
                + (_esc(diferenca_massas_ef(r)) or "-") + "</td><td>" + (_esc(area_amostra_ef(r)) or "-") + "</td><td>"
                + _esc(dens) + "</td></tr>")
        if testada == "No":
            cond = "<span class='neutro'>Not tested</span>"
        elif (r.get("aprovado") or "") == "Yes":
            cond = "<span class='ok'>Approved</span>"
        elif (r.get("aprovado") or "") == "No":
            cond = "<span class='ruim'>Rejected</span>"
        else:
            cond = "-"
        l_e += ("<tr><td><b>" + amostra + "</b></td><td>" + (_esc(r.get("eficiencia")) or "-") + "</td><td>" + cond + "</td></tr>")

    tab_c = ("<h3>QC samples &ndash; mass and area</h3><div class='scroll'><table class='zebra'><tr><th>Control position</th>"
             "<th>Tested?</th><th>Mass before (g)</th><th>Mass after (g)</th><th>M.after &minus; M.before (g)</th>"
             "<th>Area (cm&sup2;)</th><th>Density (&micro;g/cm&sup2;)</th></tr>" + l_c + "</table></div>")
    tab_e = ("<h3>Efficiency analysis</h3><div class='scroll'><table class='zebra'><tr><th>Control position</th><th>Relative efficiency (x)</th>"
             "<th>Condition (x &ge; " + format(LIMITE_EFICIENCIA, "g") + ")</th></tr>" + l_e + "</table></div>")
    nota = ("<p class='nota'>Only samples marked Tested = Yes are evaluated. x = UV transmission efficiency relative to the "
            "reference substrate; x &ge; " + format(LIMITE_EFICIENCIA, "g") + " is approved (no upper bound). The batch is approved only "
            "if at least " + str(MIN_AMOSTRAS_EFICIENCIA) + " samples are tested and all tested samples pass.</p>")
    obs = "<p><b>Notes:</b> " + (_esc(te.get("observacoes")) or "-") + "</p>"
    est = estado_eficiencia_dados(d)
    res = "<p><b>Result:</b> <span class='" + CLS_ESTADO[est] + "'>" + TXT_ESTADO[est] + "</span></p>"
    if te.get("revisado") == "Yes":
        rev = ("<p><b>Technical Supervisor review:</b> signed by " + _esc(te.get("supervisor") or "-")
               + " on " + _esc(te.get("data_revisao") or "-") + "</p>")
    else:
        rev = "<p><b>Technical Supervisor review:</b> <span class='neutro'>pending</span></p>"
    return ("<h2 id='eficiencia'>4. VUV OPTICAL EFFICIENCY</h2>" + tab_t + tab_c + tab_e + nota + res + obs + rev)


def _documento(titulo, corpo):
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>' + _esc(titulo) + '</title><style>' + CSS_RELATORIO + '</style></head>'
            '<body><div class="pagina">' + corpo + '</div></body></html>')


def _rodape():
    return ('<div class="rodape">Generated on ' + datetime.now().strftime("%Y-%m-%d %H:%M")
            + ' by Deposition Control System for DUNE.</div>')


def pagina_relatorio(d, secao):
    titulos = {
        "completo": "Deposition Inspection Record",
        "visual": "Visual inspection",
        "crio": "Cryogenic immersion",
        "eficiencia": "Optical efficiency",
    }
    titulo = titulos[secao]
    acoes = ('<div class="acoes"><a href="index.html">&larr; Options</a>'
             '<button onclick="window.print()">Print / Save as PDF</button></div>')
    corpo = _cabecalho_pagina("Inspection of Evaporated PTP Film – " + titulo) + acoes + _bloco_info(d)
    if secao == "completo":
        corpo += _bloco_decisao(d) + _bloco_visual(d) + _bloco_crio(d) + _bloco_ef(d) + _bloco_signoff(d)
    elif secao == "visual":
        corpo += _bloco_visual(d)
    elif secao == "crio":
        corpo += _bloco_crio(d)
    else:
        corpo += _bloco_ef(d)
    return _documento(titulo + " – " + str(d["tarefa"].get("codigo_tarefa") or ""), corpo + _rodape())


def pagina_menu(d):
    t = d["tarefa"]
    c = d["cab"]
    ei = estado_imersao_dados(d)
    ee = estado_eficiencia_dados(d)
    completos, cont, algum = resumo_visual_dados(d)
    lotes_txt = ", ".join(
        _esc(l["interno"]) + (" / " + _esc(l.get("lote_interno")) if l.get("lote_interno") else "")
        + (" (filters " + _esc(l["posicoes"]) + ")" if l.get("posicoes") else "")
        for l in d["lotes"] if l["interno"]) or "-"

    resumo = (
        "<table class='campos'>"
        "<tr><td>" + _celula_campo("PID", t.get("codigo_tarefa")) + "</td><td>" + _celula_campo("Date", t.get("data_inicio")) + "</td></tr>"
        "<tr><td>" + _celula_campo("Run", c.get("run_evaporation")) + "</td><td>" + _celula_campo("Positions", t.get("position_range")) + "</td></tr>"
        "<tr><td colspan='2'><b>Batches:</b> " + lotes_txt + "</td></tr></table>"
    )
    dec = decisao_lote(ei, ee)
    cor = {"APPROVED": "#2e7d32", "REJECTED": "#c62828"}.get(dec, "#1f3a5f")
    por_so, data_so = _signoff_dados(t)
    if por_so:
        linha_so = ('<div class="titulo">QA Sign-off by: <b>' + _esc(por_so) + '</b> &nbsp;|&nbsp; Date: '
                    + (_esc(data_so) or "-") + '</div>')
    else:
        linha_so = '<div class="titulo">QA Sign-off: <span class="neutro">pending</span></div>'
    caixa = ('<div class="caixa" style="border-color:' + cor + '"><div class="titulo">BATCH DECISION</div>'
             '<div class="valor" style="color:' + cor + '">' + dec + '</div>' + linha_so + '</div>')

    def botao(nome, titulo, detalhe):
        return '<a class="botao" href="' + nome + '.html"><b>' + titulo + '</b><span>' + detalhe + '</span></a>'

    botoes = (
        botao("completo", "Deposition Inspection Record (full report)",
              "Container information, visual inspection, cryogenic immersion and optical efficiency")
        + botao("visual", "Visual inspection",
                str(completos) + "/" + str(N_FILTROS) + " substrates classified – A: " + str(cont["A"])
                + ", B: " + str(cont["B"]) + ", C: " + str(cont["C"]))
        + botao("crio", "Cryogenic immersion", TXT_ESTADO[ei])
        + botao("eficiencia", "Optical efficiency", TXT_ESTADO[ee])
    )
    corpo = (_cabecalho_pagina("Report options") + resumo + caixa + "<h3>Choose a report</h3>" + botoes + _rodape())
    return _documento("Report options – " + str(t.get("codigo_tarefa") or ""), corpo)


def renderizar_pagina(tarefa_id, nome):
    d = coletar_dados_relatorio(tarefa_id)
    if d is None:
        return _documento("Not found", "<p>Sample not found.</p>")
    if nome == "index":
        return pagina_menu(d)
    return pagina_relatorio(d, nome)


# ---------------- servidor local ----------------
class _HandlerRelatorio(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _enviar(self, codigo, texto):
        dados = texto.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        caminho = urllib.parse.urlparse(self.path).path
        m = re.fullmatch(r"/t/(\d+)/([0-9a-f]{12})/(?:(index|completo|visual|crio|eficiencia)\.html)?", caminho)
        if not m:
            self._enviar(404, _documento("Not found", "<p>Not found.</p>"))
            return
        tarefa_id = int(m.group(1))
        try:
            if not hmac.compare_digest(m.group(2), token_tarefa(tarefa_id)):
                self._enviar(404, _documento("Not found", "<p>Not found.</p>"))
                return
            self._enviar(200, renderizar_pagina(tarefa_id, m.group(3) or "index"))
        except Exception:
            self._enviar(500, _documento("Error", "<p>Could not generate the report.</p>"))


def iniciar_servidor_relatorios():
    """Inicia o servidor leve em segundo plano (modo 1). Retorna True se estiver ativo."""
    global servidor_http
    if URL_BASE_RELATORIO or servidor_http is not None:
        return servidor_http is not None
    try:
        servidor_http = ThreadingHTTPServer(("0.0.0.0", SERVIDOR_PORTA), _HandlerRelatorio)
    except OSError:
        servidor_http = None
        return False
    threading.Thread(target=servidor_http.serve_forever, daemon=True).start()
    return True


def ip_local():
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(("10.255.255.255", 1))     # não envia nada; só descobre a interface de rede usada
        ip = sk.getsockname()[0]
        sk.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def url_relatorio(tarefa_id, nome="index"):
    tok = token_tarefa(tarefa_id)
    if URL_BASE_RELATORIO:
        return URL_BASE_RELATORIO.rstrip("/") + "/" + str(tarefa_id) + "_" + tok + "/" + nome + ".html"
    return "http://" + ip_local() + ":" + str(SERVIDOR_PORTA) + "/t/" + str(tarefa_id) + "/" + tok + "/" + nome + ".html"


def gerar_arquivos_relatorio(tarefa_id):
    """Grava as páginas HTML da tarefa em PASTA_RELATORIOS (modo 2). Retorna a pasta."""
    pasta = os.path.join(PASTA_RELATORIOS, str(tarefa_id) + "_" + token_tarefa(tarefa_id))
    os.makedirs(pasta, exist_ok=True)
    d = coletar_dados_relatorio(tarefa_id)
    for nome in PAGINAS_RELATORIO:
        texto = pagina_menu(d) if nome == "index" else pagina_relatorio(d, nome)
        with open(os.path.join(pasta, nome + ".html"), "w", encoding="utf-8") as f:
            f.write(texto)
    return pasta


# ---------------- QR code ----------------
def _fonte_qr(tamanho, negrito=True):
    """Fonte TrueType disponível no sistema (Windows/Linux/macOS), com fallback."""
    nomes = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf"] if negrito
             else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"])
    for n in nomes:
        try:
            return ImageFont.truetype(n, tamanho)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=tamanho)
    except Exception:
        return ImageFont.load_default()


def gerar_imagem_qr(url, pid, caminho):
    """Cria o PNG do QR com o PID da tarefa impresso logo abaixo."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    larg, alt = img_qr.size
    pid = (pid or "").strip()
    if not pid:
        img_qr.save(caminho, "PNG")
        return caminho

    margem = 20
    tam = 44
    fonte = _fonte_qr(tam)
    medidor = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while tam > 12:
        caixa = medidor.textbbox((0, 0), pid, font=fonte)
        if caixa[2] - caixa[0] <= larg - 2 * margem:
            break
        tam -= 2
        fonte = _fonte_qr(tam)
    caixa = medidor.textbbox((0, 0), pid, font=fonte)
    larg_txt, alt_txt = caixa[2] - caixa[0], caixa[3] - caixa[1]

    faixa = alt_txt + 2 * margem
    final = Image.new("RGB", (larg, alt + faixa), "white")
    final.paste(img_qr, (0, 0))
    d = ImageDraw.Draw(final)
    # a borda branca do QR (4 módulos) já separa o texto; sobe um pouco o texto
    x = (larg - larg_txt) // 2 - caixa[0]
    y = alt - 10 + (faixa - alt_txt) // 2 - caixa[1]
    d.text((x, y), pid, fill="black", font=fonte)
    final.save(caminho, "PNG")
    return caminho
