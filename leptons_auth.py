"""Usuários, senhas e registro de auditoria dos programas do laboratório (Leptons Lab).

Módulo compartilhado: os programas de lotes e de deposições usam a mesma lista de usuários,
guardada em "usuarios.db" (na pasta de trabalho dos programas, junto de lotes.db e
rastreabilidade.db).  Deve ficar na MESMA pasta dos dois programas.

Importante (limites): este login controla o uso do programa e registra quem fez o quê; ele não
substitui a proteção do computador. Quem tem acesso direto aos arquivos .db pode ignorá-lo.
"""
import csv
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import sys
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

DB_USUARIOS = "usuarios.db"
PERFIS = ("Admin", "Operator", "Supervisor/QA")
ITERACOES = 600_000          # custo do PBKDF2 (dificulta adivinhar senhas se o arquivo vazar)
MIN_SENHA = 8
MAX_FALHAS = 5               # tentativas erradas seguidas antes de bloquear
BLOQUEIO_MIN = 5             # minutos de bloqueio

usuario_atual = {"id": None, "username": "", "nome": "", "perfil": ""}
_programa = ""
_fundo = "#f4f6f8"


# ---------------------------------------------------------------------------
# BANCO
# ---------------------------------------------------------------------------
def _con():
    con = sqlite3.connect(DB_USUARIOS, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def criar_tabelas():
    con = _con()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                nome TEXT NOT NULL,
                perfil TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                iteracoes INTEGER NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                trocar_senha INTEGER NOT NULL DEFAULT 0,
                falhas INTEGER NOT NULL DEFAULT 0,
                bloqueado_ate TEXT,
                criado_em TEXT,
                ultimo_login TEXT
            )""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quando TEXT NOT NULL,
                usuario TEXT,
                nome TEXT,
                programa TEXT,
                acao TEXT NOT NULL,
                detalhe TEXT
            )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_quando ON auditoria(quando)")
        con.commit()
    finally:
        con.close()


def _agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def registrar(acao, detalhe=""):
    """Grava uma linha na auditoria (nunca interrompe o programa se falhar)."""
    try:
        con = _con()
        try:
            con.execute(
                "INSERT INTO auditoria (quando, usuario, nome, programa, acao, detalhe) VALUES (?,?,?,?,?,?)",
                (_agora(), usuario_atual["username"], usuario_atual["nome"], _programa, acao, str(detalhe)))
            con.commit()
        finally:
            con.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SENHAS E USUÁRIOS (lógica, sem interface)
# ---------------------------------------------------------------------------
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
    sql = "SELECT COUNT(*) FROM usuarios WHERE perfil='Admin' AND ativo=1"
    args = ()
    if ignorar_id is not None:
        sql += " AND id <> ?"
        args = (ignorar_id,)
    return con.execute(sql, args).fetchone()[0]


def contar_usuarios():
    con = _con()
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
    con = _con()
    try:
        try:
            con.execute(
                "INSERT INTO usuarios (username, nome, perfil, senha_hash, salt, iteracoes, trocar_senha, criado_em) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (username, nome, perfil, _hash(senha, salt, ITERACOES), salt, ITERACOES,
                 1 if trocar_senha else 0, _agora()))
            con.commit()
        except sqlite3.IntegrityError:
            raise ValueError("This username already exists.")
    finally:
        con.close()


def autenticar(username, senha):
    """Retorna (ok, mensagem, linha_do_usuario_ou_None)."""
    con = _con()
    con.row_factory = sqlite3.Row
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
            con.execute("UPDATE usuarios SET falhas=0, bloqueado_ate=NULL, ultimo_login=? WHERE id=?",
                        (_agora(), u["id"]))
            con.commit()
            return True, "", dict(u)
        falhas = u["falhas"] + 1
        if falhas >= MAX_FALHAS:
            ate = (agora + timedelta(minutes=BLOQUEIO_MIN)).strftime("%Y-%m-%d %H:%M:%S")
            con.execute("UPDATE usuarios SET falhas=0, bloqueado_ate=? WHERE id=?", (ate, u["id"]))
            msg = f"Too many failed attempts. Account locked for {BLOQUEIO_MIN} min."
        else:
            con.execute("UPDATE usuarios SET falhas=? WHERE id=?", (falhas, u["id"]))
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
    con = _con()
    try:
        con.execute("UPDATE usuarios SET senha_hash=?, salt=?, iteracoes=?, trocar_senha=?, falhas=0, "
                    "bloqueado_ate=NULL WHERE id=?",
                    (_hash(nova_senha, salt, ITERACOES), salt, ITERACOES, 1 if trocar_senha else 0, user_id))
        con.commit()
    finally:
        con.close()


def alterar_usuario(user_id, nome=None, perfil=None, ativo=None):
    """Altera nome, perfil ou situação; nunca deixa o sistema sem um Admin ativo."""
    con = _con()
    con.row_factory = sqlite3.Row
    try:
        u = con.execute("SELECT * FROM usuarios WHERE id=?", (user_id,)).fetchone()
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
        con.execute("UPDATE usuarios SET nome=?, perfil=?, ativo=? WHERE id=?",
                    ((nome or u["nome"]).strip(), novo_perfil, novo_ativo, user_id))
        con.commit()
    finally:
        con.close()


def listar_usuarios():
    con = _con()
    try:
        return con.execute("SELECT id, username, nome, perfil, ativo, ultimo_login FROM usuarios "
                           "ORDER BY username COLLATE NOCASE").fetchall()
    finally:
        con.close()


def eh_admin():
    return usuario_atual["perfil"] == "Admin"


def nome_responsavel():
    """Nome do usuário logado, para preencher o campo Responsible."""
    return usuario_atual["nome"] or usuario_atual["username"]


# ---------------------------------------------------------------------------
# INTERFACE
# ---------------------------------------------------------------------------
def _form(parent, titulo, campos, texto_ok="OK", extra=None):
    """Janela modal simples. campos = [(chave, rótulo, tipo)], tipo: 'text' | 'password' | lista de opções.

    Retorna {chave: valor} ou None se cancelada. extra = {chave: valor inicial}."""
    extra = extra or {}
    win = tk.Toplevel(parent)
    win.title(titulo)
    win.configure(bg=_fundo, padx=20, pady=16)
    win.resizable(False, False)
    vars_ = {}
    resultado = {"v": None}
    primeiro = None
    for i, (chave, rotulo, tipo) in enumerate(campos):
        tk.Label(win, text=rotulo, bg=_fundo, anchor="w").grid(row=i, column=0, sticky="w", pady=5, padx=(0, 12))
        v = tk.StringVar(master=win, value=extra.get(chave, ""))
        vars_[chave] = v
        if isinstance(tipo, (list, tuple)):
            w = ttk.Combobox(win, textvariable=v, values=list(tipo), state="readonly", width=28)
            if not v.get():
                v.set(tipo[0])
        else:
            w = ttk.Entry(win, textvariable=v, width=31, show="*" if tipo == "password" else "")
        w.grid(row=i, column=1, pady=5)
        if primeiro is None:
            primeiro = w
    msg = tk.Label(win, text="", bg=_fundo, fg="#c62828", wraplength=330, justify="left")
    msg.grid(row=len(campos), column=0, columnspan=2, sticky="w")

    def ok(_e=None):
        resultado["v"] = {k: v.get() for k, v in vars_.items()}
        win.destroy()

    botoes = tk.Frame(win, bg=_fundo)
    botoes.grid(row=len(campos) + 1, column=0, columnspan=2, pady=(10, 0), sticky="e")
    ttk.Button(botoes, text="Cancel", command=win.destroy).pack(side="right", padx=(8, 0))
    ttk.Button(botoes, text=texto_ok, command=ok).pack(side="right")
    win.bind("<Return>", ok)
    win.bind("<Escape>", lambda e: win.destroy())
    win.update_idletasks()
    win.grab_set()
    if primeiro is not None:
        primeiro.focus_set()
    win.wait_window()
    return resultado["v"]


def _form_validado(parent, titulo, campos, validar, texto_ok="OK", extra=None):
    """Repete o formulário até a validação passar (validar devolve mensagem de erro ou None)."""
    valores = extra
    while True:
        r = _form(parent, titulo, campos, texto_ok, valores)
        if r is None:
            return None
        erro = validar(r)
        if not erro:
            return r
        messagebox.showwarning(titulo, erro, parent=parent)
        valores = {k: v for k, v in r.items() if k not in ("senha", "senha2", "atual", "nova", "nova2")}


def _primeiro_admin(root):
    messagebox.showinfo("First use",
                        "No users are registered yet.\nCreate the first administrator account.", parent=root)

    def validar(r):
        if r["senha"] != r["senha2"]:
            return "The passwords do not match."
        try:
            criar_usuario(r["username"], r["nome"], "Admin", r["senha"], trocar_senha=False)
        except ValueError as e:
            return str(e)
        return None

    r = _form_validado(root, "Create administrator", [
        ("username", "Username", "text"), ("nome", "Full name", "text"),
        ("senha", "Password (min. %d)" % MIN_SENHA, "password"), ("senha2", "Repeat password", "password")],
        validar, "Create")
    return r is not None


def _trocar_senha_obrigatoria(root, u):
    """Primeiro acesso ou senha redefinida pelo admin: obriga a escolher uma senha nova."""
    messagebox.showinfo("Password", "You must choose a new password before continuing.", parent=root)

    def validar(r):
        ok, _m, _u = autenticar(u["username"], r["atual"])
        if not ok:
            return "Current password is incorrect."
        if r["nova"] != r["nova2"]:
            return "The new passwords do not match."
        if r["nova"] == r["atual"]:
            return "Choose a password different from the current one."
        erro = validar_senha(r["nova"], u["username"])
        if erro:
            return erro
        definir_senha(u["id"], r["nova"], trocar_senha=False, username=u["username"])
        return None

    r = _form_validado(root, "New password", [
        ("atual", "Current (temporary) password", "password"),
        ("nova", "New password", "password"), ("nova2", "Repeat new password", "password")],
        validar, "Save")
    return r is not None


def iniciar(root, programa):
    """Pede o login antes de abrir o programa. Fecha o programa se o login não for feito."""
    global _programa
    _programa = programa
    criar_tabelas()
    root.withdraw()
    if contar_usuarios() == 0 and not _primeiro_admin(root):
        root.destroy()
        sys.exit(0)

    logado = None
    while logado is None:
        r = _form(root, "Login - " + programa,
                  [("username", "Username", "text"), ("senha", "Password", "password")], "Login")
        if r is None:
            root.destroy()
            sys.exit(0)
        ok, msg, u = autenticar(r["username"], r["senha"])
        if not ok:
            usuario_atual.update(username=r["username"].strip(), nome="", perfil="")
            registrar("LOGIN_FAILED", msg)
            messagebox.showerror("Login", msg, parent=root)
            usuario_atual.update(username="")
            continue
        if u["trocar_senha"]:
            if not _trocar_senha_obrigatoria(root, u):
                continue
            registrar_como(u, "PASSWORD_CHANGE", "first access / temporary password")
        logado = u

    usuario_atual.update(id=logado["id"], username=logado["username"], nome=logado["nome"],
                         perfil=logado["perfil"])
    registrar("LOGIN")
    instalar_menu(root)
    root.after(0, root.deiconify)
    root.protocol("WM_DELETE_WINDOW", lambda: _sair(root))


def registrar_como(u, acao, detalhe=""):
    ant = dict(usuario_atual)
    usuario_atual.update(id=u["id"], username=u["username"], nome=u["nome"], perfil=u["perfil"])
    registrar(acao, detalhe)
    usuario_atual.update(ant)


def _sair(root):
    registrar("LOGOUT")
    root.destroy()


def _trocar_usuario(root):
    registrar("LOGOUT", "switch user")
    try:
        root.destroy()
    except Exception:
        pass
    os.execv(sys.executable, [sys.executable] + sys.argv)


def trocar_minha_senha(root):
    def validar(r):
        ok, _m, _u = autenticar(usuario_atual["username"], r["atual"])
        if not ok:
            return "Current password is incorrect."
        if r["nova"] != r["nova2"]:
            return "The new passwords do not match."
        erro = validar_senha(r["nova"], usuario_atual["username"])
        if erro:
            return erro
        definir_senha(usuario_atual["id"], r["nova"], trocar_senha=False, username=usuario_atual["username"])
        return None

    r = _form_validado(root, "Change password", [
        ("atual", "Current password", "password"),
        ("nova", "New password", "password"), ("nova2", "Repeat new password", "password")],
        validar, "Save")
    if r is not None:
        registrar("PASSWORD_CHANGE")
        messagebox.showinfo("Password", "Password changed.", parent=root)


def instalar_menu(root):
    barra = tk.Menu(root)
    conta = tk.Menu(barra, tearoff=0)
    conta.add_command(label=f"User: {usuario_atual['nome'] or usuario_atual['username']} ({usuario_atual['perfil']})",
                      state="disabled")
    conta.add_separator()
    conta.add_command(label="Change my password...", command=lambda: trocar_minha_senha(root))
    conta.add_command(label="Switch user (log out)", command=lambda: _trocar_usuario(root))
    if eh_admin():
        conta.add_separator()
        conta.add_command(label="Manage users...", command=lambda: abrir_usuarios(root))
        conta.add_command(label="Audit log...", command=lambda: abrir_auditoria(root))
    barra.add_cascade(label="Account", menu=conta)
    root.config(menu=barra)


def _nova_senha_dialogo(parent, titulo, username):
    def validar(r):
        if r["senha"] != r["senha2"]:
            return "The passwords do not match."
        return validar_senha(r["senha"], username)
    return _form_validado(parent, titulo, [
        ("senha", "Temporary password", "password"), ("senha2", "Repeat password", "password")], validar, "Save")


def abrir_usuarios(root):
    if not eh_admin():
        messagebox.showwarning("Users", "Only an Admin can manage users.", parent=root)
        return
    win = tk.Toplevel(root)
    win.title("Manage users")
    win.configure(bg=_fundo)
    win.geometry("760x420")
    cols = ("Username", "Full name", "Role", "Active", "Last login")
    tab = ttk.Treeview(win, columns=cols, show="headings", height=12)
    for c, w in zip(cols, (130, 220, 110, 60, 150)):
        tab.heading(c, text=c)
        tab.column(c, width=w, anchor="w")
    tab.pack(fill="both", expand=True, padx=12, pady=(12, 6))
    ids = {}

    def carregar():
        tab.delete(*tab.get_children())
        ids.clear()
        for id_, user, nome, perfil, ativo, ult in listar_usuarios():
            item = tab.insert("", "end", values=(user, nome, perfil, "Yes" if ativo else "No", ult or "-"))
            ids[item] = (id_, user, nome, perfil, ativo)

    def selecionado():
        s = tab.selection()
        if not s:
            messagebox.showwarning("Users", "Select a user in the table.", parent=win)
            return None
        return ids[s[0]]

    def novo():
        def validar(r):
            if r["senha"] != r["senha2"]:
                return "The passwords do not match."
            try:
                criar_usuario(r["username"], r["nome"], r["perfil"], r["senha"], trocar_senha=True)
            except ValueError as e:
                return str(e)
            return None
        r = _form_validado(win, "New user", [
            ("username", "Username", "text"), ("nome", "Full name", "text"),
            ("perfil", "Role", list(PERFIS)),
            ("senha", "Temporary password", "password"), ("senha2", "Repeat password", "password")],
            validar, "Create")
        if r:
            registrar("USER_CREATE", f"{r['username']} ({r['perfil']})")
            carregar()
            messagebox.showinfo("Users", "User created. The person must choose a new password at the first login.",
                                parent=win)

    def editar():
        u = selecionado()
        if not u:
            return
        id_, user, nome, perfil, ativo = u
        r = _form(win, "Edit user " + user, [("nome", "Full name", "text"), ("perfil", "Role", list(PERFIS))],
                  "Save", {"nome": nome, "perfil": perfil})
        if r:
            try:
                alterar_usuario(id_, nome=r["nome"], perfil=r["perfil"])
            except ValueError as e:
                messagebox.showwarning("Users", str(e), parent=win)
                return
            registrar("USER_UPDATE", f"{user}: {nome}/{perfil} -> {r['nome']}/{r['perfil']}")
            carregar()

    def redefinir():
        u = selecionado()
        if not u:
            return
        id_, user, *_ = u
        r = _nova_senha_dialogo(win, "Reset password: " + user, user)
        if r:
            definir_senha(id_, r["senha"], trocar_senha=True, username=user)
            registrar("PASSWORD_RESET", user)
            messagebox.showinfo("Users", "Temporary password set. The user must change it at the next login.",
                                parent=win)

    def ativar_desativar():
        u = selecionado()
        if not u:
            return
        id_, user, nome, perfil, ativo = u
        if id_ == usuario_atual["id"] and ativo:
            messagebox.showwarning("Users", "You cannot deactivate your own account.", parent=win)
            return
        acao = "Deactivate" if ativo else "Activate"
        if not messagebox.askyesno("Users", f"{acao} user {user}?\nRecords made by this user are kept.", parent=win):
            return
        try:
            alterar_usuario(id_, ativo=not ativo)
        except ValueError as e:
            messagebox.showwarning("Users", str(e), parent=win)
            return
        registrar("USER_DEACTIVATE" if ativo else "USER_ACTIVATE", user)
        carregar()

    botoes = tk.Frame(win, bg=_fundo)
    botoes.pack(pady=(4, 12))
    for txt, cmd in (("New user", novo), ("Edit", editar), ("Reset password", redefinir),
                     ("Activate / Deactivate", ativar_desativar), ("Close", win.destroy)):
        ttk.Button(botoes, text=txt, command=cmd).pack(side="left", padx=5)
    carregar()


def abrir_auditoria(root):
    if not eh_admin():
        messagebox.showwarning("Audit log", "Only an Admin can see the audit log.", parent=root)
        return
    win = tk.Toplevel(root)
    win.title("Audit log")
    win.configure(bg=_fundo)
    win.geometry("1060x520")
    topo = tk.Frame(win, bg=_fundo)
    topo.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(topo, text="Search:", bg=_fundo).pack(side="left")
    termo = tk.StringVar(master=win)
    ent = ttk.Entry(topo, textvariable=termo, width=34)
    ent.pack(side="left", padx=6)
    cols = ("When", "User", "Program", "Action", "Details")
    tab = ttk.Treeview(win, columns=cols, show="headings")
    for c, w in zip(cols, (150, 100, 190, 150, 420)):
        tab.heading(c, text=c)
        tab.column(c, width=w, anchor="w")
    tab.pack(fill="both", expand=True, padx=12, pady=6)
    estado = {"linhas": []}

    def carregar(_e=None):
        t = "%" + termo.get().strip() + "%"
        con = _con()
        try:
            estado["linhas"] = con.execute(
                "SELECT quando, usuario, programa, acao, detalhe FROM auditoria "
                "WHERE usuario LIKE ? OR programa LIKE ? OR acao LIKE ? OR detalhe LIKE ? OR quando LIKE ? "
                "ORDER BY id DESC LIMIT 2000", (t, t, t, t, t)).fetchall()
        finally:
            con.close()
        tab.delete(*tab.get_children())
        for r in estado["linhas"]:
            tab.insert("", "end", values=r)

    def exportar():
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", parent=win,
                                               initialfile="audit_log.csv")
        if not caminho:
            return
        with open(caminho, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(estado["linhas"])
        messagebox.showinfo("Audit log", "CSV file created.", parent=win)

    ttk.Button(topo, text="Search", command=carregar).pack(side="left")
    ttk.Button(topo, text="Export CSV", command=exportar).pack(side="right")
    ent.bind("<Return>", carregar)
    carregar()
