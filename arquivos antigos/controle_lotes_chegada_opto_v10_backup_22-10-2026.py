import os
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import qrcode
from datetime import datetime
import csv
import math
import re
import webbrowser
from pathlib import Path
from PIL import Image

# Caixas menores (lotes internos) são registradas como DUNE-CX-0001, DUNE-CX-0002, ...
PREFIXO_CAIXA = "DUNE-CX-"
# Lotes de limpeza realizada no Leptons (material que passou por remoção de PTP e nova limpeza)
PREFIXO_LIMPEZA = "DUNE-LP-"
PASTA_PDF = "relatorios_pdf"          # onde os PDFs de arquivo são gravados
DIGITOS_CAIXA = 4

# ===============================
# CONFIGURAÇÕES
# ===============================
DB_NAME = "lotes.db"
QR_DIR = "qrcodes_lotes"
SMALL_BOX_CAPACITY = 28

os.makedirs(QR_DIR, exist_ok=True)

# ===============================
# BANCO
# ===============================
conn = sqlite3.connect(DB_NAME, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")      # leituras e gravações não se bloqueiam; mais seguro contra queda
conn.execute("PRAGMA synchronous=FULL")      # confirma cada gravação no disco
conn.execute("PRAGMA busy_timeout=30000")    # espera até 30 s se o banco estiver ocupado
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_id TEXT,
    lote_geral TEXT,
    lote_fornecedor TEXT,
    data_recebimento TEXT,
    responsavel TEXT,
    fornecedor TEXT,
    total_filtros TEXT,
    numero_caixas_menores TEXT,
    capacidade_caixa_menor TEXT,
    material TEXT,
    dimensoes TEXT,
    espessura TEXT,
    tipo_acabamento TEXT,
    filtros_quebrados TEXT,
    quantidade_confere TEXT,
    procedimento_limpeza TEXT,
    resultado_inspecao TEXT,
    arquivo_controle TEXT,
    observacoes TEXT,
    qr_code_path TEXT,
    qrcodes_caixas_dir TEXT,
    data_hora_registro TEXT
)
""")
conn.commit()

# Atualiza bancos antigos sem perder registros já salvos
# IMPORTANTE: o SQLite não diferencia maiúsculas/minúsculas em nomes de colunas.
# Por isso, usamos lower() para evitar erro como: duplicate column name: fornecedor
colunas_existentes = [
    col[1].lower()
    for col in cursor.execute("PRAGMA table_info(lotes)").fetchall()
]

novas_colunas = {
    "tracking_id": "TEXT",
    "lote_geral": "TEXT",
    "lote_fornecedor": "TEXT",
    "data_recebimento": "TEXT",
    "responsavel": "TEXT",
    "fornecedor": "TEXT",
    "total_filtros": "TEXT",
    "numero_caixas_menores": "TEXT",
    "capacidade_caixa_menor": "TEXT",
    "material": "TEXT",
    "dimensoes": "TEXT",
    "espessura": "TEXT",
    "tipo_acabamento": "TEXT",
    "filtros_quebrados": "TEXT",
    "quantidade_confere": "TEXT",
    "procedimento_limpeza": "TEXT",
    "resultado_inspecao": "TEXT",
    "arquivo_controle": "TEXT",
    "observacoes": "TEXT",
    "qr_code_path": "TEXT",
    "qrcodes_caixas_dir": "TEXT",
    "data_hora_registro": "TEXT",
}

for nome, tipo in novas_colunas.items():
    if nome.lower() not in colunas_existentes:
        cursor.execute(f"ALTER TABLE lotes ADD COLUMN {nome} {tipo}")
        colunas_existentes.append(nome.lower())

conn.commit()

# Lotes internos: um código (e o lote do fornecedor) por caixa menor, escolhido depois no programa de deposição
cursor.execute("""
CREATE TABLE IF NOT EXISTS lotes_internos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_lote INTEGER,
    numero_caixa INTEGER,
    codigo_interno TEXT,
    quantidade_filtros TEXT,
    observacoes TEXT,
    lote_fornecedor TEXT
)
""")
cursor.execute("PRAGMA table_info(lotes_internos)")
if "lote_fornecedor" not in [c[1].lower() for c in cursor.fetchall()]:
    cursor.execute("ALTER TABLE lotes_internos ADD COLUMN lote_fornecedor TEXT")
conn.commit()

# Lotes de limpeza realizada no Leptons: viram lotes internos selecionáveis no programa de deposição
cursor.execute("""
CREATE TABLE IF NOT EXISTS lotes_limpeza (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_interno TEXT,
    data_limpeza TEXT,
    responsavel TEXT,
    quantidade_filtros TEXT,
    origem TEXT,
    remocao_ptp TEXT,
    procedimento TEXT,
    resultado TEXT,
    observacoes TEXT,
    data_hora_registro TEXT
)
""")
conn.commit()

registro_em_edicao = None
lotes_internos_pendentes = []   # [{"caixa": 1, "codigo": "...", "filtros": "28", "obs": ""}] do registro em edição

# ===============================
# FUNÇÕES AUXILIARES
# ===============================
def data_hora_atual():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def data_atual():
    return datetime.now().strftime("%d/%m/%Y")


def gerar_tracking_id(registro_id):
    return f"DUNE-HD-{datetime.now().year}-{registro_id:04d}"


def atualizar_relogio():
    lbl_relogio.config(text=f"Date/Time: {data_hora_atual()}")
    janela.after(1000, atualizar_relogio)


ultimo_calculo = None      # (capacidade, nº de caixas) do último cálculo; se mudar, refaz os filtros por caixa


def _inteiro_positivo(texto):
    try:
        valor = int(str(texto).strip())
        return valor if valor > 0 else None
    except ValueError:
        return None


def numero_caixas_atual():
    return _inteiro_positivo(entry_numero_caixas.get()) or 0


def definir_total(valor):
    """O total de filtros é calculado (campo somente leitura)."""
    entry_total_filtros.config(state="normal")
    entry_total_filtros.delete(0, tk.END)
    entry_total_filtros.insert(0, "" if valor is None else str(valor))
    entry_total_filtros.config(state="readonly")


def filtros_padrao_da_caixa(i, n):
    """Filtros da caixa i (de n): a capacidade. Registro antigo com última caixa parcial mantém o resto."""
    cap = _inteiro_positivo(entry_capacidade_caixa.get())
    if cap is None:
        return ""
    total = _inteiro_positivo(entry_total_filtros.get())
    if i == n and total is not None and cap * (n - 1) < total < cap * n:
        return str(total - cap * (n - 1))
    return str(cap)


def codigo_do_numero(numero):
    """'4' -> 'DUNE-CX-0004' (vazio se não houver número)."""
    numero = str(numero).strip()
    return PREFIXO_CAIXA + numero.zfill(DIGITOS_CAIXA) if numero else ""


def numero_do_codigo(codigo):
    """'DUNE-CX-0004' -> '0004'; código fora do padrão -> ''."""
    m = re.fullmatch(re.escape(PREFIXO_CAIXA) + r"(\d+)", str(codigo).strip(), flags=re.IGNORECASE)
    return m.group(1) if m else ""


def codigo_sugerido(i):
    return codigo_do_numero(i)


def ajustar_lotes_internos_ao_numero():
    """Mantém a lista de lotes internos com uma linha por caixa, preservando o que já foi digitado."""
    n = numero_caixas_atual()
    por_caixa = {item["caixa"]: item for item in lotes_internos_pendentes}
    nova = []
    for i in range(1, n + 1):
        item = por_caixa.get(i) or {"caixa": i, "codigo": "", "filtros": "", "obs": ""}
        if not str(item["filtros"]).strip():
            item["filtros"] = filtros_padrao_da_caixa(i, n)
        nova.append(item)
    lotes_internos_pendentes[:] = nova


def total_das_caixas():
    """Soma dos filtros de cada caixa (editáveis na janela de lotes internos)."""
    n = numero_caixas_atual()
    cap = _inteiro_positivo(entry_capacidade_caixa.get())
    if n == 0 or cap is None:
        return None
    soma = 0
    for it in lotes_internos_pendentes[:n]:
        f = str(it["filtros"]).strip()
        soma += int(f) if f.isdigit() else cap
    return soma


def calcular_caixas_menores(event=None):
    """capacidade x número de caixas -> total de filtros; já deixa a lista de lotes internos pronta."""
    global ultimo_calculo
    cap = _inteiro_positivo(entry_capacidade_caixa.get())
    n = numero_caixas_atual()
    if cap is None or n == 0:
        definir_total("")
        lbl_calculo.config(text="Enter the capacity and the number of small boxes.")
        atualizar_status_lotes_internos()
        return

    if ultimo_calculo != (cap, n):
        # capacidade ou número de caixas mudou: refaz os filtros de cada caixa (mantém códigos e observações)
        for it in lotes_internos_pendentes:
            it["filtros"] = ""
        ultimo_calculo = (cap, n)
    ajustar_lotes_internos_ao_numero()

    total = total_das_caixas()
    definir_total(total)
    iguais = all(str(it["filtros"]).strip() == str(cap) for it in lotes_internos_pendentes)
    if iguais:
        lbl_calculo.config(text=f"{n} small box(es) x {cap} filters = {total} filters.")
    else:
        lbl_calculo.config(text=f"{n} small box(es), {total} filters (custom count in some boxes).")
    atualizar_status_lotes_internos()


def recalcular_do_zero():
    """Volta a capacidade de cada caixa ao padrão (capacidade x caixas)."""
    global ultimo_calculo
    ultimo_calculo = None
    calcular_caixas_menores()


# ===============================
# LOTES INTERNOS (um por caixa menor)
# ===============================
def atualizar_status_lotes_internos(event=None):
    n = numero_caixas_atual()
    registrados = sum(1 for it in lotes_internos_pendentes if it["caixa"] <= n and it["codigo"].strip())
    try:
        btn_lotes_internos.config(state="normal" if n > 0 else "disabled")
        if n == 0:
            lbl_lotes_internos.config(text="Internal lots: --", fg="#757575")
        else:
            lbl_lotes_internos.config(
                text=f"Internal lots: {registrados}/{n} registered",
                fg="#2e7d32" if registrados == n else "#c62828"
            )
    except NameError:
        pass


def carregar_lotes_internos_db(registro_id):
    """Carrega os lotes internos do registro em edição (registros antigos: cria as linhas padrão)."""
    global ultimo_calculo
    lotes_internos_pendentes.clear()
    cursor.execute("""
        SELECT numero_caixa, codigo_interno, quantidade_filtros, observacoes
        FROM lotes_internos WHERE id_lote = ? ORDER BY numero_caixa
    """, (registro_id,))
    for caixa, codigo, filtros, obs in cursor.fetchall():
        lotes_internos_pendentes.append(
            {"caixa": caixa, "codigo": codigo or "", "filtros": filtros or "", "obs": obs or ""})
    ajustar_lotes_internos_ao_numero()
    ultimo_calculo = (_inteiro_positivo(entry_capacidade_caixa.get()), numero_caixas_atual())
    calcular_caixas_menores()


def buscar_lotes_internos_db(registro_id):
    """{numero_caixa: (codigo, filtros)} gravado no banco para o lote."""
    cursor.execute("SELECT numero_caixa, codigo_interno, quantidade_filtros FROM lotes_internos WHERE id_lote = ?",
                   (registro_id,))
    return {caixa: (codigo or "", filtros or "") for caixa, codigo, filtros in cursor.fetchall()}


def conflito_codigos_internos(itens=None):
    """Mensagem se um código estiver repetido dentro do mesmo lote OPTO; senão None."""
    itens = lotes_internos_pendentes if itens is None else itens
    vistos = {}
    for it in itens:
        codigo = it["codigo"].strip()
        if not codigo:
            continue
        chave = codigo.lower()
        if chave in vistos:
            return f"Internal lot code '{codigo}' is used by boxes {vistos[chave]:02d} and {it['caixa']:02d}."
        vistos[chave] = it["caixa"]
    return None


def salvar_lotes_internos(registro_id):
    """Grava os lotes internos mantendo os mesmos IDs (o programa de deposição guarda esse ID)."""
    n = numero_caixas_atual()
    cursor.execute("SELECT id, numero_caixa FROM lotes_internos WHERE id_lote = ?", (registro_id,))
    existentes = {num: id_ for id_, num in cursor.fetchall()}

    for item in lotes_internos_pendentes:
        if item["caixa"] > n:
            continue
        codigo = item["codigo"].strip()
        if not codigo:
            if item["caixa"] in existentes:
                cursor.execute("DELETE FROM lotes_internos WHERE id = ?", (existentes[item["caixa"]],))
            continue
        valores = (codigo, str(item["filtros"]).strip(), item["obs"].strip())
        if item["caixa"] in existentes:
            cursor.execute("""
                UPDATE lotes_internos
                SET codigo_interno = ?, quantidade_filtros = ?, observacoes = ?
                WHERE id = ?
            """, valores + (existentes[item["caixa"]],))
        else:
            cursor.execute("""
                INSERT INTO lotes_internos (id_lote, numero_caixa, codigo_interno, quantidade_filtros, observacoes)
                VALUES (?, ?, ?, ?, ?)
            """, (registro_id, item["caixa"]) + valores)

    cursor.execute("DELETE FROM lotes_internos WHERE id_lote = ? AND numero_caixa > ?", (registro_id, n))
    conn.commit()


def preparar_lotes_internos_para_salvar():
    """Confere os lotes internos antes de salvar o lote. Retorna False para cancelar o salvamento."""
    n = numero_caixas_atual()
    ajustar_lotes_internos_ao_numero()
    if n == 0:
        return True

    faltando = [it for it in lotes_internos_pendentes if not it["codigo"].strip()]
    if faltando:
        resposta = messagebox.askyesnocancel(
            "Internal lots",
            f"{len(faltando)} of {n} small boxes have no internal lot code ({PREFIXO_CAIXA}000X).\n\n"
            "Yes = fill them with the next numbers\n"
            "No = save without them (they will not be selectable for deposition)\n"
            "Cancel = go back and register them"
        )
        if resposta is None:
            abrir_lotes_internos()
            return False
        if resposta:
            for it in faltando:
                it["codigo"] = codigo_sugerido(it["caixa"])

    conflito = conflito_codigos_internos()
    if conflito:
        messagebox.showwarning("Internal lots", conflito)
        abrir_lotes_internos()
        return False
    atualizar_status_lotes_internos()
    return True


def abrir_lotes_internos():
    """Registra cada caixa menor como DUNE-CX-000X, com o nome do lote OPTO fixo."""
    opto = entry_lote_geral.get().strip()
    cap = _inteiro_positivo(entry_capacidade_caixa.get())
    n = numero_caixas_atual()
    if not opto:
        messagebox.showwarning("Warning", "Enter the OPTO batch first.")
        return
    if n <= 0 or cap is None:
        messagebox.showwarning("Warning", "Enter the small box capacity and the number of small boxes first.")
        return
    calcular_caixas_menores()          # garante uma linha por caixa, já com os filtros calculados

    win = tk.Toplevel(janela)
    win.title("Internal Lots")
    win.geometry("900x540")
    win.transient(janela)
    win.grab_set()

    tk.Label(
        win, font=("Segoe UI", 10, "bold"), anchor="w",
        text=f"OPTO Batch: {opto}    |    Small boxes: {n}    |    Capacity: {cap} filters per box"
    ).pack(fill="x", padx=12, pady=(10, 0))
    tk.Label(
        win, anchor="w", fg="#424242", wraplength=870, justify="left",
        text=(f"Register each small box as {PREFIXO_CAIXA}000X (type only the number). "
              "The OPTO batch name is fixed; the internal lot is chosen in the deposition program.")
    ).pack(fill="x", padx=12, pady=(2, 6))

    quadro = tk.Frame(win)
    quadro.pack(fill="both", expand=True, padx=12)
    canvas = tk.Canvas(quadro, highlightthickness=0)
    barra = ttk.Scrollbar(quadro, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=barra.set)
    barra.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    interno = tk.Frame(canvas)
    canvas.create_window((0, 0), window=interno, anchor="nw")
    interno.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    cabecalhos = (("Box", 6), ("OPTO Batch (fixed)", 26), ("Internal lot code", 22), ("Filters", 9), ("Notes", 30))
    for c, (titulo, largura) in enumerate(cabecalhos):
        tk.Label(interno, text=titulo, bg="#1f3a5f", fg="white", font=("Segoe UI", 9, "bold"),
                 width=largura, pady=5).grid(row=0, column=c, padx=1, pady=(0, 2), sticky="nsew")

    linhas = []
    for i, item in enumerate(lotes_internos_pendentes, start=1):
        v_num = tk.StringVar(value=numero_do_codigo(item["codigo"]))
        v_filtros = tk.StringVar(value=str(item["filtros"]))
        v_obs = tk.StringVar(value=item["obs"])
        tk.Label(interno, text=f"{i:02d}", font=("Segoe UI", 10, "bold")).grid(row=i, column=0, pady=2)
        tk.Label(interno, text=opto, bg="#e8e8e8", relief="sunken", anchor="w", width=28).grid(
            row=i, column=1, padx=3, pady=2)
        celula = tk.Frame(interno)
        celula.grid(row=i, column=2, padx=3, pady=2)
        tk.Label(celula, text=PREFIXO_CAIXA, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Entry(celula, textvariable=v_num, width=8, justify="center").pack(side="left")
        tk.Entry(interno, textvariable=v_filtros, width=9, justify="center").grid(row=i, column=3, padx=3, pady=2)
        tk.Entry(interno, textvariable=v_obs, width=32).grid(row=i, column=4, padx=3, pady=2)
        linhas.append((v_num, v_filtros, v_obs))

    def sugerir():
        for i, (v_num, _, _) in enumerate(linhas, start=1):
            if not v_num.get().strip():
                v_num.set(str(i).zfill(DIGITOS_CAIXA))

    def limpar_codigos():
        for v_num, _, _ in linhas:
            v_num.set("")

    def aplicar():
        itens = []
        for i, (v_num, v_filtros, v_obs) in enumerate(linhas, start=1):
            numero = v_num.get().strip()
            if numero and not numero.isdigit():
                messagebox.showwarning("Warning", f"Box {i:02d}: type only the number (digits), e.g. 0004.", parent=win)
                return
            filtros = v_filtros.get().strip()
            if filtros and not filtros.isdigit():
                messagebox.showwarning("Warning", f"Filters in box {i:02d} must be an integer.", parent=win)
                return
            itens.append({"caixa": i, "codigo": codigo_do_numero(numero), "filtros": filtros, "obs": v_obs.get().strip()})
        conflito = conflito_codigos_internos(itens)
        if conflito:
            messagebox.showwarning("Internal lots", conflito, parent=win)
            return
        lotes_internos_pendentes[:] = itens
        calcular_caixas_menores()          # atualiza o total de filtros com o que foi digitado
        win.destroy()

    botoes = tk.Frame(win)
    botoes.pack(fill="x", padx=12, pady=10)
    tk.Button(botoes, text=f"Fill empty rows ({PREFIXO_CAIXA}0001...)", command=sugerir).pack(side="left", padx=4)
    tk.Button(botoes, text="Clear codes", command=limpar_codigos).pack(side="left", padx=4)
    tk.Button(botoes, text="Cancel", command=win.destroy, width=12).pack(side="right", padx=4)
    tk.Button(botoes, text="OK", command=aplicar, bg="#2e7d32", fg="white", width=12).pack(side="right", padx=4)
    tk.Label(win, text="Nothing is stored until you use Save / Update Record on the main window.",
             fg="#757575", font=("Segoe UI", 8)).pack(pady=(0, 8))


def selecionar_arquivo_controle():
    caminho = filedialog.askopenfilename(
        title="Select supplier control file",
        filetypes=[
            ("All supported files", "*.pdf *.xlsx *.xls *.csv *.docx *.txt"),
            ("PDF", "*.pdf"),
            ("Excel", "*.xlsx *.xls"),
            ("CSV", "*.csv"),
            ("Word", "*.docx"),
            ("Text", "*.txt"),
            ("All files", "*.*"),
        ],
    )
    if caminho:
        entry_arquivo.delete(0, tk.END)
        entry_arquivo.insert(0, caminho)


def abrir_arquivo_controle():
    caminho = entry_arquivo.get().strip()
    if not caminho:
        messagebox.showwarning("Warning", "No supplier control file selected.")
        return
    if not os.path.exists(caminho):
        messagebox.showerror("Error", "The selected file was not found.")
        return
    try:
        if os.name == "nt":
            os.startfile(caminho)  # type: ignore[attr-defined]
        elif hasattr(os, "uname") and os.uname().sysname == "Darwin":
            os.system(f'open "{caminho}"')
        else:
            os.system(f'xdg-open "{caminho}"')
    except Exception as e:
        messagebox.showerror("Error opening file", str(e))


def gerar_qrcode(registro_id, tracking_id, dados):
    caminho = os.path.join(QR_DIR, f"{tracking_id}.png")
    conteudo = "\n".join([f"{k}: {v}" for k, v in dados.items()])
    img = qrcode.make(conteudo)
    img.save(caminho)
    return caminho


def gerar_qrcodes_caixas_menores(registro_id, tracking_id, dados):
    """
    Gera QR Codes individuais para as caixas menores contidas no lote geral.
    Cada QR aponta para o mesmo lote geral, mas identifica a caixa física: Box 01/N.
    """
    try:
        numero_caixas = int(dados.get("numero_caixas_menores", 0))
    except ValueError:
        numero_caixas = 0

    if numero_caixas <= 0:
        return ""

    pasta = os.path.join(QR_DIR, tracking_id, "small_boxes")
    os.makedirs(pasta, exist_ok=True)

    total_filtros = int(dados.get("total_filtros", 0))
    capacidade = int(dados.get("capacidade_caixa_menor", SMALL_BOX_CAPACITY))
    internos = buscar_lotes_internos_db(registro_id)

    for i in range(1, numero_caixas + 1):
        # Estima a quantidade em cada caixa: as anteriores completas e a última com o restante, se houver.
        if i < numero_caixas:
            filtros_na_caixa = capacidade
        else:
            restante = total_filtros - capacidade * (numero_caixas - 1)
            filtros_na_caixa = restante if restante > 0 else capacidade

        codigo_interno, filtros_interno = internos.get(i, ("", ""))
        if filtros_interno.isdigit():
            filtros_na_caixa = int(filtros_interno)

        caixa_id = f"{tracking_id}-BOX-{i:02d}"
        conteudo = "\n".join([
            f"Tracking ID: {tracking_id}",
            f"Small Box ID: {caixa_id}",
            f"Small Box: {i:02d}/{numero_caixas:02d}",
            f"Internal Lot: {codigo_interno}",
            f"OPTO Batch: {dados.get('lote_geral', '')}",
            f"Supplier: {dados.get('fornecedor', '')}",
            f"Arrival Date: {dados.get('data_recebimento', '')}",
            f"Total Filters in General Batch: {dados.get('total_filtros', '')}",
            f"Estimated Filters in This Small Box: {filtros_na_caixa}",
            f"Small Box Capacity: {capacidade}",
        ])
        img = qrcode.make(conteudo)
        img.save(os.path.join(pasta, f"BOX_{i:02d}_of_{numero_caixas:02d}.png"))

    return pasta


def abrir_pasta(caminho):
    if not caminho or not os.path.exists(caminho):
        messagebox.showerror("Error", "Folder or file was not found.")
        return
    try:
        if os.name == "nt":
            os.startfile(caminho)  # type: ignore[attr-defined]
        elif hasattr(os, "uname") and os.uname().sysname == "Darwin":
            os.system(f'open "{caminho}"')
        else:
            os.system(f'xdg-open "{caminho}"')
    except Exception as e:
        messagebox.showerror("Error opening folder", str(e))


def abrir_qrcode_selecionado():
    selecionado = tabela.selection()
    if not selecionado:
        messagebox.showwarning("Warning", "Select a record to open the QR Code.")
        return
    valores = tabela.item(selecionado[0], "values")
    id_reg = valores[0]
    cursor.execute("SELECT qr_code_path FROM lotes WHERE id = ?", (id_reg,))
    resultado = cursor.fetchone()
    if not resultado or not resultado[0]:
        messagebox.showwarning("Warning", "This record does not have a QR Code yet.")
        return
    caminho = resultado[0]
    if not os.path.exists(caminho):
        messagebox.showerror("Error", "QR Code file was not found.")
        return
    try:
        if os.name == "nt":
            os.startfile(caminho)  # type: ignore[attr-defined]
        elif hasattr(os, "uname") and os.uname().sysname == "Darwin":
            os.system(f'open "{caminho}"')
        else:
            os.system(f'xdg-open "{caminho}"')
    except Exception as e:
        messagebox.showerror("Error opening QR Code", str(e))


def abrir_qrcodes_caixas_selecionado():
    selecionado = tabela.selection()
    if not selecionado:
        messagebox.showwarning("Warning", "Select a record to open the small-box QR Codes.")
        return

    valores = tabela.item(selecionado[0], "values")
    id_reg = valores[0]

    cursor.execute("""
        SELECT qrcodes_caixas_dir, tracking_id, lote_geral, lote_fornecedor,
               fornecedor, data_recebimento, total_filtros, numero_caixas_menores,
               capacidade_caixa_menor
        FROM lotes WHERE id = ?
    """, (id_reg,))
    row = cursor.fetchone()
    if not row:
        messagebox.showerror("Error", "Record not found.")
        return

    pasta = row[0]
    if pasta and os.path.exists(pasta):
        abrir_pasta(pasta)
        return

    # Caso o registro seja antigo e ainda não tenha QR das caixas, gera agora.
    dados = {
        "lote_geral": row[2] or "",
        "lote_fornecedor": row[3] or "",
        "fornecedor": row[4] or "",
        "data_recebimento": row[5] or "",
        "total_filtros": row[6] or "0",
        "numero_caixas_menores": row[7] or "0",
        "capacidade_caixa_menor": row[8] or str(SMALL_BOX_CAPACITY),
    }
    tracking_id = row[1] or gerar_tracking_id(int(id_reg))
    pasta = gerar_qrcodes_caixas_menores(int(id_reg), tracking_id, dados)
    if pasta:
        cursor.execute("UPDATE lotes SET qrcodes_caixas_dir = ?, tracking_id = ? WHERE id = ?", (pasta, tracking_id, id_reg))
        conn.commit()
        abrir_pasta(pasta)
    else:
        messagebox.showwarning("Warning", "No small-box QR Codes were generated. Check the number of small boxes.")


# ===============================
# CRUD
# ===============================
def coletar_dados():
    calcular_caixas_menores()
    return {
        "lote_geral": entry_lote_geral.get().strip(),
        "lote_fornecedor": entry_lote_fornecedor.get().strip(),
        "data_recebimento": entry_data.get().strip(),
        "responsavel": entry_resp.get().strip(),
        "fornecedor": entry_fornecedor.get().strip(),
        "total_filtros": entry_total_filtros.get().strip(),
        "numero_caixas_menores": entry_numero_caixas.get().strip(),
        "capacidade_caixa_menor": entry_capacidade_caixa.get().strip(),
        "material": entry_material.get().strip(),
        "dimensoes": entry_dimensoes.get().strip(),
        "espessura": entry_espessura.get().strip(),
        "tipo_acabamento": combo_acabamento.get().strip(),
        "filtros_quebrados": var_filtros_quebrados.get(),
        "quantidade_confere": var_quantidade_confere.get(),
        "procedimento_limpeza": var_procedimento_limpeza.get(),
        "resultado_inspecao": combo_resultado_inspecao.get().strip(),
        "arquivo_controle": entry_arquivo.get().strip(),
        "observacoes": txt_obs.get("1.0", "end").strip(),
        "data_hora_registro": data_hora_atual(),
    }


def validar_dados(dados):
    if not dados["lote_geral"]:
        messagebox.showwarning("Warning", "Enter the general batch ID.")
        return False
    if not dados["total_filtros"]:
        messagebox.showwarning("Warning", "Enter the small box capacity and the number of small boxes "
                                      "(the total number of filters is calculated from them).")
        return False
    try:
        total = int(dados["total_filtros"])
        if total < 0:
            raise ValueError
    except ValueError:
        messagebox.showwarning("Warning", "Total number of filters must be an integer.")
        return False
    try:
        caixas = int(dados["numero_caixas_menores"])
        if caixas < 1:
            raise ValueError
    except ValueError:
        messagebox.showwarning("Warning", "Number of small boxes must be an integer.")
        return False
    return True


def salvar():
    global registro_em_edicao
    try:
        dados = coletar_dados()
        if not validar_dados(dados):
            return
        if not preparar_lotes_internos_para_salvar():
            return

        if registro_em_edicao is None:
            cursor.execute("""
                INSERT INTO lotes (
                    lote_geral, lote_fornecedor, data_recebimento, responsavel,
                    fornecedor, total_filtros, numero_caixas_menores,
                    capacidade_caixa_menor, material, dimensoes, espessura,
                    tipo_acabamento, filtros_quebrados, quantidade_confere,
                    procedimento_limpeza, resultado_inspecao, arquivo_controle,
                    observacoes, data_hora_registro
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dados["lote_geral"], dados["lote_fornecedor"], dados["data_recebimento"],
                dados["responsavel"], dados["fornecedor"], dados["total_filtros"],
                dados["numero_caixas_menores"], dados["capacidade_caixa_menor"],
                dados["material"], dados["dimensoes"], dados["espessura"],
                dados["tipo_acabamento"], dados["filtros_quebrados"],
                dados["quantidade_confere"], dados["procedimento_limpeza"],
                dados["resultado_inspecao"], dados["arquivo_controle"],
                dados["observacoes"], dados["data_hora_registro"]
            ))
            conn.commit()
            registro_id = cursor.lastrowid
            tracking_id = gerar_tracking_id(registro_id)
        else:
            registro_id = registro_em_edicao
            cursor.execute("SELECT tracking_id FROM lotes WHERE id = ?", (registro_id,))
            row = cursor.fetchone()
            tracking_id = row[0] if row and row[0] else gerar_tracking_id(registro_id)
            cursor.execute("""
                UPDATE lotes SET
                    lote_geral = ?, lote_fornecedor = ?, data_recebimento = ?,
                    responsavel = ?, fornecedor = ?, total_filtros = ?,
                    numero_caixas_menores = ?, capacidade_caixa_menor = ?,
                    material = ?, dimensoes = ?, espessura = ?, tipo_acabamento = ?,
                    filtros_quebrados = ?, quantidade_confere = ?,
                    procedimento_limpeza = ?, resultado_inspecao = ?,
                    arquivo_controle = ?, observacoes = ?, data_hora_registro = ?
                WHERE id = ?
            """, (
                dados["lote_geral"], dados["lote_fornecedor"], dados["data_recebimento"],
                dados["responsavel"], dados["fornecedor"], dados["total_filtros"],
                dados["numero_caixas_menores"], dados["capacidade_caixa_menor"],
                dados["material"], dados["dimensoes"], dados["espessura"],
                dados["tipo_acabamento"], dados["filtros_quebrados"],
                dados["quantidade_confere"], dados["procedimento_limpeza"],
                dados["resultado_inspecao"], dados["arquivo_controle"],
                dados["observacoes"], dados["data_hora_registro"], registro_id
            ))
            conn.commit()

        salvar_lotes_internos(registro_id)

        qr_path = gerar_qrcode(registro_id, tracking_id, {
            "Tracking ID": tracking_id,
            "OPTO Batch": dados["lote_geral"],
            "Supplier": dados["fornecedor"],
            "Arrival Date": dados["data_recebimento"],
            "Total Filters": dados["total_filtros"],
            "Number of Small Boxes": dados["numero_caixas_menores"],
            "Small Box Capacity": dados["capacidade_caixa_menor"],
        })
        qrcodes_caixas_dir = gerar_qrcodes_caixas_menores(registro_id, tracking_id, dados)

        cursor.execute("""
            UPDATE lotes
            SET tracking_id = ?, qr_code_path = ?, qrcodes_caixas_dir = ?
            WHERE id = ?
        """, (tracking_id, qr_path, qrcodes_caixas_dir, registro_id))
        conn.commit()

        atualizar_tabela()
        limpar()
        messagebox.showinfo("Success", "Record saved successfully.")

    except Exception as e:
        messagebox.showerror("Error saving", str(e))


def carregar_para_edicao():
    global registro_em_edicao
    selecionado = tabela.selection()
    if not selecionado:
        messagebox.showwarning("Warning", "Select a record in the table to edit.")
        return

    valores = tabela.item(selecionado[0], "values")
    id_reg = valores[0]
    cursor.execute("""
        SELECT id, lote_geral, lote_fornecedor, data_recebimento, responsavel,
               fornecedor, total_filtros, numero_caixas_menores,
               capacidade_caixa_menor, material, dimensoes, espessura,
               tipo_acabamento, filtros_quebrados, quantidade_confere,
               procedimento_limpeza, resultado_inspecao, arquivo_controle,
               observacoes
        FROM lotes WHERE id = ?
    """, (id_reg,))
    row = cursor.fetchone()
    if not row:
        messagebox.showerror("Error", "Record not found.")
        return

    limpar()
    registro_em_edicao = row[0]
    entry_data.delete(0, tk.END)
    entry_fornecedor.delete(0, tk.END)
    entry_lote_geral.insert(0, row[1] or "")
    entry_lote_fornecedor.insert(0, row[2] or "")
    entry_data.insert(0, row[3] or "")
    entry_resp.insert(0, row[4] or "")
    entry_fornecedor.insert(0, row[5] or "")
    definir_total(row[6] or "")
    entry_numero_caixas.insert(0, row[7] or "")
    entry_capacidade_caixa.delete(0, tk.END)
    entry_capacidade_caixa.insert(0, row[8] or str(SMALL_BOX_CAPACITY))
    entry_material.insert(0, row[9] or "")
    entry_dimensoes.insert(0, row[10] or "")
    entry_espessura.insert(0, row[11] or "")
    combo_acabamento.set(row[12] or "Polished")
    var_filtros_quebrados.set(row[13] or "No")
    var_quantidade_confere.set(row[14] or "Yes")
    var_procedimento_limpeza.set(row[15] or "Yes")
    combo_resultado_inspecao.set(row[16] or "Approved")
    entry_arquivo.insert(0, row[17] or "")
    txt_obs.insert("1.0", row[18] or "")
    btn_save.config(text="Update Record")
    lbl_modo.config(text=f"Editing record ID {registro_em_edicao}")
    carregar_lotes_internos_db(registro_em_edicao)


def limpar():
    global registro_em_edicao, ultimo_calculo
    registro_em_edicao = None
    for entry in [
        entry_lote_geral, entry_lote_fornecedor, entry_data, entry_resp,
        entry_fornecedor, entry_numero_caixas,
        entry_material, entry_dimensoes, entry_espessura, entry_arquivo
    ]:
        entry.delete(0, tk.END)

    entry_data.insert(0, data_atual())
    entry_fornecedor.insert(0, "OPTO")
    entry_capacidade_caixa.delete(0, tk.END)
    entry_capacidade_caixa.insert(0, str(SMALL_BOX_CAPACITY))
    combo_acabamento.set("Polished")
    combo_resultado_inspecao.set("Approved")
    txt_obs.delete("1.0", tk.END)
    var_filtros_quebrados.set("No")
    var_quantidade_confere.set("Yes")
    var_procedimento_limpeza.set("Yes")
    lbl_calculo.config(text="Small boxes: --")
    btn_save.config(text="Save")
    lbl_modo.config(text="New record")
    lotes_internos_pendentes.clear()
    ultimo_calculo = None
    definir_total("")
    atualizar_status_lotes_internos()


def inserir_linha_tabela(row):
    """row = (..., numero_caixas_menores, qtd_lotes_internos, ...): mostra 'registrados/caixas'."""
    valores = list(row)
    valores[6] = f"{row[6]}/{row[5] or 0}"
    tabela.insert("", tk.END, values=valores)


def atualizar_tabela():
    for i in tabela.get_children():
        tabela.delete(i)

    cursor.execute("""
        SELECT id, tracking_id, lote_geral, fornecedor,
               total_filtros, numero_caixas_menores,
               (SELECT COUNT(*) FROM lotes_internos li WHERE li.id_lote = lotes.id),
               data_recebimento, responsavel, resultado_inspecao, data_hora_registro
        FROM lotes
        ORDER BY id DESC
    """)
    for row in cursor.fetchall():
        inserir_linha_tabela(row)


def buscar():
    termo = entry_busca.get().strip()
    for i in tabela.get_children():
        tabela.delete(i)

    cursor.execute("""
        SELECT id, tracking_id, lote_geral, fornecedor,
               total_filtros, numero_caixas_menores,
               (SELECT COUNT(*) FROM lotes_internos li WHERE li.id_lote = lotes.id),
               data_recebimento, responsavel, resultado_inspecao, data_hora_registro
        FROM lotes
        WHERE tracking_id LIKE ? OR lote_geral LIKE ? OR lote_fornecedor LIKE ?
              OR fornecedor LIKE ? OR responsavel LIKE ?
              OR id IN (SELECT id_lote FROM lotes_internos WHERE codigo_interno LIKE ?)
        ORDER BY id DESC
    """, tuple(['%' + termo + '%'] * 6))
    for row in cursor.fetchall():
        inserir_linha_tabela(row)


def exportar_csv():
    caminho = filedialog.asksaveasfilename(defaultextension=".csv")
    if not caminho:
        return

    cursor.execute("""
        SELECT id, tracking_id, lote_geral, data_recebimento,
               responsavel, fornecedor, total_filtros, numero_caixas_menores,
               capacidade_caixa_menor, material, dimensoes, espessura,
               tipo_acabamento, filtros_quebrados, quantidade_confere,
               procedimento_limpeza, resultado_inspecao, arquivo_controle,
               observacoes, qr_code_path, qrcodes_caixas_dir, data_hora_registro,
               (SELECT GROUP_CONCAT(codigo_interno, '; ') FROM lotes_internos li WHERE li.id_lote = lotes.id)
        FROM lotes
        ORDER BY id DESC
    """)
    dados = cursor.fetchall()

    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "Tracking ID", "OPTO Batch", "Arrival Date",
            "Responsible", "Supplier", "Total Number of Filters",
            "Number of Small Boxes", "Small Box Capacity", "Material", "Dimensions",
            "Thickness", "Finishing Type", "Broken Filters?", "Quantity Matches?",
            "Cleaning Procedure Verified?", "Inspection Result", "Supplier Control File",
            "Observations", "General Batch QR Code", "Small Boxes QR Code Folder", "Record Date/Time",
            "Internal Lots"
        ])
        writer.writerows(dados)

    messagebox.showinfo("Exported", "CSV file created.")


def excluir_selecionado():
    selecionado = tabela.selection()
    if not selecionado:
        messagebox.showwarning("Warning", "Select a record in the table to delete.")
        return

    valores = tabela.item(selecionado[0], "values")
    id_reg = valores[0]
    ok = messagebox.askyesno("Confirm deletion", f"Delete record ID {id_reg}?")
    if not ok:
        return

    cursor.execute("DELETE FROM lotes WHERE id = ?", (id_reg,))
    cursor.execute("DELETE FROM lotes_internos WHERE id_lote = ?", (id_reg,))
    conn.commit()
    atualizar_tabela()
    limpar()
    messagebox.showinfo("Success", "Record deleted.")


# ===============================
# PDF PARA ARQUIVO (backup dos dados)
# ===============================
def _registrar_fontes_pdf():
    """Procura uma fonte TrueType com boa cobertura de caracteres; senão usa Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidatos = [
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for normal, negrito in candidatos:
        if os.path.exists(normal) and os.path.exists(negrito):
            try:
                pdfmetrics.registerFont(TTFont("RelFonte", normal))
                pdfmetrics.registerFont(TTFont("RelFonte-Bold", negrito))
                pdfmetrics.registerFontFamily("RelFonte", normal="RelFonte", bold="RelFonte-Bold",
                                              italic="RelFonte", boldItalic="RelFonte-Bold")
                return "RelFonte", "RelFonte-Bold"
            except Exception:
                pass
    return "Helvetica", "Helvetica-Bold"


def _pdf_disponivel():
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        messagebox.showerror(
            "PDF",
            "The 'reportlab' package is required to create PDFs.\nInstall it with:  pip install reportlab"
        )
        return False


def _kit_pdf(landscape_pagina=False):
    """Estilos e funções auxiliares comuns aos PDFs deste programa."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
    from xml.sax.saxutils import escape as xesc

    pagina = landscape(A4) if landscape_pagina else A4
    largura = pagina[0] - 24 * mm
    fonte, negrito = _registrar_fontes_pdf()
    azul = colors.HexColor("#1f3a5f")
    zebra = colors.HexColor("#eef3f9")
    grade = colors.HexColor("#9aa7b5")

    base = ParagraphStyle("base", fontName=fonte, fontSize=8, leading=10)
    est_cel = ParagraphStyle("cel", parent=base, fontSize=7.5, leading=9)
    est_cab = ParagraphStyle("cab", parent=est_cel, fontName=negrito, textColor=colors.white, alignment=TA_CENTER)
    est_titulo = ParagraphStyle("tit", parent=base, fontName=negrito, fontSize=13, leading=16,
                                alignment=TA_CENTER, textColor=azul)
    est_sub = ParagraphStyle("sub", parent=base, alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
    est_sec = ParagraphStyle("sec", parent=base, fontName=negrito, fontSize=10, leading=12, textColor=colors.white)

    def txt(v, vazio="-"):
        v = "" if v is None else str(v).strip()
        return xesc(v).replace("\n", "<br/>") if v else vazio

    def P(v, estilo=None, vazio="-"):
        return Paragraph(txt(v, vazio), estilo or est_cel)

    def H(texto):
        return Paragraph(xesc(texto), est_cab)

    def campo(rotulo, valor):
        return Paragraph("<b>" + xesc(rotulo) + ":</b> " + txt(valor), est_cel)

    def secao(titulo):
        tb = Table([[Paragraph(xesc(titulo), est_sec)]], colWidths=[largura])
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), azul), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return tb

    def tabela(linhas, larguras, cabecalho=True, extra=None):
        tb = Table(linhas, colWidths=[w * mm for w in larguras], repeatRows=1 if cabecalho else 0)
        estilo = [("FONTNAME", (0, 0), (-1, -1), fonte), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                  ("GRID", (0, 0), (-1, -1), 0.4, grade), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                  ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        if cabecalho:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), azul),
                       ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, zebra])]
        if extra:
            estilo += extra
        tb.setStyle(TableStyle(estilo))
        return tb

    return {
        "A4": A4, "pagina": pagina, "mm": mm, "largura": largura, "fonte": fonte, "colors": colors,
        "est_titulo": est_titulo, "est_sub": est_sub, "Spacer": Spacer, "Table": Table, "TableStyle": TableStyle,
        "Paragraph": Paragraph, "txt": txt, "P": P, "H": H, "campo": campo, "secao": secao, "tabela": tabela,
        "azul": azul,
    }


def _cabecalho_pdf(k, titulo, subtitulo):
    """Cabeçalho com logos (esquerda.png / direita.png, se existirem na pasta do programa)."""
    from reportlab.platypus import Image as RLImage
    mm = k["mm"]

    def logo(nome, alinhamento):
        try:
            with Image.open(nome) as im:
                w, h = im.size
            altura = 13 * mm
            return RLImage(nome, width=altura * w / h, height=altura, hAlign=alinhamento)
        except Exception:
            return ""

    topo = k["Table"]([[logo("esquerda.png", "LEFT"),
                        [k["Paragraph"](titulo[0], k["est_titulo"]), k["Paragraph"](titulo[1], k["est_titulo"]),
                         k["Paragraph"](subtitulo, k["est_sub"])],
                        logo("direita.png", "RIGHT")]],
                      colWidths=[40 * mm, k["largura"] - 80 * mm, 40 * mm])
    topo.setStyle(k["TableStyle"]([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("LINEBELOW", (0, 0), (-1, 0), 1.5, k["azul"]),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return topo


def _gravar_pdf(k, story, caminho, titulo_doc, rodape_esq, landscape_pagina=False):
    from reportlab.platypus import SimpleDocTemplate
    mm = k["mm"]
    colors = k["colors"]
    fonte = k["fonte"]
    A4 = k["pagina"]

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont(fonte, 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(12 * mm, 8 * mm, rodape_esq + "  |  Generated on " + data_hora_atual()
                          + "  |  Batch Control for DUNE")
        canvas.drawRightString(A4[0] - 12 * mm, 8 * mm, "Page " + str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(caminho, pagesize=k["pagina"], leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=15 * mm, title=titulo_doc,
                            author="Batch Control for DUNE")
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)


def gerar_pdf_lote(registro_id, caminho):
    """PDF de arquivo com tudo o que foi registrado para o lote OPTO (e suas caixas/lotes internos)."""
    k = _kit_pdf()
    P, H, campo, secao, tabela, Spacer = k["P"], k["H"], k["campo"], k["secao"], k["tabela"], k["Spacer"]

    cursor.execute("""
        SELECT tracking_id, lote_geral, data_recebimento, responsavel, fornecedor, total_filtros,
               numero_caixas_menores, capacidade_caixa_menor, material, dimensoes, espessura, tipo_acabamento,
               filtros_quebrados, quantidade_confere, procedimento_limpeza, resultado_inspecao, arquivo_controle,
               observacoes, qr_code_path, qrcodes_caixas_dir, data_hora_registro, lote_fornecedor
        FROM lotes WHERE id = ?
    """, (registro_id,))
    r = cursor.fetchone()
    if r is None:
        raise ValueError("Batch not found")
    (tracking, opto, chegada, resp, empresa, total, n_caixas, capacidade, material, dimensoes, espessura,
     acabamento, quebrados, confere, limpeza_ok, resultado, arquivo, obs, qr_path, qr_dir, registrado, forn_legado) = r

    story = [_cabecalho_pdf(k, ("DUNE HD – X-ARAPUCA PTP FILMS", "OPTO BATCH ARRIVAL RECORD"),
                            "Registered data of the batch received from OPTO"), Spacer(1, 6)]

    story += [secao("1. OPTO BATCH INFORMATION"), Spacer(1, 3)]
    linhas = [
        [campo("OPTO BATCH", opto), campo("TRACKING ID", tracking)],
        [campo("SUPPLIER / COMPANY", empresa), campo("ARRIVAL DATE", chegada)],
        [campo("RESPONSIBLE", resp), campo("RECORDED", registrado)],
        [campo("TOTAL FILTERS", total), campo("SMALL BOXES", n_caixas)],
        [campo("SMALL BOX CAPACITY (filters per box)", capacidade), (campo("SUPPLIER BATCH (old records)", forn_legado) if forn_legado else "")],
    ]
    story.append(tabela(linhas, [93, 93], cabecalho=False))

    story += [Spacer(1, 6), secao("2. SUBSTRATE INFORMATION"), Spacer(1, 3)]
    story.append(tabela([[campo("MATERIAL", material), campo("DIMENSIONS", dimensoes)],
                         [campo("THICKNESS", espessura), campo("FINISHING TYPE", acabamento)]],
                        [93, 93], cabecalho=False))

    story += [Spacer(1, 6), secao("3. ARRIVAL INSPECTION"), Spacer(1, 3)]
    story.append(tabela([[campo("BROKEN FILTERS?", quebrados), campo("QUANTITY MATCHES SUPPLIER?", confere)],
                         [campo("CLEANING PROCEDURE VERIFIED?", limpeza_ok), campo("INSPECTION RESULT", resultado)]],
                        [93, 93], cabecalho=False))

    story += [Spacer(1, 6), secao("4. INTERNAL LOTS (SMALL BOXES)"), Spacer(1, 3)]
    cursor.execute("SELECT numero_caixa, codigo_interno, quantidade_filtros, observacoes FROM lotes_internos "
                   "WHERE id_lote = ? ORDER BY numero_caixa", (registro_id,))
    internos = cursor.fetchall()
    linhas_i = [[H("Box"), H("OPTO Batch"), H("Internal Lot"), H("Filters"), H("Notes")]]
    for caixa, codigo, filtros, nota in internos:
        linhas_i.append([P(str(caixa).zfill(2)), P(opto), P(codigo), P(filtros), P(nota)])
    if len(linhas_i) == 1:
        linhas_i.append([P("-")] * 5)
    soma = 0
    for _, _, filtros, _ in internos:
        soma += int(filtros) if str(filtros or "").isdigit() else 0
    story.append(tabela(linhas_i, [14, 50, 45, 25, 52]))
    story.append(Spacer(1, 2))
    story.append(P("Registered: " + str(len(internos)) + " of " + str(n_caixas or 0) + " small boxes  |  filters in the "
                   "registered boxes: " + str(soma)))

    story += [Spacer(1, 6), secao("5. TRACEABILITY AND NOTES"), Spacer(1, 3)]
    story.append(tabela([[campo("SUPPLIER CONTROL FILE", arquivo), ""],
                         [campo("BATCH QR CODE FILE", qr_path), ""],
                         [campo("SMALL BOX QR CODES FOLDER", qr_dir), ""],
                         [campo("OBSERVATIONS", obs), ""]],
                        [93, 93], cabecalho=False,
                        extra=[("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1)),
                               ("SPAN", (0, 2), (1, 2)), ("SPAN", (0, 3), (1, 3))]))

    _gravar_pdf(k, story, caminho, "OPTO batch record - " + str(opto), "OPTO batch " + str(opto))
    return caminho


def imprimir_relatorio_lote():
    """Gera o PDF do lote selecionado na tabela e abre no visualizador."""
    selecionado = tabela.selection()
    if not selecionado:
        messagebox.showwarning("Warning", "Select a record in the table to print.")
        return
    if not _pdf_disponivel():
        return
    id_reg = int(tabela.item(selecionado[0], "values")[0])
    cursor.execute("SELECT lote_geral FROM lotes WHERE id = ?", (id_reg,))
    row = cursor.fetchone()
    if row is None:
        messagebox.showwarning("Warning", "Record not found.")
        return
    nome = re.sub(r"[^A-Za-z0-9_.-]", "_", str(row[0] or "batch"))
    os.makedirs(PASTA_PDF, exist_ok=True)
    caminho = os.path.join(PASTA_PDF, "Batch_" + nome + "_id" + str(id_reg) + ".pdf")
    try:
        gerar_pdf_lote(id_reg, caminho)
    except PermissionError:
        messagebox.showerror("PDF", "Could not write the file. Close the PDF if it is open and try again:\n"
                             + os.path.abspath(caminho))
        return
    except Exception as erro:
        messagebox.showerror("PDF", "Could not generate the PDF:\n" + str(erro))
        return
    webbrowser.open(Path(caminho).resolve().as_uri())
    messagebox.showinfo("PDF", "Report saved at:\n" + os.path.abspath(caminho))


# ===============================
# LIMPEZA LEPTONS (lotes de material reprocessado)
# ===============================
RESULTADOS_LIMPEZA = ["Approved", "Approved with observations", "Rejected", "Under inspection"]


def proximo_numero_limpeza():
    cursor.execute("SELECT codigo_interno FROM lotes_limpeza")
    maior = 0
    for (codigo,) in cursor.fetchall():
        m = re.fullmatch(re.escape(PREFIXO_LIMPEZA) + r"(\d+)", str(codigo or "").strip(), flags=re.IGNORECASE)
        if m:
            maior = max(maior, int(m.group(1)))
    return str(maior + 1).zfill(DIGITOS_CAIXA)


def gerar_pdf_limpeza(caminho):
    """PDF de arquivo com a lista de todos os lotes de limpeza do Leptons."""
    k = _kit_pdf(landscape_pagina=True)
    P, H, secao, tabela, Spacer = k["P"], k["H"], k["secao"], k["tabela"], k["Spacer"]
    cursor.execute("""
        SELECT codigo_interno, data_limpeza, responsavel, quantidade_filtros, origem, remocao_ptp,
               procedimento, resultado, observacoes
        FROM lotes_limpeza ORDER BY id
    """)
    linhas = [[H("Cleaning lot"), H("Date"), H("Responsible"), H("Filters"), H("Origin"), H("PTP removed"),
               H("Procedure"), H("Result"), H("Notes")]]
    for r in cursor.fetchall():
        linhas.append([P(x) for x in r])
    if len(linhas) == 1:
        linhas.append([P("-")] * 9)
    story = [_cabecalho_pdf(k, ("DUNE HD – X-ARAPUCA PTP FILMS", "LEPTONS CLEANING LOTS"),
                            "Material cleaned again at Leptons Lab after PTP removal"), Spacer(1, 6),
             secao("CLEANING LOTS (internal lots selectable in the deposition program)"), Spacer(1, 3),
             tabela(linhas, [28, 20, 28, 14, 50, 20, 46, 26, 35])]
    _gravar_pdf(k, story, caminho, "Leptons cleaning lots", "Leptons cleaning lots", landscape_pagina=True)
    return caminho


def abrir_limpeza_leptons():
    """Cadastro dos lotes de limpeza realizada no Leptons (viram lotes internos para a deposição)."""
    fundo = "#f4f6f8"
    win = tk.Toplevel(janela)
    win.title("Leptons Cleaning Lots")
    win.geometry("1150x720")
    win.configure(bg=fundo)
    win.transient(janela)

    editando = {"id": None}
    v = {nome: tk.StringVar() for nome in ("num", "data", "resp", "filtros", "origem", "ptp", "proc", "resultado", "obs")}

    tk.Label(win, bg=fundo, anchor="w", justify="left", wraplength=1100, fg="#424242",
             text=("Material that went through PTP removal and a new cleaning at Leptons Lab. Each cleaning lot becomes an "
                   f"internal lot ({PREFIXO_LIMPEZA}000X) that can be chosen in the deposition program.")
             ).pack(fill="x", padx=14, pady=(10, 4))

    form = tk.LabelFrame(win, text="Cleaning lot", bg=fundo, font=("Segoe UI", 10, "bold"), padx=12, pady=8)
    form.pack(fill="x", padx=12, pady=4)

    def rot(r, c, texto):
        tk.Label(form, text=texto, bg=fundo, font=("Segoe UI", 9, "bold")).grid(row=r, column=c, sticky="e", padx=(0, 6), pady=3)

    rot(0, 0, "Cleaning lot code:")
    cel = tk.Frame(form, bg=fundo)
    cel.grid(row=0, column=1, sticky="w")
    tk.Label(cel, text=PREFIXO_LIMPEZA, bg=fundo, font=("Segoe UI", 10, "bold")).pack(side="left")
    tk.Entry(cel, textvariable=v["num"], width=8, justify="center").pack(side="left")
    rot(0, 2, "Cleaning date:")
    tk.Entry(form, textvariable=v["data"], width=16).grid(row=0, column=3, sticky="w")
    rot(0, 4, "Responsible:")
    tk.Entry(form, textvariable=v["resp"], width=24).grid(row=0, column=5, sticky="w")

    rot(1, 0, "Number of filters:")
    tk.Entry(form, textvariable=v["filtros"], width=10, justify="center").grid(row=1, column=1, sticky="w")
    rot(1, 2, "PTP removed?")
    cel_ptp = tk.Frame(form, bg=fundo)
    cel_ptp.grid(row=1, column=3, sticky="w")
    for op in ("Yes", "No"):
        tk.Radiobutton(cel_ptp, text=op, value=op, variable=v["ptp"], bg=fundo, activebackground=fundo).pack(side="left")
    rot(1, 4, "Result after cleaning:")
    ttk.Combobox(form, textvariable=v["resultado"], values=RESULTADOS_LIMPEZA, state="readonly", width=26).grid(
        row=1, column=5, sticky="w")

    rot(2, 0, "Origin (previous PID / lot):")
    tk.Entry(form, textvariable=v["origem"], width=60).grid(row=2, column=1, columnspan=3, sticky="w")
    rot(3, 0, "Cleaning procedure:")
    tk.Entry(form, textvariable=v["proc"], width=60).grid(row=3, column=1, columnspan=3, sticky="w")
    rot(4, 0, "Notes:")
    tk.Entry(form, textvariable=v["obs"], width=60).grid(row=4, column=1, columnspan=3, sticky="w")

    botoes = tk.Frame(win, bg=fundo)
    botoes.pack(fill="x", padx=12, pady=6)
    btn_salvar = tk.Button(botoes, text="Save", bg="#2e7d32", fg="white", width=14)
    btn_salvar.pack(side="left", padx=4)

    colunas_t = ("ID", "Cleaning lot", "Date", "Responsible", "Filters", "Origin", "PTP removed", "Procedure", "Result", "Notes")
    larguras = (35, 110, 85, 110, 55, 190, 80, 170, 120, 130)
    tab = ttk.Treeview(win, columns=colunas_t, show="headings", height=12, selectmode="browse")
    for c, w in zip(colunas_t, larguras):
        tab.heading(c, text=c)
        tab.column(c, anchor="center", width=w)

    def carregar_tabela():
        for i in tab.get_children():
            tab.delete(i)
        cursor.execute("""
            SELECT id, codigo_interno, data_limpeza, responsavel, quantidade_filtros, origem, remocao_ptp,
                   procedimento, resultado, observacoes
            FROM lotes_limpeza ORDER BY id DESC
        """)
        for row in cursor.fetchall():
            tab.insert("", "end", values=["" if x is None else x for x in row])

    def novo():
        editando["id"] = None
        v["num"].set(proximo_numero_limpeza())
        v["data"].set(data_atual())
        for chave in ("resp", "filtros", "origem", "proc", "obs"):
            v[chave].set("")
        v["ptp"].set("Yes")
        v["resultado"].set("Under inspection")
        btn_salvar.config(text="Save")
        tab.selection_remove(*tab.selection())

    def ao_selecionar(event=None):
        sel = tab.selection()
        if not sel:
            return
        valores = tab.item(sel[0], "values")
        editando["id"] = int(valores[0])
        numero = re.sub(r"^" + re.escape(PREFIXO_LIMPEZA), "", valores[1], flags=re.IGNORECASE)
        v["num"].set(numero)
        for chave, valor in zip(("data", "resp", "filtros", "origem", "ptp", "proc", "resultado", "obs"), valores[2:10]):
            v[chave].set(valor)
        btn_salvar.config(text="Update")

    def salvar_limpeza():
        numero = v["num"].get().strip()
        if not numero.isdigit():
            messagebox.showwarning("Warning", f"Type only the number of the cleaning lot (e.g. 0001).", parent=win)
            return
        codigo = PREFIXO_LIMPEZA + numero.zfill(DIGITOS_CAIXA)
        if not v["data"].get().strip() or not v["resp"].get().strip():
            messagebox.showwarning("Warning", "Enter the cleaning date and the responsible.", parent=win)
            return
        filtros = v["filtros"].get().strip()
        if not filtros.isdigit() or int(filtros) < 1:
            messagebox.showwarning("Warning", "Number of filters must be an integer greater than zero.", parent=win)
            return
        if not v["resultado"].get().strip():
            messagebox.showwarning("Warning", "Select the result after cleaning.", parent=win)
            return
        cursor.execute("SELECT id FROM lotes_limpeza WHERE lower(codigo_interno) = lower(?) AND id IS NOT ?",
                       (codigo, editando["id"]))
        if cursor.fetchone():
            messagebox.showwarning("Warning", f"The cleaning lot {codigo} already exists.", parent=win)
            return
        valores = (codigo, v["data"].get().strip(), v["resp"].get().strip(), filtros, v["origem"].get().strip(),
                   v["ptp"].get(), v["proc"].get().strip(), v["resultado"].get().strip(), v["obs"].get().strip())
        if editando["id"] is None:
            cursor.execute("""
                INSERT INTO lotes_limpeza (codigo_interno, data_limpeza, responsavel, quantidade_filtros, origem,
                                           remocao_ptp, procedimento, resultado, observacoes, data_hora_registro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, valores + (data_hora_atual(),))
        else:
            cursor.execute("""
                UPDATE lotes_limpeza
                SET codigo_interno = ?, data_limpeza = ?, responsavel = ?, quantidade_filtros = ?, origem = ?,
                    remocao_ptp = ?, procedimento = ?, resultado = ?, observacoes = ?
                WHERE id = ?
            """, valores + (editando["id"],))
        conn.commit()
        messagebox.showinfo("Success", f"Cleaning lot {codigo} saved.", parent=win)
        carregar_tabela()
        novo()

    def excluir_limpeza():
        sel = tab.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a cleaning lot in the table to delete.", parent=win)
            return
        valores = tab.item(sel[0], "values")
        if messagebox.askyesno("Confirm deletion", f"Delete cleaning lot {valores[1]}?\n"
                               "Depositions that already used it keep the code in their records.", parent=win):
            cursor.execute("DELETE FROM lotes_limpeza WHERE id = ?", (int(valores[0]),))
            conn.commit()
            carregar_tabela()
            novo()

    def imprimir_lista():
        if not _pdf_disponivel():
            return
        os.makedirs(PASTA_PDF, exist_ok=True)
        caminho = os.path.join(PASTA_PDF, "Leptons_cleaning_lots.pdf")
        try:
            gerar_pdf_limpeza(caminho)
        except PermissionError:
            messagebox.showerror("PDF", "Could not write the file. Close the PDF if it is open and try again:\n"
                                 + os.path.abspath(caminho), parent=win)
            return
        except Exception as erro:
            messagebox.showerror("PDF", "Could not generate the PDF:\n" + str(erro), parent=win)
            return
        webbrowser.open(Path(caminho).resolve().as_uri())
        messagebox.showinfo("PDF", "Report saved at:\n" + os.path.abspath(caminho), parent=win)

    btn_salvar.config(command=salvar_limpeza)
    tk.Button(botoes, text="New", command=novo, width=12).pack(side="left", padx=4)
    tk.Button(botoes, text="Delete selected", command=excluir_limpeza, bg="#c62828", fg="white", width=16).pack(side="left", padx=4)
    tk.Button(botoes, text="Print list (PDF)", command=imprimir_lista, width=16).pack(side="left", padx=4)
    tk.Button(botoes, text="Close", command=win.destroy, width=12).pack(side="right", padx=4)

    tab.pack(fill="both", expand=True, padx=12, pady=(4, 12))
    tab.bind("<<TreeviewSelect>>", ao_selecionar)
    carregar_tabela()
    novo()


# ===============================
# JANELA PRINCIPAL
# ===============================
# ---------------------------------------------------------------------------
# BACKUP AUTOMÁTICO (semanal) dos bancos de dados
# ---------------------------------------------------------------------------
PASTA_BACKUP = "backups"        # pasta local onde ficam as cópias (criada ao lado dos bancos)
DIAS_ENTRE_BACKUPS = 7          # intervalo mínimo entre backups
BACKUPS_MANTIDOS = 12           # quantas cópias de cada banco manter (as mais antigas são removidas)
BANCOS_BACKUP = ("lotes.db", "rastreabilidade.db")


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
            erros.append(banco + ": " + str(e))
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
        for antigo in _datas_backups(prefixo)[BACKUPS_MANTIDOS:]:
            try:
                os.remove(antigo)
            except Exception:
                pass
    return criados, erros


INDICES_BANCO = {
    "rastreabilidade.db": [("massa_posicoes", "id_tarefa"), ("inspecao_visual_cab", "id_tarefa"),
                           ("inspecao_visual_filtros", "id_tarefa"), ("imersao_massas", "id_tarefa"),
                           ("imersao_itens", "id_tarefa"), ("tarefa_lotes", "id_tarefa"),
                           ("eficiencia_teste", "id_tarefa"), ("eficiencia_amostras", "id_tarefa")],
    "lotes.db": [("lotes_internos", "id_lote")],
}


def criar_indices():
    """Índices nas colunas de ligação: mantêm listas e relatórios rápidos com muitos registros."""
    for banco, lista in INDICES_BANCO.items():
        if not os.path.exists(banco):
            continue
        con = None
        try:
            con = sqlite3.connect(banco, timeout=30)
            for tabela_, col in lista:
                try:
                    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{tabela_}_{col} ON {tabela_}({col})")
                except sqlite3.Error:
                    pass          # tabela ainda não existe neste banco
            con.commit()
        except Exception:
            pass
        finally:
            if con is not None:
                con.close()


def backup_ao_abrir():
    """Chamado ao abrir o programa: faz o backup semanal e avisa só se algo falhar."""
    criar_indices()
    try:
        _, erros = fazer_backup()
    except Exception as e:
        erros = [str(e)]
    if erros:
        messagebox.showwarning("Backup", "Não foi possível concluir o backup automático:\n\n" + "\n".join(erros))


janela = tk.Tk()
janela.title("Arrival Batch Control System - OPTO / DUNE")
janela.geometry("1600x850")

# ===============================
# INTERFACE
# ===============================
frame_cad = tk.LabelFrame(janela, text="General Batch Registration", padx=10, pady=10)
frame_cad.pack(fill="x", padx=10, pady=5)

frame_cad.columnconfigure(0, weight=1)
frame_cad.columnconfigure(1, weight=1)

lbl_relogio = tk.Label(frame_cad, text="", font=("Segoe UI", 10, "bold"))
lbl_relogio.grid(row=0, column=0, sticky="w", padx=5, pady=(0, 8))

lbl_modo = tk.Label(frame_cad, text="New record", font=("Segoe UI", 10, "bold"), fg="#1565c0")
lbl_modo.grid(row=0, column=1, sticky="e", padx=5, pady=(0, 8))

# -------- LOTE GERAL --------
frame_lote = tk.LabelFrame(frame_cad, text="General OPTO Batch Information", padx=10, pady=10)
frame_lote.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

labels_entries = [
    ("OPTO Batch (General Batch ID)", "entry_lote_geral"),
    ("Arrival Date", "entry_data"),
    ("Responsible", "entry_resp"),
    ("Supplier / Company", "entry_fornecedor"),
    ("Total Number of Filters (calculated)", "entry_total_filtros"),
]

entry_lote_geral = tk.Entry(frame_lote, width=28)
entry_lote_fornecedor = tk.Entry(frame_lote, width=28)   # oculto: guarda o valor antigo; agora é registrado por caixa
entry_data = tk.Entry(frame_lote, width=28)
entry_resp = tk.Entry(frame_lote, width=28)
entry_fornecedor = tk.Entry(frame_lote, width=28)
entry_total_filtros = tk.Entry(frame_lote, width=28)

entries = [entry_lote_geral, entry_data, entry_resp, entry_fornecedor, entry_total_filtros]
for idx, ((label, _), entry) in enumerate(zip(labels_entries, entries)):
    tk.Label(frame_lote, text=label).grid(row=idx, column=0, sticky="e", padx=5, pady=3)
    entry.grid(row=idx, column=1, sticky="w", padx=5, pady=3)

entry_total_filtros.config(state="readonly")

# -------- CAIXAS MENORES --------
frame_caixas = tk.LabelFrame(frame_cad, text="Small Boxes Inside the General Batch", padx=10, pady=10)
frame_caixas.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

tk.Label(frame_caixas, text="Small Box Capacity (filters per box)").grid(row=0, column=0, sticky="e", padx=5, pady=3)
entry_capacidade_caixa = tk.Entry(frame_caixas, width=18)
entry_capacidade_caixa.grid(row=0, column=1, sticky="w", padx=5, pady=3)
entry_capacidade_caixa.insert(0, str(SMALL_BOX_CAPACITY))
entry_capacidade_caixa.config(state="normal")
entry_capacidade_caixa.bind("<KeyRelease>", calcular_caixas_menores)

tk.Label(frame_caixas, text="Number of Small Boxes in the Batch").grid(row=1, column=0, sticky="e", padx=5, pady=3)
entry_numero_caixas = tk.Entry(frame_caixas, width=18)
entry_numero_caixas.grid(row=1, column=1, sticky="w", padx=5, pady=3)

entry_numero_caixas.bind("<KeyRelease>", calcular_caixas_menores)

# ícone/botão que abre o registro dos lotes internos (habilita quando há caixas)
btn_lotes_internos = tk.Button(
    frame_caixas, text="\U0001F4E6 Register internal lots", command=abrir_lotes_internos,
    bg="#1565c0", fg="white", state="disabled"
)
btn_lotes_internos.grid(row=1, column=2, sticky="w", padx=(12, 5), pady=3)
lbl_lotes_internos = tk.Label(frame_caixas, text="Internal lots: --", fg="#757575", font=("Segoe UI", 9, "bold"))
lbl_lotes_internos.grid(row=2, column=2, sticky="w", padx=(12, 5))

tk.Button(frame_caixas, text="Recalculate (capacity x boxes)", command=recalcular_do_zero).grid(row=2, column=0, columnspan=2, pady=6)
lbl_calculo = tk.Label(frame_caixas, text="Small boxes: --", fg="#1565c0", font=("Segoe UI", 9, "bold"))
lbl_calculo.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

tk.Label(
    frame_caixas,
    text="Total filters = capacity x number of small boxes (editable per box in the internal lots window).\nEach small box is registered as DUNE-CX-000X (internal lot) under the OPTO batch.",
    justify="left",
    fg="#424242"
).grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=8)

# -------- SUBSTRATO E INSPEÇÃO --------
frame_mid = tk.Frame(janela)
frame_mid.pack(fill="x", padx=10, pady=5)
frame_mid.columnconfigure(0, weight=1)
frame_mid.columnconfigure(1, weight=1)
frame_mid.columnconfigure(2, weight=1)

frame_substrato = tk.LabelFrame(frame_mid, text="Substrate Information", padx=10, pady=10)
frame_substrato.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

tk.Label(frame_substrato, text="Material").grid(row=0, column=0, sticky="e", padx=5, pady=3)
entry_material = tk.Entry(frame_substrato, width=25)
entry_material.grid(row=0, column=1, sticky="w", padx=5, pady=3)
entry_material.insert(0, "Filter substrate")

tk.Label(frame_substrato, text="Dimensions").grid(row=1, column=0, sticky="e", padx=5, pady=3)
entry_dimensoes = tk.Entry(frame_substrato, width=25)
entry_dimensoes.grid(row=1, column=1, sticky="w", padx=5, pady=3)
entry_dimensoes.insert(0, "100 x 77 mm")

tk.Label(frame_substrato, text="Thickness").grid(row=2, column=0, sticky="e", padx=5, pady=3)
entry_espessura = tk.Entry(frame_substrato, width=25)
entry_espessura.grid(row=2, column=1, sticky="w", padx=5, pady=3)
entry_espessura.insert(0, "1 mm")

tk.Label(frame_substrato, text="Finishing Type").grid(row=3, column=0, sticky="e", padx=5, pady=3)
combo_acabamento = ttk.Combobox(frame_substrato, width=22, state="readonly", values=["Raw", "Lapped", "Polished", "Other"])
combo_acabamento.grid(row=3, column=1, sticky="w", padx=5, pady=3)
combo_acabamento.set("Polished")

frame_inspecao = tk.LabelFrame(frame_mid, text="Arrival Inspection", padx=10, pady=10)
frame_inspecao.grid(row=0, column=1, sticky="nsew", padx=8)

var_filtros_quebrados = tk.StringVar(value="No")
var_quantidade_confere = tk.StringVar(value="Yes")
var_procedimento_limpeza = tk.StringVar(value="Yes")

tk.Label(frame_inspecao, text="Broken filters?").grid(row=0, column=0, sticky="w", pady=4)
tk.Radiobutton(frame_inspecao, text="Yes", variable=var_filtros_quebrados, value="Yes").grid(row=0, column=1, sticky="w")
tk.Radiobutton(frame_inspecao, text="No", variable=var_filtros_quebrados, value="No").grid(row=0, column=2, sticky="w")

tk.Label(frame_inspecao, text="Quantity matches supplier?").grid(row=1, column=0, sticky="w", pady=4)
tk.Radiobutton(frame_inspecao, text="Yes", variable=var_quantidade_confere, value="Yes").grid(row=1, column=1, sticky="w")
tk.Radiobutton(frame_inspecao, text="No", variable=var_quantidade_confere, value="No").grid(row=1, column=2, sticky="w")

tk.Label(frame_inspecao, text="Cleaning procedure verified?").grid(row=2, column=0, sticky="w", pady=4)
tk.Radiobutton(frame_inspecao, text="Yes", variable=var_procedimento_limpeza, value="Yes").grid(row=2, column=1, sticky="w")
tk.Radiobutton(frame_inspecao, text="No", variable=var_procedimento_limpeza, value="No").grid(row=2, column=2, sticky="w")

tk.Label(frame_inspecao, text="Inspection Result").grid(row=3, column=0, sticky="w", pady=4)
combo_resultado_inspecao = ttk.Combobox(frame_inspecao, width=28, state="readonly", values=["Approved", "Approved with observations", "Rejected", "Under inspection"])
combo_resultado_inspecao.grid(row=3, column=1, columnspan=2, sticky="w")
combo_resultado_inspecao.set("Approved")

frame_doc = tk.LabelFrame(frame_mid, text="Traceability Document", padx=10, pady=10)
frame_doc.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

tk.Label(frame_doc, text="Supplier Control File").grid(row=0, column=0, sticky="w", pady=3)
entry_arquivo = tk.Entry(frame_doc, width=45)
entry_arquivo.grid(row=1, column=0, columnspan=2, sticky="we", pady=3)

tk.Button(frame_doc, text="Upload/Browse file", command=selecionar_arquivo_controle).grid(row=2, column=0, sticky="w", pady=5)
tk.Button(frame_doc, text="Open selected file", command=abrir_arquivo_controle).grid(row=2, column=1, sticky="w", pady=5)
tk.Button(frame_doc, text="Open General Batch QR", command=abrir_qrcode_selecionado).grid(row=3, column=0, sticky="w", pady=5)
tk.Button(frame_doc, text="Open Small-Box QR Folder", command=abrir_qrcodes_caixas_selecionado).grid(row=3, column=1, sticky="w", pady=5)

# -------- OBSERVAÇÕES --------
frame_obs = tk.LabelFrame(janela, text="Observations", padx=10, pady=10)
frame_obs.pack(fill="x", padx=10, pady=5)
txt_obs = tk.Text(frame_obs, height=4, font=("Segoe UI", 9), bd=1, relief="solid")
txt_obs.pack(fill="x", expand=False)

# -------- BOTÕES --------
frame_buttons = tk.Frame(janela)
frame_buttons.pack(fill="x", padx=10, pady=5)

btn_save = tk.Button(frame_buttons, text="Save", command=salvar, bg="#2e7d32", fg="white", width=16)
btn_save.pack(side="left", padx=5)
tk.Button(frame_buttons, text="Clear", command=limpar, width=16).pack(side="left", padx=5)
tk.Button(frame_buttons, text="Edit Selected", command=carregar_para_edicao, bg="#1565c0", fg="white", width=16).pack(side="left", padx=5)
tk.Button(frame_buttons, text="Delete", command=excluir_selecionado, bg="#c62828", fg="white", width=16).pack(side="left", padx=5)
tk.Button(frame_buttons, text="Print report (PDF)", command=imprimir_relatorio_lote, width=18).pack(side="left", padx=(25, 5))
tk.Button(frame_buttons, text="Leptons Cleaning", command=abrir_limpeza_leptons, bg="#6a1b9a", fg="white", width=18).pack(side="left", padx=5)

# -------- BUSCA ----------
frame_busca = tk.LabelFrame(janela, text="Batch Search", padx=10, pady=10)
frame_busca.pack(fill="x", padx=10, pady=5)

entry_busca = tk.Entry(frame_busca, width=40)
entry_busca.pack(side="left", padx=5)
tk.Button(frame_busca, text="Search", command=buscar).pack(side="left", padx=5)
tk.Button(frame_busca, text="Show All", command=atualizar_tabela).pack(side="left", padx=5)
tk.Button(frame_busca, text="Export CSV", command=exportar_csv).pack(side="right", padx=5)

# -------- TABELA ----------
frame_tabela = tk.Frame(janela)
frame_tabela.pack(fill="both", expand=True, padx=10, pady=10)

colunas = (
    "ID", "Tracking ID", "OPTO Batch", "Supplier",
    "Total Filters", "Small Boxes", "Internal Lots", "Arrival Date", "Responsible",
    "Inspection", "Record Date/Time"
)
tabela = ttk.Treeview(frame_tabela, columns=colunas, show="headings")

larguras = {
    "ID": 60,
    "Tracking ID": 150,
    "OPTO Batch": 160,
    "Supplier": 110,
    "Total Filters": 110,
    "Small Boxes": 110,
    "Internal Lots": 110,
    "Arrival Date": 110,
    "Responsible": 140,
    "Inspection": 170,
    "Record Date/Time": 150,
}

for col in colunas:
    tabela.heading(col, text=col)
    tabela.column(col, anchor="center", width=larguras.get(col, 120))

tabela.pack(fill="both", expand=True)

# Inicialização
limpar()
atualizar_relogio()
atualizar_tabela()

janela.after(500, backup_ao_abrir)
janela.mainloop()
