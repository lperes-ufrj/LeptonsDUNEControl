"""Copia os dados dos bancos SQLite antigos (rastreabilidade.db, lotes.db, usuarios.db) para o MariaDB.

Uso, na pasta do programa e com a configuração do servidor:

    LEPTONS_CONFIG=/etc/leptons/leptons.conf python3 deploy/migrar_sqlite.py /pasta/com/os/arquivos.db

Cria as tabelas que faltam, copia as linhas mantendo os ids e confere as contagens antes de gravar (tudo numa
transação: se algo falhar, nada fica gravado). Só roda com as tabelas do MariaDB vazias, para não misturar dados.
Os bancos SQLite são abertos só para leitura.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webapp import db  # noqa: E402

# tabela do MariaDB -> arquivo SQLite de onde vem
ORIGEM = {
    "tarefas": "rastreabilidade.db", "massa_posicoes": "rastreabilidade.db", "inspecao_visual_cab": "rastreabilidade.db",
    "inspecao_visual_filtros": "rastreabilidade.db", "imersao_massas": "rastreabilidade.db",
    "imersao_itens": "rastreabilidade.db", "tarefa_lotes": "rastreabilidade.db", "filtro_origem": "rastreabilidade.db",
    "eficiencia_teste": "rastreabilidade.db", "eficiencia_amostras": "rastreabilidade.db",
    "filtro_retirado": "rastreabilidade.db", "config_sistema": "rastreabilidade.db",
    "lotes": "lotes.db", "lotes_internos": "lotes.db", "lotes_limpeza": "lotes.db",
    "usuarios": "usuarios.db", "auditoria": "usuarios.db",
}
# config_sistema: só o segredo dos links dos QR codes (os outros valores eram do computador antigo)
CHAVES_CONFIG = ("segredo_qr",)
# lotes de versões antigas: coluna nova vazia recebe o valor da coluna antiga
COLUNAS_ANTIGAS = {"lotes": {"lote_geral": "lote", "data_recebimento": "data", "total_filtros": "quantidade"}}
# arquivos enviados: o banco novo guarda o caminho relativo à pasta de dados do servidor
PASTA_ENVIOS = {("tarefas", "anexos_txt"): "anexos", ("lotes", "arquivo_controle"): "arquivos_lotes"}


def colunas_mariadb(con, tabela):
    """{nome em minúsculas: (nome, tipo)} das colunas da tabela no MariaDB."""
    return {r[0].lower(): (r[0], r[1].lower()) for r in con.execute(
        "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION", (tabela,))}


def valor(v, tipo):
    """Número real numa coluna de texto (ex.: massas gravadas como REAL no SQLite) vira o texto que o programa mostrava."""
    if isinstance(v, float) and tipo in ("text", "varchar"):
        return str(v)
    return v


def caminhos_relativos(texto, pasta, copiar):
    """'C:/.../a.pdf;/home/.../b.xlsx' -> 'anexos/a.pdf;anexos/b.xlsx'; anota o que precisa ser copiado."""
    novos = []
    for c in (texto or "").split(";"):
        c = c.strip()
        if not c:
            continue
        nome = c.replace("\\", "/").rsplit("/", 1)[-1]
        novos.append(f"{pasta}/{nome}")
        copiar.append((c, f"{pasta}/{nome}"))
    return ";".join(novos)


def migrar(pasta_sqlite):
    pasta_sqlite = Path(pasta_sqlite)
    fontes = {}
    for arquivo in sorted(set(ORIGEM.values())):
        caminho = pasta_sqlite / arquivo
        if not caminho.is_file():
            sys.exit(f"Not found: {caminho}")
        fontes[arquivo] = sqlite3.connect(caminho.resolve().as_uri() + "?mode=ro", uri=True)
        fontes[arquivo].row_factory = sqlite3.Row

    db.criar_tabelas()
    con = db.conectar()
    try:
        cheias = [t for t in ORIGEM if con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]]
        if cheias:
            sys.exit("The MariaDB tables already have data (" + ", ".join(cheias) + "). Nothing was copied. "
                     "To migrate again, empty the database first.")

        copiar, avisos, resumo = [], [], []
        for tabela, arquivo in ORIGEM.items():
            src = fontes[arquivo]
            existe = src.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,)).fetchone()
            if not existe:
                resumo.append((tabela, 0, 0))
                continue
            destino = colunas_mariadb(con, tabela)
            origem = [c[1] for c in src.execute(f"PRAGMA table_info({tabela})")]
            comuns = [c for c in origem if c.lower() in destino]
            antigas = COLUNAS_ANTIGAS.get(tabela, {})
            # colunas que não existem mais no banco novo: avisa se alguma tinha dados
            for c in origem:
                if c.lower() not in destino and c.lower() not in antigas.values():
                    n = src.execute(f'SELECT COUNT(*) FROM "{tabela}" WHERE COALESCE("{c}", \'\') <> \'\'').fetchone()[0]
                    if n:
                        avisos.append(f"{tabela}.{c}: {n} filled value(s) not copied (column no longer used)")

            linhas = src.execute(f'SELECT * FROM "{tabela}"').fetchall()
            if tabela == "config_sistema":
                linhas = [r for r in linhas if r["chave"] in CHAVES_CONFIG]
            for r in linhas:
                d = {destino[c.lower()][0]: valor(r[c], destino[c.lower()][1]) for c in comuns}
                for nova, antiga in antigas.items():
                    if not str(d.get(nova) or "").strip() and antiga in {c.lower() for c in origem}:
                        d[nova] = next(r[c] for c in origem if c.lower() == antiga)
                for (tab, col), pasta in PASTA_ENVIOS.items():
                    if tab == tabela and d.get(col):
                        d[col] = caminhos_relativos(d[col], pasta, copiar)
                con.execute(f"INSERT INTO {tabela} ({', '.join(d)}) VALUES ({', '.join('?' * len(d))})",
                            tuple(d.values()))
            gravadas = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
            if gravadas != len(linhas):
                raise RuntimeError(f"{tabela}: {len(linhas)} rows read, {gravadas} written")
            resumo.append((tabela, len(linhas), gravadas))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
        for f in fontes.values():
            f.close()

    print(f"{'table':<26}{'SQLite':>8}{'MariaDB':>9}")
    for tabela, lidas, gravadas in resumo:
        print(f"{tabela:<26}{lidas:>8}{gravadas:>9}")
    for a in avisos:
        print("Warning:", a)
    if copiar:
        print("\nCopy these files into the data folder (data_dir in the configuration):")
        for antigo, novo in copiar:
            print(f"  {antigo}  ->  {novo}")
    print("\nDone: all rows copied.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("pasta", help="folder with rastreabilidade.db, lotes.db and usuarios.db")
    migrar(p.parse_args().pasta)
