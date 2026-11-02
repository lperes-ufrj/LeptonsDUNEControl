"""Relatório em PDF com todas as informações gravadas da tarefa (pacote reportlab); igual ao do programa de mesa."""
import io
import os
from datetime import datetime

from PIL import Image, ImageChops

from . import dados
from .relatorio import (AMOSTRAS_EFICIENCIA, AMOSTRAS_IMERSAO, ITENS_IMERSAO, LIMITE_EFICIENCIA, LIMITE_PERDA_PCT,
                        MIN_AMOSTRAS_EFICIENCIA, N_FILTROS, TXT_ESTADO, area_amostra_ef, coletar_dados_relatorio,
                        decisao_lote, diferenca_massas_ef, estado_eficiencia_dados, estado_imersao_dados,
                        resumo_visual_dados)

PASTA_PDF = dados.PASTA / "relatorios_pdf"
nomes_posicoes = dados.POSICOES


def _registrar_fontes_pdf():
    """Procura uma fonte TrueType com boa cobertura de caracteres; senão usa Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidatos = [
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for normal, negrito in candidatos:
        if os.path.exists(normal) and os.path.exists(negrito):
            try:
                pdfmetrics.registerFont(TTFont("RelFonte", normal))
                pdfmetrics.registerFont(TTFont("RelFonte-Bold", negrito))
                pdfmetrics.registerFontFamily("RelFonte", normal="RelFonte", bold="RelFonte-Bold",
                                              italic="RelFonte", boldItalic="RelFonte-Bold")
                return "RelFonte", "RelFonte-Bold"
            except Exception:
                pass
    return "Helvetica", "Helvetica-Bold"


def gerar_pdf_relatorio(tarefa_id, caminho):
    """Gera o PDF com todas as informações gravadas da tarefa (usa o pacote reportlab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer,
                                    Image as RLImage, PageBreak, CondPageBreak)
    from xml.sax.saxutils import escape as xesc

    d = coletar_dados_relatorio(tarefa_id)
    if d is None:
        raise ValueError("Sample not found")
    t = d["tarefa"]
    cab = d["cab"]
    fonte, negrito = _registrar_fontes_pdf()

    AZUL = colors.HexColor("#1f3a5f")
    ZEBRA = colors.HexColor("#eef3f9")
    GRADE = colors.HexColor("#9aa7b5")
    VERDE = colors.HexColor("#2e7d32")
    VERMELHO = colors.HexColor("#c62828")
    LARANJA = colors.HexColor("#ef6c00")
    CINZA = colors.HexColor("#888888")
    largura = A4[0] - 24 * mm

    base = ParagraphStyle("base", fontName=fonte, fontSize=8, leading=10)
    est_cel = ParagraphStyle("cel", parent=base, fontSize=7.5, leading=9)
    est_cab = ParagraphStyle("cab", parent=est_cel, fontName=negrito, textColor=colors.white, alignment=TA_CENTER)
    est_titulo = ParagraphStyle("tit", parent=base, fontName=negrito, fontSize=13, leading=16,
                                alignment=TA_CENTER, textColor=AZUL)
    est_sub = ParagraphStyle("sub", parent=base, alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
    est_sec = ParagraphStyle("sec", parent=base, fontName=negrito, fontSize=10, leading=12, textColor=colors.white)
    est_h3 = ParagraphStyle("h3", parent=base, fontName=negrito, fontSize=8.5, textColor=AZUL, spaceBefore=6, spaceAfter=3)
    est_nota = ParagraphStyle("nota", parent=base, fontSize=7, leading=8.5, textColor=colors.HexColor("#555555"))

    def txt(v, vazio="-"):
        v = "" if v is None else str(v).strip()
        return xesc(v).replace("\n", "<br/>") if v else vazio

    def P(v, estilo=None, vazio="-"):
        return Paragraph(txt(v, vazio), estilo or est_cel)

    def M(markup, estilo=None):
        return Paragraph(markup, estilo or est_cel)

    def H(texto):
        return Paragraph(xesc(texto), est_cab)

    def secao(titulo):
        tb = Table([[Paragraph(xesc(titulo), est_sec)]], colWidths=[largura])
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AZUL), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return tb

    def tabela(linhas, larguras, extra=None, cabecalho=True):
        tb = Table(linhas, colWidths=[w * mm for w in larguras], repeatRows=1 if cabecalho else 0)
        estilo = [("FONTNAME", (0, 0), (-1, -1), fonte), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                  ("GRID", (0, 0), (-1, -1), 0.4, GRADE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                  ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        if cabecalho:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA])]
        if extra:
            estilo += extra
        tb.setStyle(TableStyle(estilo))
        return tb

    def hexcor(c):
        return "#" + c.hexval()[2:]

    def rev_pdf(supervisor, data, revisado):
        if revisado == "Yes":
            return M("<b>Technical Supervisor review:</b> signed by " + txt(supervisor) + " on " + txt(data))
        return M("<b>Technical Supervisor review:</b> pending")

    def proc(data, quem):
        return M("<b>Date:</b> " + txt(data) + " &nbsp;&nbsp;|&nbsp;&nbsp; <b>Performed by:</b> " + txt(quem))

    def logo(nome, alinhamento):
        """Logo sem as margens brancas do arquivo, com até 22 mm de altura e 35 mm de largura."""
        try:
            with Image.open(dados.BASE / nome) as im:
                im = im.convert("RGB")
            branco = Image.new("RGB", im.size, (255, 255, 255))
            caixa = ImageChops.difference(im, branco).point(lambda p: 255 if p > 20 else 0).getbbox()
            if caixa:
                im = im.crop(caixa)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            buf.seek(0)
            w, h = im.size
            escala = min(22 * mm / h, 35 * mm / w)
            return RLImage(buf, width=w * escala, height=h * escala, hAlign=alinhamento)
        except Exception:
            return ""

    cor_estado = {"approved": VERDE, "rejected": VERMELHO}
    story = []

    # ---------------- cabeçalho ----------------
    topo = Table([[logo("esquerda.png", "CENTER"),
                   [Paragraph("DUNE HD – X-ARAPUCA PTP FILMS", est_titulo),
                    Paragraph("DEPOSITION INSPECTION RECORD", est_titulo),
                    Paragraph("Inspection of Evaporated PTP Film", est_sub)],
                   logo("direita.png", "RIGHT")]],
                 colWidths=[40 * mm, largura - 80 * mm, 40 * mm])
    topo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.5, AZUL),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("ALIGN", (0, 0), (0, 0), "CENTER")]))
    story += [topo, Spacer(1, 6)]

    # ---------------- 1. informações da caixa ----------------
    inspetor = cab.get("inspector") or t.get("responsavel")

    def campo(rot, val):
        return M("<b>" + xesc(rot) + ":</b> " + txt(val))

    linhas = [
        [campo("BOX PID", t.get("codigo_tarefa")), campo("DEPOSITION DATE", t.get("data_inicio"))],
        [campo("RUN EVAPORATION", cab.get("run_evaporation")), campo("POSITION FILTERS", t.get("position_range"))],
        [campo("PTP MASS (g)", t.get("massa_ptp_g")), campo("INSPECTOR NAME (RESPONSIBLE)", inspetor)],
        [campo("FILTER TYPE", t.get("descricao")), campo("RECORDED", t.get("data_hora_registro"))],
        [campo("PTP BATCH", t.get("lote_ptp")), ""],
        [M("<b>CHILDREN PID'S:</b> &nbsp; P02: " + txt(cab.get("pid_p02")) + " &nbsp;&nbsp; P03: " + txt(cab.get("pid_p03"))
           + " &nbsp;&nbsp; P14: " + txt(cab.get("pid_p14"))), ""],
        [campo("NOTES", t.get("observacoes")), ""],
    ]
    anexos = [os.path.basename(a) for a in (t.get("anexos_txt") or "").split(";") if a.strip()]
    linhas.append([campo("ATTACHED FILES", ", ".join(anexos)), ""])
    story += [secao("1. SHIPMENT CONTAINER INFORMATION"), Spacer(1, 3)]
    story.append(tabela(linhas, [93, 93], cabecalho=False,
                        extra=[("SPAN", (0, 4), (1, 4)), ("SPAN", (0, 5), (1, 5)), ("SPAN", (0, 6), (1, 6))]))

    # lotes
    story.append(Paragraph("Batches", est_h3))
    if len(d["lotes"]) > 1:            # vários lotes: de onde veio cada filtro
        linhas_l = [[H("OPTO Batch"), H("Internal Lot"), H("Arrival / Cleaned"), H("Company"), H("Filters"),
                     H("Used for filters")]]
        for l in d["lotes"]:
            linhas_l.append([P(l["interno"]), P(l.get("lote_interno")), P(l["chegada"]),
                             P(l["empresa"]), P(l["filtros"]), P(l.get("posicoes") or "-")])
        story.append(tabela(linhas_l, [34, 34, 30, 40, 16, 32]))
        if d.get("sem_origem"):
            story.append(Paragraph(f"{d['sem_origem']} filter(s) without origin.", est_nota))
    else:
        linhas_l = [[H("OPTO Batch"), H("Internal Lot"), H("Arrival / Cleaned"), H("Company"), H("Filters")]]
        for l in d["lotes"]:
            linhas_l.append([P(l["interno"]), P(l.get("lote_interno")), P(l["chegada"]),
                             P(l["empresa"]), P(l["filtros"])])
        if len(linhas_l) == 1:
            linhas_l.append([P("-")] * 5)
        story.append(tabela(linhas_l, [40, 40, 36, 50, 20]))

    # massas por posição
    story.append(Paragraph("Mass control by position", est_h3))
    linhas_m = [[H("Position"), H("Mass before (g)"), H("Mass after (g)"), H("Mass density (µg/cm²)")]]
    for m in d["massas"]:
        try:
            nome_pos = nomes_posicoes.get(int(m["posicao"]), "")
        except Exception:
            nome_pos = ""
        linhas_m.append([P(str(m["posicao"]) + (" - " + nome_pos if nome_pos else "")), P(m["massa_antes"]),
                         P(m["massa_depois"]), P(m["densidade_massa_ug_cm2"])])
    if len(linhas_m) == 1:
        linhas_m.append([P("-")] * 4)
    story.append(tabela(linhas_m, [46, 46, 46, 48]))
    story.append(Spacer(1, 8))

    # ---------------- decisão do lote ----------------
    ei = estado_imersao_dados(d)
    ee = estado_eficiencia_dados(d)
    dec = decisao_lote(ei, ee)
    cor_dec = {"APPROVED": VERDE, "REJECTED": VERMELHO}.get(dec, AZUL)
    completos, cont, _ = resumo_visual_dados(d)
    rev = d["ef_teste"]
    if rev.get("revisado") == "Yes":
        assinatura = "Signed by " + txt(rev.get("supervisor")) + " on " + txt(rev.get("data_revisao"))
    else:
        assinatura = "Pending Technical Supervisor review"
    visual_txt = (str(completos) + "/" + str(N_FILTROS) + " substrates classified  |  A: " + str(cont["A"])
                  + " (reject)  B: " + str(cont["B"]) + " (QA/QC review)  C: " + str(cont["C"]) + " (accept)")

    def estado_markup(e):
        return '<font color="' + hexcor(cor_estado.get(e, CINZA)) + '"><b>' + TXT_ESTADO[e] + "</b></font>"

    por_so = (t.get("qa_signoff_por") or "").strip()
    data_so = (t.get("qa_signoff_data") or "").strip()
    signoff_pdf = ("<b>" + xesc(por_so) + "</b>  |  Date: " + txt(data_so)) if por_so else "Pending final QA sign-off"
    linhas_d = [
        [M('<font size="7" color="#555555">BATCH DECISION (cryogenic immersion + optical efficiency)</font>'), ""],
        [M('<font size="16" color="' + hexcor(cor_dec) + '"><b>' + dec + "</b></font>", ParagraphStyle("dec", parent=base, leading=20)), ""],
        [M("<b>Visual inspection</b>"), M(visual_txt)],
        [M("<b>Cryogenic immersion</b>"), M(estado_markup(ei))],
        [M("<b>Optical efficiency</b>"), M(estado_markup(ee))],
        [M("<b>QA Sign-off by</b>"), M(signoff_pdf)],
    ]
    tb_dec = Table(linhas_d, colWidths=[45 * mm, largura - 45 * mm])
    tb_dec.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.5, cor_dec), ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1)),
                                ("LINEABOVE", (0, 2), (-1, 2), 0.4, GRADE), ("INNERGRID", (0, 2), (-1, -1), 0.3, GRADE),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(tb_dec)

    # ---------------- 2. inspeção visual ----------------
    story += [PageBreak(), secao("2. VISUAL INSPECTION TABLE"), Spacer(1, 3),
              proc(cab.get("data_inspecao"), cab.get("operador")), Spacer(1, 4)]
    cabecalho_v = [H(x) for x in ("Filter nº", "Visual Status", "Uniformity", "Stains", "Particles", "Edge Defects",
                                  "Finger Defects", "Other Defects", "Comments", "Class.")]
    linhas_v = [cabecalho_v]
    extra_v = [("FONTNAME", (0, 1), (-1, -1), fonte), ("FONTSIZE", (0, 1), (-1, -1), 7.5),
               ("ALIGN", (0, 1), (-1, -1), "CENTER"), ("FONTNAME", (0, 1), (0, -1), negrito)]
    cores_valor = {"Fail": VERMELHO, "Major": VERMELHO, "Minor": LARANJA, "Yes": LARANJA,
                   "A": VERMELHO, "B": LARANJA, "C": VERDE}
    chaves = ("visual_status", "uniformity", "stains", "particles", "edge_defects", "finger_defects",
              "other_defects")
    for n in range(1, N_FILTROS + 1):
        f = d["filtros"].get(n, {})
        linha = [format(n, "02d")] + [(f.get(k) or "-") for k in chaves]
        linha.append(P(f.get("comments"), ParagraphStyle("cm", parent=est_cel, fontSize=6.8, leading=8), vazio=""))
        linha.append(f.get("classification") or "-")
        linhas_v.append(linha)
        for c in list(range(1, 8)) + [9]:
            cor = cores_valor.get(linha[c])
            if cor is not None:
                extra_v.append(("TEXTCOLOR", (c, n), (c, n), cor))
                extra_v.append(("FONTNAME", (c, n), (c, n), negrito))
    story.append(tabela(linhas_v, [11, 16, 20, 14, 17, 14, 14, 14, 44, 22], extra=extra_v))

    story.append(Paragraph("Classification", est_h3))
    linhas_c = [[H("Class"), H("Description"), H("Disposition")],
                [P("A", est_cel), P("Defects affecting coating integrity, adhesion, or optical performance."), P("Reject glass substrate")],
                [P("B", est_cel), P("Localized defects with limited impact requiring evaluation."), P("QA/QC review")],
                [P("C", est_cel), P("Minor cosmetic defects with no expected impact on performance."), P("Accept")]]
    story.append(tabela(linhas_c, [14, 120, 52]))
    story.append(Spacer(1, 4))
    story.append(rev_pdf(cab.get("supervisor"), cab.get("data_revisao"), cab.get("revisado")))

    # ---------------- 3. imersão criogênica ----------------
    story += [Spacer(1, 10), CondPageBreak(95 * mm), secao("3. CRYOGENIC IMMERSION"), Spacer(1, 3),
              proc(t.get("imersao_data"), t.get("imersao_operador")), Spacer(1, 4)]
    linhas_i = [[H("Sample Control"), H("Mass Before (g)"), H("Mass After (g)"), H("Difference (after - before)"),
                 H("Condition (loss <= " + format(LIMITE_PERDA_PCT, "g") + " %)")]]
    extra_i = [("ALIGN", (0, 1), (-1, -1), "CENTER")]
    for i, amostra in enumerate(AMOSTRAS_IMERSAO, start=1):
        r = d["im_massas"].get(amostra) or {}
        dif = (txt(r.get("diferenca_g")) + " g (" + txt(r.get("diferenca_pct")) + " %)") if r.get("diferenca_g") else "-"
        ap = r.get("aprovado") or ""
        cond = M('<font color="' + hexcor(VERDE) + '"><b>Approved</b></font>', ParagraphStyle("c1", parent=est_cel, alignment=TA_CENTER)) if ap == "Yes" else (
            M('<font color="' + hexcor(VERMELHO) + '"><b>Rejected</b></font>', ParagraphStyle("c2", parent=est_cel, alignment=TA_CENTER)) if ap == "No" else
            P("-", est_cel))
        linhas_i.append([P(amostra, est_cel), P(r.get("massa_antes")), P(r.get("massa_depois")), P(dif), cond])
    story.append(tabela(linhas_i, [30, 34, 34, 50, 38], extra=extra_i))
    story.append(Spacer(1, 3))
    story.append(Paragraph("Accept criteria: a maximum mass loss of " + format(LIMITE_PERDA_PCT, "g")
                           + "% is acceptable. Any control substrate with a mass loss greater than "
                           + format(LIMITE_PERDA_PCT, "g") + "% is non-conforming.", est_nota))

    story.append(Paragraph("Post-immersion inspection", est_h3))
    linhas_k = [[H("Inspection Item"), H("Acceptance Criteria"), H("Rejected Condition"), H("Approved?")]]
    extra_k = [("ALIGN", (3, 1), (3, -1), "CENTER")]
    for i, (chave, titulo, aceite, rejeitado) in enumerate(ITENS_IMERSAO, start=1):
        valor = d["im_itens"].get(chave) or ""
        linhas_k.append([M("<b>" + xesc(titulo) + "</b>"), P(aceite), P(rejeitado), valor or "-"])
        if valor in ("Yes", "No"):
            extra_k += [("TEXTCOLOR", (3, i), (3, i), VERDE if valor == "Yes" else VERMELHO), ("FONTNAME", (3, i), (3, i), negrito)]
    story.append(tabela(linhas_k, [36, 62, 62, 26], extra=extra_k))
    story.append(Spacer(1, 3))
    story.append(M("<b>Notes:</b> " + txt(d["im_obs"])))
    story.append(M("<b>Result:</b> " + estado_markup(ei)))
    story.append(rev_pdf(t.get("imersao_supervisor"), t.get("imersao_data_revisao"), t.get("imersao_revisado")))

    # ---------------- 4. eficiência óptica ----------------
    te = d["ef_teste"]
    story += [Spacer(1, 10), CondPageBreak(110 * mm), secao("4. VUV OPTICAL EFFICIENCY"), Spacer(1, 3)]
    linhas_t = [
        [campo("TEST DATE", te.get("data_teste")), campo("PERFORMED BY (OPERATOR)", te.get("operador"))],
        [campo("REFERENCE SUBSTRATE ID", te.get("ref_id")), campo("REFERENCE INSTALLATION DATE", te.get("ref_data"))],
        [campo("MEAN ROOM TEMPERATURE (°C)", te.get("temperatura_c")), campo("MEAN RELATIVE HUMIDITY (%)", te.get("umidade_pct"))],
    ]
    story.append(tabela(linhas_t, [93, 93], cabecalho=False))

    story.append(Paragraph("QC samples - mass and area", est_h3))
    linhas_s = [[H("Control position"), H("Tested?"), H("Mass before (g)"), H("Mass after (g)"),
                 H("M.after − M.before (g)"), H("Area (cm²)"), H("Density (µg/cm²)")]]
    linhas_x = [[H("Control position"), H("Relative efficiency (x)"),
                 H("Condition (x >= " + format(LIMITE_EFICIENCIA, "g") + ")")]]
    extra_x = [("ALIGN", (0, 1), (-1, -1), "CENTER")]
    for i, amostra in enumerate(AMOSTRAS_EFICIENCIA, start=1):
        r = d["ef_amostras"].get(amostra) or {}
        linhas_s.append([P(amostra), P(r.get("testada")), P(r.get("massa_antes")), P(r.get("massa_depois")),
                         P(diferenca_massas_ef(r)), P(area_amostra_ef(r)), P(r.get("densidade_ug_cm2"))])
        if r.get("testada") == "No":
            cond_txt, cor_c = "Not tested", CINZA
        elif (r.get("aprovado") or "") == "Yes":
            cond_txt, cor_c = "Approved", VERDE
        elif (r.get("aprovado") or "") == "No":
            cond_txt, cor_c = "Rejected", VERMELHO
        else:
            cond_txt, cor_c = "-", CINZA
        linhas_x.append([amostra, r.get("eficiencia") or "-", cond_txt])
        extra_x += [("TEXTCOLOR", (2, i), (2, i), cor_c), ("FONTNAME", (2, i), (2, i), negrito)]
    story.append(tabela(linhas_s, [26, 18, 28, 28, 32, 24, 30],
                        extra=[("ALIGN", (0, 1), (-1, -1), "CENTER")]))
    story.append(Paragraph("Efficiency analysis", est_h3))
    story.append(tabela(linhas_x, [50, 68, 68], extra=extra_x))
    story.append(Spacer(1, 3))
    story.append(Paragraph("Only samples marked Tested = Yes are evaluated. x = UV transmission efficiency relative to the "
                           "reference substrate; x >= " + format(LIMITE_EFICIENCIA, "g") + " is approved (no upper bound). "
                           "The batch is approved only if at least " + str(MIN_AMOSTRAS_EFICIENCIA)
                           + " samples are tested and all tested samples pass.", est_nota))
    story.append(Spacer(1, 3))
    story.append(M("<b>Result:</b> " + estado_markup(ee)))
    story.append(M("<b>Notes:</b> " + txt(te.get("observacoes"))))
    story.append(rev_pdf(rev.get("supervisor"), rev.get("data_revisao"), rev.get("revisado")))

    # ---------------- 5. aval final do QA ----------------
    story += [Spacer(1, 12), CondPageBreak(30 * mm), secao("5. FINAL QA SIGN-OFF"), Spacer(1, 3)]
    story.append(tabela([[campo("FINAL QA SIGN-OFF BY", por_so or "________________________________"),
                          campo("DATE", data_so or "____ / ____ / ________")]], [124, 62], cabecalho=False))

    # ---------------- rodapé e gravação ----------------
    pid_txt = str(t.get("codigo_tarefa") or "")

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont(fonte, 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(12 * mm, 8 * mm, "PID " + pid_txt + "  |  Generated on " + datetime.now().strftime("%Y-%m-%d %H:%M")
                          + "  |  Deposition Control System for DUNE")
        canvas.drawRightString(A4[0] - 12 * mm, 8 * mm, "Page " + str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(caminho, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=15 * mm,
                            title="Deposition Inspection Record - " + pid_txt,
                            author="Deposition Control System for DUNE")
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    return caminho
