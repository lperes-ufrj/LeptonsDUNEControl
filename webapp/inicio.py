"""O que roda na tela de entrada (logo animado), logo depois do login.

Hoje só confere se os bancos abrem e conta as amostras. É aqui que entra, no futuro, a sincronização com o
banco de dados (ex.: um servidor central): cada passo devolve um texto curto que a tela mostra.
"""
import sqlite3

from . import dados


def ao_entrar(usuario):
    """Passos feitos ao entrar. Retorna a lista de textos mostrados; levanta exceção se algo impedir o uso."""
    passos = []
    con = dados._conectar(dados.DB_TAREFAS)
    try:
        n = con.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0]
    finally:
        con.close()
    passos.append(f"{n} deposition samples found")
    if dados.DB_LOTES.exists():
        try:
            con = dados._conectar(dados.DB_LOTES)
            try:
                n_lotes = con.execute("SELECT COUNT(*) FROM lotes").fetchone()[0]
            finally:
                con.close()
            passos.append(f"{n_lotes} batch(es) in the batch database")
        except sqlite3.Error:
            passos.append("Batch database not readable")
    else:
        passos.append("Batch database not found")
    # futuro: sincronizar com o banco de dados central aqui
    return passos
