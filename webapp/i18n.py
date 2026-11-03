"""Telas em inglês ou português (botões EN | PT ao lado do nome do usuário).

O texto em inglês é a chave: t("Sample saved.") devolve a tradução em PT, ou o próprio inglês se faltar. Os
termos técnicos (sample, batch, OPTO batch, internal lot, run, PID, Final QA sign-off, PTP, os nomes dos testes,
os status e os resultados Approved/Rejected) ficam em inglês, como nos relatórios e PDFs, que não são traduzidos.
O idioma fica num cookie do navegador, então vale também na tela de login.
"""
import re

from flask import g, has_request_context, request
from markupsafe import Markup, escape

from .textos_pt import PADROES, PT, PT_JS

IDIOMAS = ("en", "pt")
COOKIE = "idioma"


def idioma():
    """'pt' ou 'en' (padrão), conforme o cookie; fora de uma página (servidor do QR code, PDFs) é sempre 'en'.

    g.so_ingles = True força o inglês numa página (ex.: os CSV das estatísticas, em inglês como os relatórios).
    """
    if has_request_context() and not g.get("so_ingles") and request.cookies.get(COOKIE) in IDIOMAS:
        return request.cookies[COOKIE]
    return "en"


def _traduzido(texto):
    if idioma() != "pt":
        return texto
    if texto in PT:
        return PT[texto]
    # mensagens montadas fora daqui (ex.: as do leptons_auth, com números no meio)
    for padrao, modelo in PADROES:
        m = re.fullmatch(padrao, texto)
        if m:
            return m.expand(modelo)
    return texto


def t(texto, **kw):
    """Texto no idioma da tela; {nome} recebe os valores de kw (mensagens, flash, validação)."""
    texto = _traduzido(texto)
    return texto.format(**kw) if kw else texto


def tj(texto, **kw):
    """_() dos templates, só para textos fixos: a tradução pode ter HTML (<b>); os valores de kw são escapados."""
    texto = Markup(_traduzido(texto))
    return texto.format(**kw) if kw else texto


def tr(valor):
    """Filtro |tr para valores vindos do banco ou das listas (Yes/No, In progress…): escapado, traduzido se houver."""
    return escape(_traduzido(str(valor))) if valor is not None else ""


def textos_js():
    """Traduções usadas pelo JavaScript (window.TXT_PT); vazio em inglês."""
    return PT_JS if idioma() == "pt" else {}
