"""Aba Statistics: números e histogramas do processo (deposição, inspeção visual, imersão, eficiência, lotes).

Só lê os bancos, com as mesmas regras das outras telas (dados.py). Os histogramas já saem daqui com as faixas
contadas; o estatisticas.js só desenha. Cada gráfico leva também a sua tabela (para ver os números sem o mouse).
A seção Removed filters · Cleaning lots usa filtro_retirado (retirados.py) e a origem de cada posição.
A janela Export CSV gera os mesmos números em CSV (em inglês, como os relatórios): um arquivo ou um .zip.
Cada linha das tabelas (e cada barra) leva também os seus "membros": as samples que ela conta, [id, detalhe], que a
página mostra numa janela ao clicar.
"""
import csv
import io
import math
import statistics
import zipfile
from datetime import date, datetime, timedelta

from . import chegada, dados, db, lotes, retirados
from .i18n import t

COR_POSICAO = {2: 1, 3: 2, 14: 3}          # posição -> cor da série (1, 2, 3 = azul, laranja, verde-água)
CLASSES = (("A", "Reject"), ("B", "QA/QC review"), ("C", "Accept"))      # legenda da classificação (texto DUNE)
NOME_POSICAO = {p: f"{nome} (P{p:02d})" for p, nome in dados.POSICOES.items()}


def _data(texto):
    try:
        return date.fromisoformat(str(texto or "").strip()[:10])
    except ValueError:
        return None


def _resumo_num(valores):
    """n, média, desvio padrão, mínimo e máximo (texto já formatado em '–' quando não há dado)."""
    if not valores:
        return {"n": 0}
    return {"n": len(valores), "media": statistics.fmean(valores),
            "dp": statistics.stdev(valores) if len(valores) > 1 else 0.0, "min": min(valores), "max": max(valores)}


def _passo_redondo(bruto):
    """Largura de faixa 'redonda' (1, 2, 2.5 ou 5 x 10^k) perto de bruto."""
    if bruto <= 0:
        return 1.0
    base = 10 ** math.floor(math.log10(bruto))
    return next(m * base for m in (1, 2, 2.5, 5, 10) if m * base >= bruto)


def _faixas(todos, n_alvo=12, fixos=()):
    """Bordas das faixas de um histograma, cobrindo os valores e os limites fixos (ex.: 0.75)."""
    pontos = list(todos) + list(fixos)
    lo, hi = min(pontos), max(pontos)
    if hi == lo:
        lo, hi = lo - 0.5, hi + 0.5
    passo = _passo_redondo((hi - lo) / n_alvo)
    inicio = math.floor(lo / passo) * passo
    n = max(1, math.ceil((hi - inicio) / passo + 1e-9))
    if inicio + n * passo <= hi:
        n += 1
    return [round(inicio + i * passo, 10) for i in range(n + 1)]


def _faixa_de(v, bordas):
    return max(min(int((v - bordas[0]) // (bordas[1] - bordas[0])), len(bordas) - 2), 0)


def _contar(valores, bordas):
    contagens = [0] * (len(bordas) - 1)
    for v in valores:
        contagens[_faixa_de(v, bordas)] += 1
    return contagens


def _fmt(x, casas):
    return "–" if x is None else f"{x:.{casas}f}"


def histograma(series, unidade, casas=0, limites=(), n_alvo=12, estender=True, refs=None):
    """series = [(nome, cor, [valores])] com as mesmas faixas; limites = [(valor, rótulo)] (linhas de referência).

    estender: as faixas vão até os limites (False quando eles estão longe dos dados: o gráfico só os mostra se couberem).
    refs: [(id da sample, detalhe)] na ordem dos valores da série (um histograma de uma série): os membros de cada faixa.
    """
    todos = [v for _, _, vs in series for v in vs]
    if not todos:
        return None
    bordas = _faixas(todos, n_alvo, [v for v, _ in limites] if estender else ())
    passo = bordas[1] - bordas[0]
    casas_faixa = max(casas, 0 if passo >= 1 else len(f"{passo:.10f}".rstrip("0").split(".")[1]))
    saida = {"tipo": "histograma", "bordas": bordas, "unidade": unidade, "casas": casas_faixa,
             "limites": [{"valor": v, "rotulo": r} for v, r in limites], "series": []}
    for nome, cor, vs in series:
        r = _resumo_num(vs)
        saida["series"].append({"nome": nome, "cor": cor, "contagens": _contar(vs, bordas), **r,
                                "texto": (t("n = {n} · mean {media} · s.d. {dp} · min {min} · max {max}",
                                            n=r["n"], media=_fmt(r["media"], casas), dp=_fmt(r["dp"], casas),
                                            min=_fmt(r["min"], casas), max=_fmt(r["max"], casas))
                                          if r["n"] else t("no data"))})
    faixa = lambda i: f"{bordas[i]:.{casas_faixa}f} – {bordas[i + 1]:.{casas_faixa}f}"
    saida["tabela"] = {"cab": [unidade] + [s["nome"] for s in saida["series"]],
                       "linhas": [[faixa(i)] + [s["contagens"][i] for s in saida["series"]]
                                  for i in range(len(bordas) - 1)]}
    if refs is not None:
        membros = [[] for _ in range(len(bordas) - 1)]
        for v, ref in sorted(zip(series[0][2], refs), key=lambda par: par[0]):
            membros[_faixa_de(v, bordas)].append(list(ref))
        saida["membros"] = membros
    return saida


def _semana(d):
    return d - timedelta(days=d.weekday())


def por_periodo(datas, refs=(), conta="Samples"):
    """Samples depositadas (ou outra coisa, ex.: filtros retirados) por semana (até ~6 meses) ou por mês, com os períodos
    vazios no meio; refs = ids das samples, na ordem; conta = o que é contado (cabeçalho da tabela e do CSV)."""
    if not datas:
        return None
    lo, hi = min(datas), max(datas)
    mensal = (hi - lo).days > 190
    if mensal:
        chave = lambda d: d.replace(day=1)
        passo = lambda d: (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        rotulo = lambda d: d.strftime("%Y-%m")
    else:
        chave, passo, rotulo = _semana, (lambda d: d + timedelta(days=7)), (lambda d: d.strftime("%m-%d"))
    contagem, membros = {}, {}
    for d, ref in sorted(zip(datas, refs), key=lambda par: par[0]):
        contagem[chave(d)] = contagem.get(chave(d), 0) + 1
        membros.setdefault(chave(d), []).append([ref, d.isoformat()])
    periodos, p = [], chave(lo)
    while p <= chave(hi):
        periodos.append(p)
        p = passo(p)
    nomes = [rotulo(p) for p in periodos]
    valores = [contagem.get(p, 0) for p in periodos]
    titulo = t("month") if mensal else t("week of")
    return {"tipo": "colunas", "rotulos": nomes, "valores": valores, "mensal": mensal, "conta": conta,
            "unidades": [t("sample"), t("samples")] if conta == "Samples" else [t("filter"), t("filters")],
            "dicas": [(p.strftime("%Y-%m") if mensal else t("week of {d}", d=p.isoformat())) for p in periodos],
            "tabela": {"cab": [titulo, t(conta)],
                       "linhas": [[p.strftime("%Y-%m") if mensal else p.isoformat(), v] for p, v in zip(periodos, valores)]},
            "membros": [membros.get(p, []) for p in periodos]}


def barras(itens, unidade="", casas=0, total=None, membros=None):
    """Barras horizontais [(nome, valor)]; com total, o valor é mostrado também como % do total.

    membros = {nome: [[id, detalhe]]}: as samples de cada barra.
    """
    if not itens:
        return None
    saida = {"tipo": "barras", "unidade": unidade, "casas": casas, "total": total,
             "itens": [{"nome": n, "valor": v} for n, v in itens],
             "tabela": {"cab": ["", unidade or t("count")] + (["%"] if total else []),
                        "linhas": [[n, v] + ([f"{100 * v / total:.1f}"] if total else []) for n, v in itens]}}
    if membros is not None:
        saida["membros"] = [membros.get(n, []) for n, _ in itens]
    return saida


def _filtros_txt(numeros):
    return t("filter {n}", n=numeros[0]) if len(numeros) == 1 else t("filters {lista}", lista=lotes.faixas(numeros))


def _densidade_posicao(m):
    x = dados.numero(m.get("densidade_massa_ug_cm2"))
    return x if x is not None else dados.densidade(m.get("massa_antes"), m.get("massa_depois"))


def _variacao_imersao(r):
    x = dados.numero(r.get("diferenca_pct"))
    if x is not None:
        return x
    a, d = dados.numero(r.get("massa_antes")), dados.numero(r.get("massa_depois"))
    return (d - a) * 100 / a if a and d is not None else None


def _origem_posicoes(d, gravada):
    """{posição: (tipo, código do lote interno)}: o único lote vale para todas; com vários, o que a janela gravou."""
    if len(d["lotes"]) == 1:
        l = d["lotes"][0]
        return {n: (l["tipo"], l["interno"]) for n in range(1, dados.N_FILTROS + 1)}
    return dict(gravada) if d["lotes"] else {}


def ler_amostras():
    """Todas as samples, já com os estados calculados (as mesmas regras da lista)."""
    conn = db.conectar()
    try:
        internos, limpezas = dados.codigos_lotes_internos()
        origem = {}                  # {id: {posição: (tipo, código do lote interno)}} da janela Filter origin
        for r in conn.execute("SELECT id_tarefa, filtro, tipo_lote, lote_interno_id, codigo_lote_interno FROM filtro_origem"):
            tipo = r["tipo_lote"] or "opto"
            codigo = (limpezas if tipo == "limpeza" else internos).get(r["lote_interno_id"]) or r["codigo_lote_interno"] or ""
            origem.setdefault(r["id_tarefa"], {})[r["filtro"]] = (tipo, codigo)
        saida = []
        for d in dados.dados_tarefas(conn):
            d["status"] = dados.status(d)
            d["estado_imersao"], d["estado_eficiencia"] = dados.estado_imersao(d), dados.estado_eficiencia(d)
            d["decisao"] = dados.decisao_lote(d["estado_imersao"], d["estado_eficiencia"])
            d["numero"] = dados.numero_run(d["cab"].get("run_evaporation"))
            d["data"] = _data(d["tarefa"].get("data_inicio"))
            d["posicoes"] = _origem_posicoes(d, origem.get(d["id"], {}))
            saida.append(d)
        return saida
    finally:
        conn.close()


def _ordem(d):
    """Ordem das samples nas janelas e no CSV: pela run (as sem run no fim), depois pelo id."""
    return d["numero"] == "", int(d["numero"] or 0), d["id"]


def calcular(de=None, ate=None, lote=""):
    """Tudo o que a página mostra, para as samples depositadas entre de e ate (datas) e do OPTO batch escolhido."""
    todas = ler_amostras()
    optos = sorted({l["opto"] for d in todas for l in d["lotes"] if l["opto"]})
    sel = [d for d in todas
           if (not de or (d["data"] and d["data"] >= de)) and (not ate or (d["data"] and d["data"] <= ate))
           and (not lote or any(l["opto"] == lote for l in d["lotes"]))]
    sem_data = sum(1 for d in sel if not d["data"])
    sel = sorted(sel, key=_ordem)

    # ---- deposição: densidade de massa por posição, uniformidade e evolução por run
    dens = {p: [] for p in dados.POSICOES}
    refs_dens = {p: [] for p in dados.POSICOES}
    por_run, razoes, refs_razoes = [], [], []
    for d in sel:
        linha = {}
        for p in dados.POSICOES:
            x = _densidade_posicao(d["massas"].get(p) or {})
            if x is not None:
                dens[p].append(x)
                refs_dens[p].append((d["id"], f"{x:.1f} µg/cm²"))
                linha[p] = x
        if linha.get(2) and 14 in linha:
            razoes.append(linha[14] / linha[2])
            refs_razoes.append((d["id"], f"{linha[14] / linha[2]:.3f}  ({linha[14]:.1f} ÷ {linha[2]:.1f})"))
        if d["numero"] and linha:
            por_run.append((int(d["numero"]), linha, d["id"]))
    por_run.sort(key=lambda r: r[0])
    nome_pos = NOME_POSICAO
    linhas = None
    if por_run:
        linhas = {"tipo": "linhas", "unidade": "µg/cm²", "x": [r for r, _, _ in por_run],
                  "series": [{"nome": nome_pos[p], "cor": COR_POSICAO[p], "valores": [l.get(p) for _, l, _ in por_run]}
                             for p in dados.POSICOES],
                  "tabela": {"cab": ["Run"] + [nome_pos[p] for p in dados.POSICOES],
                             "linhas": [[r] + [_fmt(l.get(p), 1) for p in dados.POSICOES] for r, l, _ in por_run]},
                  "membros": [[[i, " · ".join(f"P{p:02d} {_fmt(l.get(p), 1)}" for p in dados.POSICOES)]]
                              for _, l, i in por_run]}

    # ---- inspeção visual: classificação e defeitos (filtros com a linha preenchida)
    classes = {"A": 0, "B": 0, "C": 0}
    defeitos = {nome: 0 for nome in ("Visual: Fail", "Uniformity: Minor", "Uniformity: Major", "Stains",
                                     "Particles", "Edge", "Finger", "Other")}
    inspecionados = 0
    filtros_de = {}                       # (barra, id) -> números dos filtros: os membros de cada barra
    def conta(barra, d, n):
        filtros_de.setdefault((barra, d["id"]), []).append(n)
    for d in sel:
        for n, f in sorted(d["filtros"].items()):
            if f.get("classification") in classes:
                classes[f["classification"]] += 1
                conta(f["classification"], d, n)
            if not f.get("visual_status"):
                continue
            inspecionados += 1
            achados = [("Visual: Fail", f.get("visual_status") == "Fail"), ("Uniformity: Minor", f.get("uniformity") == "Minor"),
                       ("Uniformity: Major", f.get("uniformity") == "Major")]
            achados += [(nome, f.get(col) == "Yes") for col, nome in (
                ("stains", "Stains"), ("particles", "Particles"), ("edge_defects", "Edge"),
                ("finger_defects", "Finger"), ("other_defects", "Other"))]
            for nome, sim in achados:
                defeitos[nome] += sim
                if sim:
                    conta(nome, d, n)
    n_classes = sum(classes.values())
    membros_filtros = {}
    for (barra, i), ns in filtros_de.items():           # sel já está na ordem das runs
        membros_filtros.setdefault(barra, []).append([i, _filtros_txt(ns)])
    membros_classes = {f"{k} → {acao}": membros_filtros.get(k, []) for k, acao in CLASSES}

    # ---- imersão criogênica e eficiência óptica (amostras P02/P03/P14)
    var_im, refs_im = [], []
    for d in sel:
        for a in dados.AMOSTRAS:
            if (x := _variacao_imersao(d["im_massas"].get(a) or {})) is not None:
                var_im.append(x)
                refs_im.append((d["id"], f"{a} · {x:+.2f} %"))
    efs, dens_ef, refs_efs, refs_dens_ef = [], [], [], []
    for d in sel:
        for a in dados.AMOSTRAS:
            r = d["ef_amostras"].get(a) or {}
            if r.get("testada") != "Yes":
                continue
            if (x := dados.numero(r.get("eficiencia"))) is not None:
                efs.append(x)
                refs_efs.append((d["id"], f"{a} · {x:.3f}"))
            if (x := dados.numero(r.get("densidade_ug_cm2"))) is not None:
                dens_ef.append(x)
                refs_dens_ef.append((d["id"], f"{a} · {x:.1f} µg/cm²"))
    itens_im = [v for d in sel for v in d["im_itens"].values() if v in ("Yes", "No")]

    # ---- batches: samples por internal lot e filtros recebidos
    por_interno, membros_internos = {}, {}
    for d in sel:
        for l in d["lotes"]:
            nome = l["interno"] or l["opto"] or "?"
            por_interno[nome] = por_interno.get(nome, 0) + 1
            membros_internos.setdefault(nome, []).append([d["id"], f"OPTO batch {l['opto']}" if l["opto"] else ""])
    lotes_reg = [l for l in chegada.listar() if not lote or l.get("lote_geral") == lote]
    recebidos = sum(int(x) for l in lotes_reg if str(x := l.get("total_filtros") or "").isdigit())

    limpeza = _secao_limpeza(todas, sel)

    lim = dados.LIMITE_PERDA_PCT
    e = {
        "sel": sel, "optos": optos, "limpeza": limpeza["numeros"], "n_total": len(todas), "n": len(sel), "sem_data": sem_data,
        "status": {s: sum(1 for d in sel if d["status"] == s) for s in dados.STATUS_TODOS},
        "decisao": {k: sum(1 for d in sel if d["decisao"] == k) for k in ("Approved", "Rejected", "Pending")},
        "filtros_dep": len(sel) * dados.N_FILTROS, "filtros_rec": recebidos, "n_lotes": len(lotes_reg),
        "centro": _resumo_num(dens[2]),
        "inspecionados": inspecionados, "classes": classes, "n_classes": n_classes,
        "itens_im": {"Yes": itens_im.count("Yes"), "No": itens_im.count("No")},
        "ef_ok": sum(1 for x in efs if round(x, 6) >= dados.LIMITE_EFICIENCIA), "n_ef": len(efs),
        "graficos": {
            "periodo": por_periodo([d["data"] for d in sel if d["data"]], [d["id"] for d in sel if d["data"]]),
            # um histograma por posição, cada um com as suas faixas (as médias são bem diferentes)
            **{f"densidade_{p}": histograma([(nome_pos[p], COR_POSICAO[p], dens[p])], "µg/cm²", 1, n_alvo=10,
                                            refs=refs_dens[p])
               for p in dados.POSICOES},
            "por_run": linhas,
            "uniformidade": histograma([(t("External ÷ Center"), 1, razoes)], t("ratio"), 3, n_alvo=10, refs=refs_razoes),
            "classes": barras([(f"{k} → {acao}", classes[k]) for k, acao in CLASSES], t("filters"), total=n_classes,
                              membros=membros_classes) if n_classes else None,
            "defeitos": barras(list(defeitos.items()), t("filters"), total=inspecionados, membros=membros_filtros)
                        if inspecionados else None,
            "imersao": histograma([(t("Mass change"), 1, var_im)], "%", 2,
                                  [(-lim, f"−{lim:g} %"), (lim, f"+{lim:g} %")] if var_im else (), n_alvo=10,
                                  estender=False, refs=refs_im),
            "eficiencia": histograma([(t("Relative efficiency"), 1, efs)], t("relative efficiency"), 3,
                                     [(dados.LIMITE_EFICIENCIA, t("limit {x}", x=dados.LIMITE_EFICIENCIA))] if efs else (),
                                     n_alvo=10, refs=refs_efs),
            "dens_ef": histograma([(t("Witness sample density"), 1, dens_ef)], "µg/cm²", 1, n_alvo=10, refs=refs_dens_ef),
            "internos": barras(sorted(por_interno.items(), key=lambda kv: -kv[1]), t("samples"), membros=membros_internos),
            **limpeza["graficos"],
        },
    }
    # samples citadas nas janelas (as da seleção e as de origem dos filtros limpos): [run, PID, data, status]
    citadas = {i for g in e["graficos"].values() if g for linha in g.get("membros") or [] for i, _ in linha}
    citadas |= {d["id"] for d in sel}
    e["amostras"] = {d["id"]: [d["numero"] or "", d["tarefa"].get("codigo_tarefa") or "", d["tarefa"].get("data_inicio") or "",
                               d["status"]] for d in todas if d["id"] in citadas}
    return e


# ---------------- filtros retirados e cleaning lots ----------------
SITUACOES = (("descartado", "Discarded"), ("aguardando", "Waiting for cleaning"),
             ("no_lote", "In a cleaning lot, not used yet"), ("reusado", "Reused in a new sample"))
ORIGENS = (("opto", "OPTO internal lots"), ("limpeza", "Leptons cleaning lots"),
           (None, "Several batches, slot not assigned"), ("sem", "No batch recorded"))


def _membros(grupos, ordem):
    """{barra: {id: [nº dos filtros]}} -> {barra: [[id, 'filters 1–3']]} na ordem das samples."""
    pos = {i: k for k, i in enumerate(ordem)}
    return {b: [[i, retirados_txt(ns)] for i, ns in sorted(por.items(), key=lambda kv: pos.get(kv[0], 1e9))]
            for b, por in grupos.items()}


def retirados_txt(ns):
    return t("filter {n}", n=ns[0]) if len(ns) == 1 else t("filters {lista}", lista=lotes.faixas(ns))


def _secao_limpeza(todas, sel):
    """Números e gráficos da seção Removed filters · Cleaning lots.

    Retiradas, destino e origem das posições: das samples da seleção. Cleaning lots: todos (o estoque de hoje)."""
    ids_sel = {d["id"] for d in sel}
    ordem = [d["id"] for d in sel] + [d["id"] for d in todas if d["id"] not in ids_sel]
    todas_ret = retirados._listar()
    rem = [r for r in todas_ret if r["id_tarefa"] in ids_sel]
    chave_rem = {(r["id_tarefa"], r["filtro"]) for r in rem}

    # filtros A / B: retirados ou ainda na sample
    por_classe = {}
    for d in sel:
        for n, f in sorted(d["filtros"].items()):
            c = f.get("classification")
            if c in retirados.CLASSES_RETIRAVEIS:
                barra = f"{c} → " + (t("removed") if (d["id"], n) in chave_rem else t("still in the sample"))
                por_classe.setdefault(barra, {}).setdefault(d["id"], []).append(n)
    barras_classe = [f"{c} → {t(x)}" for c in retirados.CLASSES_RETIRAVEIS for x in ("removed", "still in the sample")]
    n_ab = sum(len(ns) for por in por_classe.values() for ns in por.values())

    # destino dos retirados
    por_destino = {}
    for r in rem:
        por_destino.setdefault(t(dict(SITUACOES)[r["situacao"]]), {}).setdefault(r["id_tarefa"], []).append(r["filtro"])
    situacoes = {s: sum(1 for r in rem if r["situacao"] == s) for s, _ in SITUACOES}

    # de onde veio cada posição depositada
    por_origem = {}
    nome_origem = {tipo: t(nome) for tipo, nome in ORIGENS}
    for d in sel:
        for n in range(1, dados.N_FILTROS + 1):
            tipo = (d["posicoes"].get(n) or (None,))[0] if d["lotes"] else "sem"
            nome = nome_origem.get(tipo, nome_origem[None])
            por_origem.setdefault(nome, {}).setdefault(d["id"], []).append(n)
    n_limpeza = sum(len(ns) for ns in por_origem.get(nome_origem["limpeza"], {}).values())
    rastreados = sum(1 for r in todas_ret if r["usado_tarefa_id"] in ids_sel)

    # cleaning lots (todos): posições usadas em samples, tamanho do lote, filtros retirados controlados
    usados_lote = {}
    for d in todas:
        for n, (tipo, cod) in d["posicoes"].items():
            if tipo == "limpeza":
                usados_lote.setdefault(cod, {}).setdefault(d["id"], []).append(n)
    controlados = retirados.por_limpeza()
    itens_lote, linhas_lote = [], []
    for l in sorted(lotes.limpezas(), key=lambda l: l["codigo"] or ""):
        cod = l["codigo"] or "?"
        usados = sum(len(ns) for ns in usados_lote.get(cod, {}).values())
        tamanho = lotes.inteiro(l["filtros"])
        ctl = controlados.get(l["id"], [])
        itens_lote.append((cod, usados))
        linhas_lote.append([cod, usados, "" if tamanho is None else tamanho,
                            "" if tamanho is None else tamanho - usados, len(ctl),          # negativo: usaram mais do que o lote tinha
                            sum(1 for r in ctl if r["situacao"] == "no_lote")])
    g_lotes = None
    if itens_lote:
        g_lotes = barras(itens_lote, t("filters used"), membros=_membros(usados_lote, ordem))
        g_lotes["tabela"] = {"cab": ["", t("used in samples"), t("filters in the lot"), t("left"), t("removed filters recorded"),
                                     t("recorded, not used yet")], "linhas": linhas_lote}

    graficos = {
        "retirada_classe": barras([(b, sum(len(ns) for ns in por_classe.get(b, {}).values())) for b in barras_classe],
                                  t("filters"), total=n_ab, membros=_membros(por_classe, ordem)) if n_ab else None,
        "destino": barras([(t(nome), situacoes[s]) for s, nome in SITUACOES], t("filters"), total=len(rem),
                          membros=_membros(por_destino, ordem)) if rem else None,
        "retirados_periodo": por_periodo([_data(r["data_hora"]) for r in rem if _data(r["data_hora"])],
                                         [r["id_tarefa"] for r in rem if _data(r["data_hora"])], "Filters removed"),
        "origem_filtros": barras([(nome_origem[tipo], sum(len(ns) for ns in por_origem.get(nome_origem[tipo], {}).values()))
                                  for tipo, _ in ORIGENS], t("filters"), total=len(sel) * dados.N_FILTROS,
                                 membros=_membros(por_origem, ordem)) if sel else None,
        "lotes_limpeza": g_lotes,
    }
    aguardando = sum(1 for r in todas_ret if r["situacao"] == "aguardando")
    disponiveis = sum(1 for r in todas_ret if r["situacao"] == "no_lote")
    return {"graficos": graficos, "numeros": {
        "removidos": len(rem), "n_ab": n_ab, "situacoes": situacoes, "n_limpeza": n_limpeza, "rastreados": rastreados,
        "aguardando": aguardando, "disponiveis": disponiveis, "n_lotes": len(itens_lote)}}


# =====================================================================
# EXPORTAÇÃO CSV (janela Export CSV): os números de cada gráfico, o resumo e os dados de cada sample
# =====================================================================
# (grupo, chave, nome do arquivo, título): a ordem é a da janela e a dos arquivos no .zip
ITENS_CSV = [
    ("General", "resumo", "summary", "Summary"),
    ("General", "descritiva", "descriptive_statistics", "Descriptive statistics (n, mean, s.d., min, max)"),
    ("General", "amostras", "data_per_sample", "Data per sample (one row per sample)"),
    ("General", "periodo", "samples_per_period", "Samples deposited per week / month"),
    ("Deposition · Mass control", "densidade_2", "mass_density_center_p02", "Mass density · Center (P02) – histogram"),
    ("Deposition · Mass control", "densidade_3", "mass_density_middle_p03", "Mass density · Middle (P03) – histogram"),
    ("Deposition · Mass control", "densidade_14", "mass_density_external_p14", "Mass density · External (P14) – histogram"),
    ("Deposition · Mass control", "por_run", "mass_density_per_run", "Mass density per run"),
    ("Deposition · Mass control", "uniformidade", "radial_uniformity", "Radial uniformity – histogram"),
    ("Deposition · Mass control", "internos", "samples_per_internal_lot", "Samples per internal lot"),
    ("Visual inspection", "classes", "visual_classification", "Classification"),
    ("Visual inspection", "defeitos", "visual_defects", "Defects found"),
    ("Cryogenic immersion · Optical efficiency", "imersao", "immersion_mass_change", "Mass change after immersion – histogram"),
    ("Cryogenic immersion · Optical efficiency", "eficiencia", "relative_efficiency", "Relative efficiency – histogram"),
    ("Cryogenic immersion · Optical efficiency", "dens_ef", "witness_sample_density", "Witness sample density – histogram"),
    ("Removed filters · Cleaning lots", "retirada_classe", "filters_a_b_removed", "Filters classified A or B – removed or still in the sample"),
    ("Removed filters · Cleaning lots", "destino", "removed_filters_destination", "Removed filters – destination"),
    ("Removed filters · Cleaning lots", "retirados_periodo", "filters_removed_per_period", "Filters removed per week / month"),
    ("Removed filters · Cleaning lots", "origem_filtros", "deposited_filters_origin", "Deposited filters – origin (OPTO / cleaning lots)"),
    ("Removed filters · Cleaning lots", "lotes_limpeza", "cleaning_lots_usage", "Cleaning lots – filters used, left and recorded"),
]
CHAVES_CSV = [i[1] for i in ITENS_CSV]


def grupos_csv(e):
    """Itens da janela por grupo: [(grupo, [(chave, título, tem dados)])]."""
    grupos = {}
    for grupo, chave, _arq, titulo in ITENS_CSV:
        tem = e["n"] > 0 if chave in ("resumo", "descritiva", "amostras") else bool(e["graficos"].get(chave))
        grupos.setdefault(grupo, []).append((chave, titulo, tem))
    return list(grupos.items())


def _num(x, casas=4):
    return "" if x is None else round(x, casas)


def _por_amostra(d):
    """Uma linha do CSV 'Data per sample'."""
    t_, dens_ = d["tarefa"], {p: _densidade_posicao(d["massas"].get(p) or {}) for p in dados.POSICOES}
    _, classes, _ = dados.resumo_visual(d)
    linha = [d["id"], d["numero"], t_.get("codigo_tarefa") or "", t_.get("data_inicio") or "", t_.get("responsavel") or "",
             "; ".join(dict.fromkeys(l["opto"] for l in d["lotes"] if l["opto"])),
             "; ".join(l["interno"] for l in d["lotes"] if l["interno"]),
             d["status"], d["decisao"], dados.TXT_ESTADO[d["estado_imersao"]], dados.TXT_ESTADO[d["estado_eficiencia"]]]
    linha += [_num(dens_[p], 2) for p in dados.POSICOES]
    linha.append(_num(dens_[14] / dens_[2]) if dens_[2] and dens_[14] is not None else "")
    linha += [classes[k] for k in "ABC"]
    linha += [_num(_variacao_imersao(d["im_massas"].get(a) or {}), 3) for a in dados.AMOSTRAS]
    for campo in ("eficiencia", "densidade_ug_cm2"):
        for a in dados.AMOSTRAS:
            r = d["ef_amostras"].get(a) or {}
            linha.append(_num(dados.numero(r.get(campo)), 3) if r.get("testada") == "Yes" else "")
    return linha


def tabela_csv(e, chave):
    """(cabeçalho, linhas) do item; None se o item não tem dados nesta seleção."""
    if chave == "resumo":
        linhas = [["Samples", e["n"]], ["Samples without a deposition date", e["sem_data"]],
                  ["Filters deposited", e["filtros_dep"]]]
        linhas += [[f"Status: {s}", n] for s, n in e["status"].items()]
        linhas += [[f"Batch decision: {k}", n] for k, n in e["decisao"].items()]
        linhas += [["Filters inspected (visual)", e["inspecionados"]]]
        linhas += [[f"Filters classified {k}", n] for k, n in e["classes"].items()]
        linhas += [["Post-immersion checks: Yes", e["itens_im"]["Yes"]], ["Post-immersion checks: No", e["itens_im"]["No"]],
                   ["Optical efficiency measurements", e["n_ef"]],
                   [f"Optical efficiency measurements >= {dados.LIMITE_EFICIENCIA}", e["ef_ok"]],
                   ["OPTO batches", e["n_lotes"]], ["Filters received (OPTO batches)", e["filtros_rec"]]]
        return ["Item", "Value"], linhas
    if chave == "descritiva":
        linhas = []
        for c in CHAVES_CSV:
            g = e["graficos"].get(c)
            if g and g["tipo"] == "histograma":
                for s in g["series"]:
                    linhas.append([s["nome"], g["unidade"], s["n"]] + [_num(s.get(k)) for k in ("media", "dp", "min", "max")])
        return (["Quantity", "Unit", "n", "Mean", "S.D.", "Min", "Max"], linhas) if linhas else None
    if chave == "amostras":
        if not e["sel"]:
            return None
        cab = ["Record ID", "Run", "PID", "Deposition date", "Responsible", "OPTO batch", "Internal lot", "Status",
               "Batch decision", "Cryogenic immersion", "Optical efficiency"]
        cab += [f"Mass density {NOME_POSICAO[p]} (µg/cm²)" for p in dados.POSICOES]
        cab += ["External ÷ Center", "Filters A", "Filters B", "Filters C"]
        cab += [f"Immersion mass change {a} (%)" for a in dados.AMOSTRAS]
        cab += [f"Relative efficiency {a}" for a in dados.AMOSTRAS]
        cab += [f"Witness sample density {a} (µg/cm²)" for a in dados.AMOSTRAS]
        return cab, [_por_amostra(d) for d in e["sel"]]
    g = e["graficos"].get(chave)
    if not g:
        return None
    if g["tipo"] == "histograma":
        b = g["bordas"]
        return ([f"From ({g['unidade']})", f"To ({g['unidade']})"] + [s["nome"] for s in g["series"]],
                [[_num(b[i], 6), _num(b[i + 1], 6)] + [s["contagens"][i] for s in g["series"]] for i in range(len(b) - 1)])
    if g["tipo"] == "colunas":
        return ["Month" if g["mensal"] else "Week of", g.get("conta", "Samples")], g["tabela"]["linhas"]
    if g["tipo"] == "linhas":
        return (["Run"] + [f"{s['nome']} ({g['unidade']})" for s in g["series"]],
                [[x] + [_num(s["valores"][i], 2) for s in g["series"]] for i, x in enumerate(g["x"])])
    return g["tabela"]["cab"], g["tabela"]["linhas"]           # barras


def _csv(cab, linhas):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cab)
    w.writerows(linhas)
    return buf.getvalue()


def exportar(e, chaves, um_arquivo, selecao):
    """(conteúdo, nome do arquivo, tipo) com os itens escolhidos; None se nenhum tem dados.

    selecao = [(item, valor)] (período, OPTO batch, quem gerou): vai no começo do arquivo único ou em selection.csv.
    Um item só sai sempre como um .csv; vários saem num .zip (um .csv cada) ou num .csv com uma seção por item.
    """
    itens = [(arq, titulo, tab) for _g, chave, arq, titulo in ITENS_CSV
             if chave in chaves and (tab := tabela_csv(e, chave))]
    if not itens:
        return None
    carimbo = datetime.now().strftime("%Y-%m-%d")
    if len(itens) == 1:
        arq, _titulo, (cab, linhas) = itens[0]
        return _csv(cab, linhas).encode("utf-8"), f"statistics_{arq}_{carimbo}.csv", "text/csv"
    if um_arquivo:
        buf = io.StringIO()
        w = csv.writer(buf)
        for titulo, (cab, linhas) in [("Selection", (["Item", "Value"], selecao))] + [(t_, tab) for _a, t_, tab in itens]:
            w.writerow([f"# {titulo}"])
            w.writerow(cab)
            w.writerows(linhas)
            w.writerow([])
        return buf.getvalue().encode("utf-8"), f"statistics_{carimbo}.csv", "text/csv"
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_selection.csv", _csv(["Item", "Value"], selecao))
        for n, (arq, _titulo, (cab, linhas)) in enumerate(itens, 1):
            z.writestr(f"{n:02d}_{arq}.csv", _csv(cab, linhas))
    return mem.getvalue(), f"statistics_{carimbo}.zip", "application/zip"
