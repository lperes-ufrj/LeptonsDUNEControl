"""Usuários, senhas e registro de auditoria.

Senhas guardadas com PBKDF2-SHA256 (sal próprio por usuário); 5 tentativas erradas seguidas bloqueiam a conta por
5 minutos. Toda ação registrada vai para a tabela auditoria (página Audit, só Admin).
"""
import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta

from . import db

log = logging.getLogger(__name__)
PROGRAMA = "Deposition Control (browser)"     # coluna "programa" da auditoria
PERFIS = ("Admin", "Operator")
ITERACOES = 600_000          # custo do PBKDF2 (dificulta adivinhar senhas se o banco vazar)
MIN_SENHA = 8
MAX_FALHAS = 5               # tentativas erradas seguidas antes de bloquear
BLOQUEIO_MIN = 5             # minutos de bloqueio


def _agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def registrar_como(u, acao, detalhe=""):
    """Grava uma linha na auditoria em nome do usuário u (dict com username e nome). Uma falha aqui não desfaz nem
    interrompe a ação já feita: vai para o log do servidor."""
    try:
        con = db.conectar()
        try:
            con.execute("INSERT INTO auditoria (quando, usuario, nome, programa, acao, detalhe) VALUES (?, ?, ?, ?, ?, ?)",
                        (_agora(), u.get("username") or "", u.get("nome") or "", PROGRAMA, acao, str(detalhe)))
            con.commit()
        finally:
            con.close()
    except Exception:
        log.exception("audit log not written: %s %s", acao, detalhe)


def linhas_auditoria(termo=""):
    """As 2000 linhas mais recentes da auditoria que contêm o termo: (quando, usuário, programa, ação, detalhe)."""
    t = "%" + termo + "%"
    con = db.conectar()
    try:
        return con.execute(
            "SELECT quando, usuario, programa, acao, detalhe FROM auditoria "
            "WHERE usuario LIKE ? OR programa LIKE ? OR acao LIKE ? OR detalhe LIKE ? OR quando LIKE ? "
            "ORDER BY id DESC LIMIT 2000", (t, t, t, t, t)).fetchall()
    finally:
        con.close()


def _hash(senha, salt_hex, iteracoes):
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(salt_hex), iteracoes).hex()


def validar_senha(senha, username=""):
    if len(senha) < MIN_SENHA:
        return f"The password must have at least {MIN_SENHA} characters."
    if username and senha.lower() == username.lower():
        return "The password cannot be the same as the username."
    return None


def validar_username(username):
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,30}", username or ""):
        return "Username: 3 to 30 characters (letters, numbers, dot, dash or underscore)."
    return None


def _contar_admins_ativos(con, ignorar_id=None):
    sql = "SELECT COUNT(*) FROM usuarios WHERE perfil = 'Admin' AND ativo = 1"
    args = ()
    if ignorar_id is not None:
        sql += " AND id <> ?"
        args = (ignorar_id,)
    return con.execute(sql, args).fetchone()[0]


def contar_usuarios():
    con = db.conectar()
    try:
        return con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    finally:
        con.close()


def criar_usuario(username, nome, perfil, senha, trocar_senha=True):
    username = (username or "").strip()
    nome = (nome or "").strip()
    erro = validar_username(username) or validar_senha(senha, username)
    if erro:
        raise ValueError(erro)
    if not nome:
        raise ValueError("Enter the full name.")
    if perfil not in PERFIS:
        raise ValueError("Invalid role.")
    salt = secrets.token_hex(16)
    con = db.conectar()
    try:
        con.execute("INSERT INTO usuarios (username, nome, perfil, senha_hash, salt, iteracoes, trocar_senha, criado_em) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (username, nome, perfil, _hash(senha, salt, ITERACOES), salt, ITERACOES,
                     1 if trocar_senha else 0, _agora()))
        con.commit()
    except db.ErroIntegridade:
        raise ValueError("This username already exists.")
    finally:
        con.close()


def autenticar(username, senha):
    """Retorna (ok, mensagem, usuário como dict ou None)."""
    con = db.conectar()
    try:
        u = con.execute("SELECT * FROM usuarios WHERE username = ?", ((username or "").strip(),)).fetchone()
        if u is None or not u["ativo"]:
            # gasta o mesmo tempo de uma verificação real (não revela se o usuário existe)
            _hash(senha or "", "00" * 16, ITERACOES)
            return False, "Invalid username or password.", None
        agora = datetime.now()
        if u["bloqueado_ate"]:
            ate = datetime.strptime(u["bloqueado_ate"], "%Y-%m-%d %H:%M:%S")
            if ate > agora:
                minutos = int((ate - agora).total_seconds() // 60) + 1
                return False, f"Too many failed attempts. Try again in {minutos} min.", None
        calculado = _hash(senha or "", u["salt"], u["iteracoes"])
        if hmac.compare_digest(calculado, u["senha_hash"]):
            con.execute("UPDATE usuarios SET falhas = 0, bloqueado_ate = NULL, ultimo_login = ? WHERE id = ?",
                        (_agora(), u["id"]))
            con.commit()
            return True, "", dict(u)
        falhas = u["falhas"] + 1
        if falhas >= MAX_FALHAS:
            ate = (agora + timedelta(minutes=BLOQUEIO_MIN)).strftime("%Y-%m-%d %H:%M:%S")
            con.execute("UPDATE usuarios SET falhas = 0, bloqueado_ate = ? WHERE id = ?", (ate, u["id"]))
            msg = f"Too many failed attempts. Account locked for {BLOQUEIO_MIN} min."
        else:
            con.execute("UPDATE usuarios SET falhas = ? WHERE id = ?", (falhas, u["id"]))
            msg = "Invalid username or password."
        con.commit()
        return False, msg, None
    finally:
        con.close()


def definir_senha(user_id, nova_senha, trocar_senha=False, username=""):
    erro = validar_senha(nova_senha, username)
    if erro:
        raise ValueError(erro)
    salt = secrets.token_hex(16)
    con = db.conectar()
    try:
        con.execute("UPDATE usuarios SET senha_hash = ?, salt = ?, iteracoes = ?, trocar_senha = ?, falhas = 0, "
                    "bloqueado_ate = NULL WHERE id = ?",
                    (_hash(nova_senha, salt, ITERACOES), salt, ITERACOES, 1 if trocar_senha else 0, user_id))
        con.commit()
    finally:
        con.close()


def alterar_usuario(user_id, nome=None, perfil=None, ativo=None):
    """Altera nome, perfil ou situação; nunca deixa o sistema sem um Admin ativo."""
    con = db.conectar()
    try:
        u = con.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
        if u is None:
            raise ValueError("User not found.")
        novo_perfil = perfil if perfil is not None else u["perfil"]
        novo_ativo = u["ativo"] if ativo is None else (1 if ativo else 0)
        if novo_perfil not in PERFIS:
            raise ValueError("Invalid role.")
        era_admin_ativo = u["perfil"] == "Admin" and u["ativo"] == 1
        segue_admin_ativo = novo_perfil == "Admin" and novo_ativo == 1
        if era_admin_ativo and not segue_admin_ativo and _contar_admins_ativos(con, user_id) == 0:
            raise ValueError("There must be at least one active Admin.")
        con.execute("UPDATE usuarios SET nome = ?, perfil = ?, ativo = ? WHERE id = ?",
                    ((nome or u["nome"]).strip(), novo_perfil, novo_ativo, user_id))
        con.commit()
    finally:
        con.close()


def listar_usuarios():
    """(id, username, nome, perfil, ativo, último login) de todos os usuários, por username."""
    con = db.conectar()
    try:
        return con.execute("SELECT id, username, nome, perfil, ativo, ultimo_login FROM usuarios "
                           "ORDER BY username").fetchall()
    finally:
        con.close()
