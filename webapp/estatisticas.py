"""Aba Statistics: números e histogramas do processo (deposição, inspeção visual, imersão, eficiência, lotes).

Só lê os bancos, com as mesmas regras das outras telas (dados.py). Os histogramas já saem daqui com as faixas
contadas; o estatisticas.js só desenha. Cada gráfico leva também a sua tabela (para ver os números sem o mouse).
"""
import math
import statistics
from datetime import date, timedelta

from . import chegada, dados
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


def _contar(valores, bordas):
    contagens = [0] * (len(bordas) - 1)
    for v in valores:
        i = min(int((v - bordas[0]) // (bordas[1] - bordas[0])), len(contagens) - 1)
        contagens[max(i, 0)] += 1
    return contagens


def _fmt(x, casas):
    return "–" if x is None else f"{x:.{casas}f}"


def histograma(series, unidade, casas=0, limites=(), n_alvo=12, estender=True):
    """series = [(nome, cor, [valores])] com as mesmas faixas; limites = [(valor, rótulo)] (linhas de referência).

    estender: as faixas vão até os limites (False quando eles estão longe dos dados: o gráfico só os mostra se couberem).
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
    return saida


def _semana(d):
    return d - timedelta(days=d.weekday())


def por_periodo(datas):
    """Samples depositadas por semana (até ~6 meses) ou por mês, com os períodos vazios no meio."""
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
    contagem = {}
    for d in datas:
        contagem[chave(d)] = contagem.get(chave(d), 0) + 1
    periodos, p = [], chave(lo)
    while p <= chave(hi):
        periodos.append(p)
        p = passo(p)
    nomes = [rotulo(p) for p in periodos]
    valores = [contagem.get(p, 0) for p in periodos]
    titulo = t("month") if mensal else t("week of")
    return {"tipo": "colunas", "rotulos": nomes, "valores": valores, "mensal": mensal,
            "dicas": [(p.strftime("%Y-%m") if mensal else t("week of {d}", d=p.isoformat())) for p in periodos],
            "tabela": {"cab": [titulo, t("Samples")],
                       "linhas": [[p.strftime("%Y-%m") if mensal else p.isoformat(), v] for p, v in zip(periodos, valores)]}}


def barras(itens, unidade="", casas=0, total=None):
    """Barras horizontais [(nome, valor)]; com total, o valor é mostrado também como % do total."""
    if not itens:
        return None
    return {"tipo": "barras", "unidade": unidade, "casas": casas, "total": total,
            "itens": [{"nome": n, "valor": v} for n, v in itens],
            "tabela": {"cab": ["", unidade or t("count")] + (["%"] if total else []),
                       "linhas": [[n, v] + ([f"{100 * v / total:.1f}"] if total else []) for n, v in itens]}}


def _densidade_posicao(m):
    x = dados.numero(m.get("densidade_massa_ug_cm2"))
    return x if x is not None else dados.densidade(m.get("massa_antes"), m.get("massa_depois"))


def _variacao_imersao(r):
    x = dados.numero(r.get("diferenca_pct"))
    if x is not None:
        return x
    a, d = dados.numero(r.get("massa_antes")), dados.numero(r.get("massa_depois"))
    return (d - a) * 100 / a if a and d is not None else None


def ler_amostras():
    """Todas as samples, já com os estados calculados (as mesmas regras da lista)."""
    conn = dados._conectar(dados.DB_TAREFAS)
    try:
        lotes_ = dados._lotes_por_tarefa(conn)
        saida = []
        for linha in conn.execute("SELECT * FROM tarefas"):
            d = dados._dados_tarefa(conn, dict(linha), lotes_.get(linha["id"], []))
            d["status"] = dados.status(d)
            d["estado_imersao"], d["estado_eficiencia"] = dados.estado_imersao(d), dados.estado_eficiencia(d)
            d["decisao"] = dados.decisao_lote(d["estado_imersao"], d["estado_eficiencia"])
            d["numero"] = dados.numero_run(d["cab"].get("run_evaporation"))
            d["data"] = _data(d["tarefa"].get("data_inicio"))
            saida.append(d)
        return saida
    finally:
        conn.close()


def calcular(de=None, ate=None, lote=""):
    """Tudo o que a página mostra, para as samples depositadas entre de e ate (datas) e do OPTO batch escolhido."""
    todas = ler_amostras()
    optos = sorted({l["opto"] for d in todas for l in d["lotes"] if l["opto"]})
    sel = [d for d in todas
           if (not de or (d["data"] and d["data"] >= de)) and (not ate or (d["data"] and d["data"] <= ate))
           and (not lote or any(l["opto"] == lote for l in d["lotes"]))]
    sem_data = sum(1 for d in sel if not d["data"])

    # ---- deposição: densidade de massa por posição, uniformidade e evolução por run
    dens = {p: [] for p in dados.POSICOES}
    por_run, razoes = [], []
    for d in sel:
        linha = {}
        for p in dados.POSICOES:
            x = _densidade_posicao(d["massas"].get(p) or {})
            if x is not None:
                dens[p].append(x)
                linha[p] = x
        if linha.get(2) and 14 in linha:
            razoes.append(linha[14] / linha[2])
        if d["numero"] and linha:
            por_run.append((int(d["numero"]), linha))
    por_run.sort(key=lambda r: r[0])
    nome_pos = NOME_POSICAO
    linhas = None
    if por_run:
        linhas = {"tipo": "linhas", "unidade": "µg/cm²", "x": [r for r, _ in por_run],
                  "series": [{"nome": nome_pos[p], "cor": COR_POSICAO[p], "valores": [l.get(p) for _, l in por_run]}
                             for p in dados.POSICOES],
                  "tabela": {"cab": ["Run"] + [nome_pos[p] for p in dados.POSICOES],
                             "linhas": [[r] + [_fmt(l.get(p), 1) for p in dados.POSICOES] for r, l in por_run]}}

    # ---- inspeção visual: classificação e defeitos (filtros com a linha preenchida)
    classes = {"A": 0, "B": 0, "C": 0}
    defeitos = {nome: 0 for nome in ("Visual: Fail", "Uniformity: Minor", "Uniformity: Major", "Stains",
                                     "Particles", "Edge", "Finger", "Other")}
    inspecionados = 0
    for d in sel:
        for f in d["filtros"].values():
            if f.get("classification") in classes:
                classes[f["classification"]] += 1
            if not f.get("visual_status"):
                continue
            inspecionados += 1
            defeitos["Visual: Fail"] += f.get("visual_status") == "Fail"
            defeitos["Uniformity: Minor"] += f.get("uniformity") == "Minor"
            defeitos["Uniformity: Major"] += f.get("uniformity") == "Major"
            for col, nome in (("stains", "Stains"), ("particles", "Particles"), ("edge_defects", "Edge"),
                              ("finger_defects", "Finger"), ("other_defects", "Other")):
                defeitos[nome] += f.get(col) == "Yes"
    n_classes = sum(classes.values())

    # ---- imersão criogênica e eficiência óptica (amostras P02/P03/P14)
    var_im = [x for d in sel for a in dados.AMOSTRAS
              if (x := _variacao_imersao(d["im_massas"].get(a) or {})) is not None]
    efs, dens_ef = [], []
    for d in sel:
        for a in dados.AMOSTRAS:
            r = d["ef_amostras"].get(a) or {}
            if r.get("testada") != "Yes":
                continue
            if (x := dados.numero(r.get("eficiencia"))) is not None:
                efs.append(x)
            if (x := dados.numero(r.get("densidade_ug_cm2"))) is not None:
                dens_ef.append(x)
    itens_im = [v for d in sel for v in d["im_itens"].values() if v in ("Yes", "No")]

    # ---- batches: samples por internal lot e filtros recebidos
    por_interno = {}
    for d in sel:
        for l in d["lotes"]:
            nome = l["interno"] or l["opto"] or "?"
            por_interno[nome] = por_interno.get(nome, 0) + 1
    lotes_reg = [l for l in chegada.listar() if not lote or l.get("lote_geral") == lote]
    recebidos = sum(int(x) for l in lotes_reg if str(x := l.get("total_filtros") or "").isdigit())

    lim = dados.LIMITE_PERDA_PCT
    return {
        "optos": optos, "n_total": len(todas), "n": len(sel), "sem_data": sem_data,
        "status": {s: sum(1 for d in sel if d["status"] == s) for s in dados.STATUS_TODOS},
        "decisao": {k: sum(1 for d in sel if d["decisao"] == k) for k in ("Approved", "Rejected", "Pending")},
        "filtros_dep": len(sel) * dados.N_FILTROS, "filtros_rec": recebidos, "n_lotes": len(lotes_reg),
        "centro": _resumo_num(dens[2]),
        "inspecionados": inspecionados, "classes": classes, "n_classes": n_classes,
        "itens_im": {"Yes": itens_im.count("Yes"), "No": itens_im.count("No")},
        "ef_ok": sum(1 for x in efs if round(x, 6) >= dados.LIMITE_EFICIENCIA), "n_ef": len(efs),
        "graficos": {
            "periodo": por_periodo([d["data"] for d in sel if d["data"]]),
            # um histograma por posição, cada um com as suas faixas (as médias são bem diferentes)
            **{f"densidade_{p}": histograma([(nome_pos[p], COR_POSICAO[p], dens[p])], "µg/cm²", 1, n_alvo=10)
               for p in dados.POSICOES},
            "por_run": linhas,
            "uniformidade": histograma([(t("External ÷ Center"), 1, razoes)], t("ratio"), 3, n_alvo=10),
            "classes": barras([(f"{k} → {acao}", classes[k]) for k, acao in CLASSES], t("filters"), total=n_classes)
                       if n_classes else None,
            "defeitos": barras(list(defeitos.items()), t("filters"), total=inspecionados) if inspecionados else None,
            "imersao": histograma([(t("Mass change"), 1, var_im)], "%", 2,
                                  [(-lim, f"−{lim:g} %"), (lim, f"+{lim:g} %")] if var_im else (), n_alvo=10,
                                  estender=False),
            "eficiencia": histograma([(t("Relative efficiency"), 1, efs)], t("relative efficiency"), 3,
                                     [(dados.LIMITE_EFICIENCIA, t("limit {x}", x=dados.LIMITE_EFICIENCIA))] if efs else (),
                                     n_alvo=10),
            "dens_ef": histograma([(t("Witness sample density"), 1, dens_ef)], "µg/cm²", 1, n_alvo=10),
            "internos": barras(sorted(por_interno.items(), key=lambda kv: -kv[1]), t("samples")),
        },
    }
