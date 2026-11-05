"""Aba Projections (só Admin): quando cada etapa chega às 2000 samples a entregar.

Uma sample conta numa etapa quando o trabalho dela está registrado (aprovada ou reprovada), na data da etapa:
  Deposition          massas medidas nas três posições       data da deposição
  Visual inspection   os 28 filtros classificados            data da inspeção
  Cryogenic immersion resultado Approved / Rejected          data do teste
  Optical efficiency  resultado Approved / Rejected          data do teste
A projeção só considera as samples da etapa a partir da 10ª (as primeiras são o começo, mais lento): o ritmo é a
inclinação da reta de mínimos quadrados do total acumulado pela data, só com essas samples; a reta parte do total de
hoje (última data) e vai até a meta. Também o ritmo das últimas 8 semanas.
"""
from datetime import date, datetime, timedelta

from . import dados, estatisticas
from .i18n import t

META = 2000
MINIMO = 10                   # a projeção considera as samples a partir da 10ª da etapa
SEMANAS_RECENTES = 8

ETAPAS = [                    # (chave, nome, cor da série)
    ("deposicao", "Deposition", 1),
    ("visual", "Visual inspection", 2),
    ("imersao", "Cryogenic immersion", 3),
    ("eficiencia", "Optical efficiency", 4),
]


def _data(texto):
    """Data ISO (2026-05-07) ou DD/MM/YYYY; None se não der."""
    s = str(texto or "").strip()
    d = estatisticas._data(s)
    if d:
        return d
    try:
        return datetime.strptime(s[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def _feita(d, chave):
    """(a sample passou pela etapa?, data da etapa)."""
    if chave == "deposicao":
        ok = all(str((d["massas"].get(p) or {}).get(k) or "").strip() for p in dados.POSICOES
                 for k in ("massa_antes", "massa_depois"))
        return ok, _data(d["tarefa"].get("data_inicio"))
    if chave == "visual":
        return dados.resumo_visual(d)[0] == dados.N_FILTROS, _data(d["cab"].get("data_inspecao"))
    if chave == "imersao":
        return d["estado_imersao"] in ("approved", "rejected"), _data(d["tarefa"].get("imersao_data"))
    return d["estado_eficiencia"] in ("approved", "rejected"), _data(d["ef_teste"].get("data_teste"))


def _ritmo(datas):
    """Inclinação (samples/dia) da reta de mínimos quadrados do total acumulado por data; None sem 2 datas diferentes."""
    acumulado, pontos = 0, []
    for d in sorted(set(datas)):
        acumulado += datas.count(d)
        pontos.append((d.toordinal(), acumulado))
    if len(pontos) < 2:
        return None
    mx = sum(x for x, _ in pontos) / len(pontos)
    my = sum(y for _, y in pontos) / len(pontos)
    sxx = sum((x - mx) ** 2 for x, _ in pontos)
    return sum((x - mx) * (y - my) for x, y in pontos) / sxx if sxx else None


def _quando(inicio, n, ritmo):
    """Data em que o total chega à meta, partindo de n em 'inicio' com 'ritmo' samples/dia."""
    if not ritmo or ritmo <= 0:
        return None
    try:
        return inicio + timedelta(days=round((META - n) / ritmo))
    except OverflowError:
        return None


def calcular(hoje=None):
    hoje = hoje or date.today()
    amostras = estatisticas.ler_amostras()
    etapas = []
    for chave, nome, cor in ETAPAS:
        feitas = [dt for d in amostras for ok, dt in [_feita(d, chave)] if ok]
        datas = sorted(x for x in feitas if x)
        n = len(feitas)
        e = {"chave": chave, "nome": nome, "cor": cor, "n": n, "sem_data": n - len(datas), "faltam": max(META - n, 0),
             "pct": min(100.0, 100 * n / META), "primeira": datas[0] if datas else None, "ultima": datas[-1] if datas else None,
             "ritmo": None, "previsao": None, "ritmo_recente": None, "previsao_recente": None, "motivo": "",
             "ajuste_desde": None}
        base = datas[MINIMO - 1:]                 # da 10ª sample (com data) em diante
        corte = hoje - timedelta(weeks=SEMANAS_RECENTES)
        e["recentes"] = sum(1 for x in datas if corte < x <= hoje)
        if n >= META:
            e["motivo"] = t("target reached")
        elif n < MINIMO:
            e["motivo"] = t("projection starts at the {m}th sample ({n} so far)", m=MINIMO, n=n)
        elif len(set(base)) < 2:
            e["motivo"] = t("needs dated samples on at least two different days from the {m}th sample on "
                            "({k} of {n} samples have a date)", m=MINIMO, k=len(datas), n=n)
        else:
            e["ajuste_desde"] = base[0]
            e["ritmo"] = _ritmo(base)
            e["previsao"] = _quando(datas[-1], n, e["ritmo"])
            if not e["previsao"]:
                e["motivo"] = t("no progress over time – cannot project")
        # o ritmo recente vale a partir da 10ª sample, mesmo sem a reta (ex.: datas num dia só)
        if MINIMO <= n < META and e["recentes"]:
            e["ritmo_recente"] = e["recentes"] / (SEMANAS_RECENTES * 7)
            e["previsao_recente"] = _quando(hoje, n, e["ritmo_recente"])
        etapas.append(e)
    return {"etapas": etapas, "hoje": hoje, "meta": META, "minimo": MINIMO, "semanas": SEMANAS_RECENTES,
            "graficos": _graficos(etapas, amostras, hoje)}


def _graficos(etapas, amostras, hoje):
    """Total acumulado de cada etapa (degraus por data) e a reta da projeção até a meta."""
    series = []
    for e in etapas:
        datas = sorted(dt for d in amostras for ok, dt in [_feita(d, e["chave"])] if ok and dt)
        pontos, acumulado = [], 0
        for d in sorted(set(datas)):
            acumulado += datas.count(d)
            pontos.append([d.isoformat(), acumulado])
        proj = ([[e["ultima"].isoformat(), e["n"]], [e["previsao"].isoformat(), META]]
                if e["previsao"] and e["ultima"] else None)
        series.append({"nome": e["nome"], "cor": e["cor"], "pontos": pontos, "projecao": proj})
    todas = [p[0] for s in series for p in s["pontos"]]
    if not todas:
        return None
    fim_proj = max([s["projecao"][1][0] for s in series if s["projecao"]] or [hoje.isoformat()])
    return {"series": series, "hoje": hoje.isoformat(), "meta": META,
            "inicio": min(todas), "fim_real": max(max(todas), hoje.isoformat()), "fim_projecao": max(fim_proj, hoje.isoformat())}
