"""Backup dos bancos (semanal ao abrir o programa, ou na hora pelo botão Backup now), com cópia em Excel."""
import os
import re
import sqlite3
from datetime import datetime

from . import dados

PASTA_BACKUP = str(dados.PASTA / "backups")     # onde ficam as cópias (ao lado dos bancos)
DIAS_ENTRE_BACKUPS = 7          # intervalo mínimo entre backups
BACKUPS_MANTIDOS = 30           # quantas cópias de cada banco manter (as mais antigas são removidas)
BANCOS_BACKUP = tuple(str(dados.PASTA / n) for n in ("lotes.db", "rastreabilidade.db", "usuarios.db"))


def _exportar_xlsx(banco, caminho):
    """Grava todas as tabelas de um banco SQLite em uma planilha .xlsx (uma aba por tabela)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    ilegais = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

    def limpo(v):
        if isinstance(v, (bytes, bytearray)):
            return "<binary>"
        if isinstance(v, str):
            return ilegais.sub("", v)[:32000]
        return v

    con = sqlite3.connect(banco)
    try:
        wb = Workbook()
        wb.remove(wb.active)
        tabelas = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for nome in tabelas:
            ws = wb.create_sheet(nome[:31])
            cur = con.execute('SELECT * FROM "' + nome + '"')
            ws.append([d[0] for d in cur.description])
            for linha in cur:
                ws.append([limpo(v) for v in linha])
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="2E6F95")
            ws.freeze_panes = "A2"
            for i, col in enumerate(ws.columns, 1):
                larg = max((len(str(c.value)) for c in list(col)[:200] if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(i)].width = min(max(larg + 2, 8), 50)
        if not wb.sheetnames:
            wb.create_sheet("empty")
        wb.save(caminho)
    finally:
        con.close()


def _datas_backups(prefixo):
    """Arquivos de backup existentes de um banco, do mais recente para o mais antigo."""
    if not os.path.isdir(PASTA_BACKUP):
        return []
    achados = [os.path.join(PASTA_BACKUP, n) for n in os.listdir(PASTA_BACKUP)
               if n.startswith(prefixo + "_") and n.endswith(".db")]
    return sorted(achados, key=os.path.getmtime, reverse=True)


def fazer_backup(forcar=False):
    """Copia cada banco para PASTA_BACKUP se o último backup tem mais de DIAS_ENTRE_BACKUPS dias.

    Usa a API de backup do SQLite (cópia consistente mesmo com o programa aberto) e confere a
    cópia com PRAGMA integrity_check. Retorna (lista_de_arquivos_criados, lista_de_erros).
    """
    criados, erros = [], []
    agora = datetime.now()
    for banco in BANCOS_BACKUP:
        if not os.path.exists(banco):
            continue
        prefixo = os.path.splitext(os.path.basename(banco))[0]
        existentes = _datas_backups(prefixo)
        if existentes and not forcar:
            idade = (agora.timestamp() - os.path.getmtime(existentes[0])) / 86400
            if idade < DIAS_ENTRE_BACKUPS:
                continue
        destino = os.path.join(PASTA_BACKUP, prefixo + "_" + agora.strftime("%Y-%m-%d_%H%M%S") + ".db")
        origem = destino_con = None
        try:
            os.makedirs(PASTA_BACKUP, exist_ok=True)
            origem = sqlite3.connect(banco)
            destino_con = sqlite3.connect(destino)
            origem.backup(destino_con)
            ok = destino_con.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise RuntimeError("integrity_check: " + str(ok))
            criados.append(destino)
        except Exception as e:
            erros.append(os.path.basename(banco) + ": " + str(e))
            try:
                if destino_con is not None:
                    destino_con.close()
                    destino_con = None
                if os.path.exists(destino):
                    os.remove(destino)
            except Exception:
                pass
        finally:
            for c in (origem, destino_con):
                try:
                    if c is not None:
                        c.close()
                except Exception:
                    pass
        if criados and criados[-1] == destino and prefixo != "usuarios":   # a planilha não inclui senhas
            try:
                _exportar_xlsx(destino, destino[:-3] + ".xlsx")
            except ImportError:
                erros.append("Excel copy not created: install the openpyxl package (python -m pip install openpyxl)")
            except Exception as e:
                erros.append(os.path.basename(banco) + " (Excel): " + str(e))
        for antigo in _datas_backups(prefixo)[BACKUPS_MANTIDOS:]:
            for arq in (antigo, antigo[:-3] + ".xlsx"):
                try:
                    if os.path.exists(arq):
                        os.remove(arq)
                except Exception:
                    pass
    return criados, erros
