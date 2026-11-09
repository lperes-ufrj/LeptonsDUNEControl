"""O que roda na tela de entrada (logo animado), logo depois do login: confere o banco e conta os registros."""
from . import db
from .i18n import t


def ao_entrar(usuario):
    """Passos feitos ao entrar. Retorna a lista de textos mostrados; levanta exceção se algo impedir o uso."""
    con = db.conectar()
    try:
        n = con.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0]
        n_lotes = con.execute("SELECT COUNT(*) FROM lotes").fetchone()[0]
    finally:
        con.close()
    return [t("{n} deposition samples found", n=n), t("{n} batch(es) in the batch database", n=n_lotes)]
