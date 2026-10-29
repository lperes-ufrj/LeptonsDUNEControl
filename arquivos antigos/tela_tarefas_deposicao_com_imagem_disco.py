from tkinter import filedialog
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import qrcode
import os
import subprocess
import sys
from PIL import Image, ImageTk

# =====================================================
# CONFIGURAÇÕES
# =====================================================
DB_TAREFAS = "rastreabilidade.db"
DB_LOTES = "lotes.db"  # banco gerado pelo programa de controle de lotes
PROGRAMA_LOTES = "controle_lotes_chegada_opto_v5_qr_caixas_07-05-26.py"
AREA_FILTRO_MM2 = 77.00 * 100.00
AREA_FILTRO_CM2 = AREA_FILTRO_MM2 / 100.0
DISCO_EVAPORACAO_IMG = "disco_evaporacao.jpg"

anexos_lista = []
tarefa_em_edicao_id = None

# =====================================================
# BANCO DE DADOS
# =====================================================
def conectar():
    return sqlite3.connect(DB_TAREFAS)


def conectar_lotes():
    return sqlite3.connect(DB_LOTES)


def coluna_existe(cur, tabela, coluna):
    cur.execute(f"PRAGMA table_info({tabela})")
    return coluna in [c[1] for c in cur.fetchall()]


def adicionar_coluna_se_precisar(cur, tabela, coluna, tipo):
    if not coluna_existe(cur, tabela, coluna):
        cur.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def inicializar_banco():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_tarefa TEXT,
            responsavel TEXT,
            data_inicio TEXT,
            status TEXT,
            descricao TEXT,
            lote_entrada_id INTEGER,
            codigo_lote TEXT,
            position_range TEXT,
            observacoes TEXT,
            anexos_txt TEXT,
            eficiencia_optica_ok TEXT,
            valor_eficiencia TEXT,
            imersao_criogenica_ok TEXT,
            data_hora_registro TEXT,
            massa_ptp_g TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS massa_posicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            posicao INTEGER,
            massa_antes TEXT,
            massa_depois TEXT,
            densidade_massa_ug_cm2 TEXT
        )
    """)

    # Migração para bancos já existentes
    for coluna, tipo in [
        ("codigo_lote", "TEXT"),
        ("eficiencia_optica_ok", "TEXT"),
        ("valor_eficiencia", "TEXT"),
        ("imersao_criogenica_ok", "TEXT"),
        ("data_hora_registro", "TEXT"),
        ("anexos_txt", "TEXT"),
        ("position_range", "TEXT"),
        ("observacoes", "TEXT"),
        ("massa_ptp_g", "TEXT"),
    ]:
        adicionar_coluna_se_precisar(cur, "tarefas", coluna, tipo)

    adicionar_coluna_se_precisar(cur, "massa_posicoes", "densidade_massa_ug_cm2", "TEXT")

    conn.commit()
    conn.close()


def carregar_lotes():
    """Carrega os lotes do banco do sistema de chegada.

    Retorna sempre tuplas no formato:
    (id, internal_lab_batch, arrival_date, company, tracking_compat,
     company_batch, total_filters, small_boxes, inspection_result, arquivo_controle)
    """
    if not os.path.exists(DB_LOTES):
        return []

    try:
        conn = conectar_lotes()
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(lotes)")
        colunas = [c[1] for c in cur.fetchall()]
        mapa = {c.lower(): c for c in colunas}

        def col(*nomes):
            for nome in nomes:
                if nome.lower() in mapa:
                    return mapa[nome.lower()]
            return None

        c_id = col("id")
        c_internal_lab_batch = col(
            "lote_geral", "lote", "batch", "internal_lab_batch", "lote_interno",
            "general_batch", "tracking_id"
        )
        c_arrival_date = col(
            "data_recebimento", "data", "arrival_date", "data_chegada", "receiving_date",
            "date", "data_hora_registro"
        )
        c_company = col("Fornecedor", "fornecedor", "supplier", "producer", "company")
        c_tracking = col("tracking_id", "tracking", "codigo_rastreio")
        c_company_batch = col(
            "lote_fornecedor", "supplier_batch", "company_batch", "opto_batch",
            "lote_empresa"
        )
        c_total_filters = col(
            "total_filtros", "total_filters", "Quantidade",
            "quantidade", "quantity", "quantity_received"
        )
        c_small_boxes = col(
            "numero_caixas_menores", "small_boxes", "number_of_small_boxes", "caixas_menores",
            "small_boxes_count", "box_quantity"
        )
        c_inspection = col("resultado_inspecao", "inspection_result", "status_inspecao", "inspection_status")
        c_arquivo = col("arquivo_controle", "control_file", "supplier_control_file")

        aliases = [
            ("id", c_id),
            ("internal_lab_batch", c_internal_lab_batch),
            ("arrival_date", c_arrival_date),
            ("company", c_company),
            ("tracking_compat", c_tracking),
            ("company_batch", c_company_batch),
            ("total_filters", c_total_filters),
            ("small_boxes", c_small_boxes),
            ("inspection_result", c_inspection),
            ("arquivo_controle", c_arquivo),
        ]

        select_cols = []
        for alias, coluna_real in aliases:
            if coluna_real:
                select_cols.append(f'"{coluna_real}" AS "{alias}"')
            else:
                select_cols.append(f'NULL AS "{alias}"')

        order_col = c_id if c_id else c_arrival_date
        sql = f"SELECT {', '.join(select_cols)} FROM lotes"
        if order_col:
            sql += f' ORDER BY "{order_col}" DESC'

        cur.execute(sql)
        dados = cur.fetchall()
        conn.close()
        return dados

    except Exception as e:
        mensagem = "Nao foi possivel ler o banco " + DB_LOTES + "." + chr(10) + chr(10) + str(e)
        messagebox.showerror("Erro ao carregar lotes", mensagem)
        return []


def buscar_dados_qr(tarefa_id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT codigo_tarefa, responsavel, data_inicio, descricao,
               codigo_lote, position_range, observacoes,
               eficiencia_optica_ok, valor_eficiencia,
               imersao_criogenica_ok, data_hora_registro, massa_ptp_g
        FROM tarefas
        WHERE id = ?
    """, (tarefa_id,))
    dados = cur.fetchone()
    conn.close()
    return dados


def carregar_tarefas():
    for i in tabela.get_children():
        tabela.delete(i)

    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, codigo_tarefa, codigo_lote, responsavel, data_inicio,
               eficiencia_optica_ok, imersao_criogenica_ok
        FROM tarefas
        ORDER BY id DESC
    """)

    for row in cur.fetchall():
        tabela.insert("", "end", values=row)

    conn.close()

def texto_lote_combo(l):
    """Texto exibido no combobox de lotes."""
    try:
        internal_lab_batch = l[1] or "-"
        arrival_date = l[2] or "-"
        company = l[3] or "-"
        company_batch = l[5] or "-"
        total = l[6] or "-"
        boxes = l[7] or "-"

        return (
            f"Internal Lab Batch: {internal_lab_batch} | "
            f"Company/OPTO Batch: {company_batch} | "
            f"Arrival: {arrival_date} | "
            f"Company: {company} | "
            f"Filters: {total} | "
            f"Small boxes: {boxes}"
        )
    except Exception:
        return str(l)


def atualizar_info_lote_selecionado(event=None):
    """Mostra na tela as informações extras do lote selecionado."""
    lote = obter_lote_selecionado()

    if lote is None:
        try:
            lbl_info_lote.config(text="No batch selected")
        except Exception:
            pass
        return

    try:
        internal_lab_batch = lote[1] or "-"
        arrival_date = lote[2] or "-"
        company = lote[3] or "-"
        company_batch = lote[5] or "-"
        total_filters = lote[6] or "-"
        small_boxes = lote[7] or "-"
        inspection = lote[8] or "-"
        control_file = lote[9] or "-"

        linhas = [
            f"Internal Lab Batch: {internal_lab_batch}",
            f"Company/OPTO Batch: {company_batch}",
            f"Arrival date: {arrival_date}",
            f"Company: {company}",
            f"Total filters: {total_filters}",
            f"Number of small boxes: {small_boxes}",
            f"Inspection: {inspection}",
            f"Control file: {control_file}",
        ]
        lbl_info_lote.config(text=chr(10).join(linhas))
    except Exception:
        try:
            lbl_info_lote.config(text="Batch information unavailable")
        except Exception:
            pass



def inserir_imagem_disco(parent, row=4, column=2):
    """Insere a imagem do disco de evaporacao no quadro Deposition Data."""
    try:
        caminhos = [
            os.path.join(os.getcwd(), DISCO_EVAPORACAO_IMG),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), DISCO_EVAPORACAO_IMG),
            os.path.join("/mnt/data", DISCO_EVAPORACAO_IMG),
            os.path.join(os.getcwd(), "Disco de evaporação.jpg"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "Disco de evaporação.jpg"),
            os.path.join("/mnt/data", "Disco de evaporação.jpg"),
        ]

        caminho_img = None
        for caminho in caminhos:
            if os.path.exists(caminho):
                caminho_img = caminho
                break

        if caminho_img is None:
            tk.Label(
                parent,
                text="Disk image not found",
                bg="#f4f6f8",
                fg="#777777",
                font=("Segoe UI", 9)
            ).grid(row=row, column=column, rowspan=4, sticky="n", padx=(18, 0), pady=(20, 0))
            return

        img = Image.open(caminho_img)
        img.thumbnail((240, 240), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)

        lbl_disco = tk.Label(parent, image=photo, bg="#f4f6f8")
        lbl_disco.image = photo
        lbl_disco.grid(row=row, column=column, rowspan=4, sticky="n", padx=(18, 0), pady=(12, 0))

    except Exception as e:
        tk.Label(
            parent,
            text="Disk image error: " + str(e),
            bg="#f4f6f8",
            fg="#777777",
            font=("Segoe UI", 8)
        ).grid(row=row, column=column, rowspan=4, sticky="n", padx=(18, 0), pady=(20, 0))


# =====================================================
# FUNÇÕES DA INTERFACE
# =====================================================
def atualizar_relogio():
    lbl_relogio.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    janela.after(1000, atualizar_relogio)


def adicionar_anexo():
    arquivos = filedialog.askopenfilenames(
        title="Selecionar arquivos",
        filetypes=[
            ("Imagens", "*.jpg *.jpeg *.png"),
            ("PDF", "*.pdf"),
            ("Todos", "*.*")
        ]
    )
    for arq in arquivos:
        anexos_lista.append(arq)
    lbl_anexos["text"] = f"{len(anexos_lista)} arquivo(s) anexado(s)"


def atualizar_lotes():
    global lotes
    lotes = carregar_lotes()
    combo_lotes["values"] = [texto_lote_combo(l) for l in lotes]


def abrir_sistema_lotes():
    """Abre o primeiro programa para cadastrar/consultar lotes."""
    caminho_local = os.path.join(os.getcwd(), PROGRAMA_LOTES)
    caminho_mnt = os.path.join("/mnt/data", PROGRAMA_LOTES)

    if os.path.exists(caminho_local):
        caminho = caminho_local
    elif os.path.exists(caminho_mnt):
        caminho = caminho_mnt
    else:
        messagebox.showwarning(
            "Programa não encontrado",
            f"Não encontrei o arquivo {PROGRAMA_LOTES}.\n"
            "Selecione manualmente o programa de controle de lotes."
        )
        caminho = filedialog.askopenfilename(
            title="Selecionar programa de controle de lotes",
            filetypes=[("Python", "*.py"), ("Todos", "*.*")]
        )
        if not caminho:
            return

    try:
        subprocess.Popen([sys.executable, caminho])
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível abrir o programa de lotes.\n\n{e}")


def selecionar_lote_em_janela():
    atualizar_lotes()
    if not lotes:
        messagebox.showwarning(
            "Nenhum lote encontrado",
            "Não encontrei lotes cadastrados no banco lotes.db.\n"
            "Abra o sistema de controle de lotes e cadastre/atualize os lotes."
        )
        return

    win = tk.Toplevel(janela)
    win.title("Selecionar lote cadastrado")
    win.geometry("760x360")
    win.configure(bg="#f4f6f8")

    cols = ("ID", "Internal Lab Batch", "Arrival Date", "Company", "QR/Tracking Code", "Company/OPTO Batch", "Total Filters", "Small Boxes", "Inspection", "Control File")
    tab = ttk.Treeview(win, columns=cols, show="headings", height=12)
    tab.pack(fill="both", expand=True, padx=12, pady=12)

    for c in cols:
        tab.heading(c, text=c)
        tab.column(c, anchor="center")

    for lote in lotes:
        tab.insert("", "end", values=lote)

    def confirmar():
        item = tab.selection()
        if not item:
            messagebox.showwarning("Warning", "Select a batch")
            return
        valores = tab.item(item[0], "values")
        lote_id = int(valores[0])
        for idx, lote in enumerate(lotes):
            if lote[0] == lote_id:
                combo_lotes.current(idx)
                atualizar_info_lote_selecionado()
                break
        win.destroy()

    ttk.Button(win, text="Use selected batch", command=confirmar).pack(pady=(0, 10))
    tab.bind("<Double-1>", lambda event: confirmar())


def obter_lote_selecionado():
    idx = combo_lotes.current()
    if idx == -1 or not lotes:
        return None
    return lotes[idx]


def limpar_campos():
    global tarefa_em_edicao_id, anexos_lista
    tarefa_em_edicao_id = None
    anexos_lista = []

    combo_lotes.set("")
    try:
        lbl_info_lote.config(text="No batch selected")
    except Exception:
        pass
    entry_serial.delete(0, tk.END)
    entry_data.delete(0, tk.END)
    entry_data.insert(0, datetime.today().strftime("%Y-%m-%d"))
    entry_resp.delete(0, tk.END)
    tipo_var.set("Substrato")
    entry_posicao.delete(0, tk.END)
    entry_obs.delete("1.0", tk.END)

    for e in [entry_a2, entry_d2, entry_a3, entry_d3, entry_a14, entry_d14, entry_ptp_mass]:
        e.delete(0, tk.END)

    for var in densidade_vars.values():
        var.set("")

    eficiencia_var.set("Não")
    entry_valor_eficiencia.delete(0, tk.END)
    imersao_var.set("Não")
    lbl_anexos["text"] = "No files"
    lbl_modo["text"] = "Mode: new record"



def converter_float(valor):
    """Aceita vírgula ou ponto como separador decimal."""
    valor = str(valor).strip().replace(",", ".")
    if not valor:
        raise ValueError("valor vazio")
    return float(valor)


def calcular_densidade_massa(antes, depois):
    """Calcula (massa depois - massa antes)/área em µg/cm²."""
    massa_antes = converter_float(antes)
    massa_depois = converter_float(depois)
    diferenca_g = massa_depois - massa_antes
    return (diferenca_g * 1_000_000.0) / AREA_FILTRO_CM2


def atualizar_densidades(*args):
    if "densidade_vars" not in globals():
        return
    pares = {
        2: (entry_a2, entry_d2),
        3: (entry_a3, entry_d3),
        14: (entry_a14, entry_d14),
    }
    for pos, (entry_antes, entry_depois) in pares.items():
        try:
            densidade = calcular_densidade_massa(entry_antes.get(), entry_depois.get())
            densidade_vars[pos].set(f"{densidade:.2f}")
        except Exception:
            densidade_vars[pos].set("")

def validar_campos():
    lote = obter_lote_selecionado()
    if lote is None:
        messagebox.showwarning("Warning", "Select the batch")
        return None

    serial = entry_serial.get().strip()
    if not serial:
        messagebox.showwarning("Warning", "Enter the serial number")
        return None

    massas = {
        2: (entry_a2.get().strip(), entry_d2.get().strip()),
        3: (entry_a3.get().strip(), entry_d3.get().strip()),
        14: (entry_a14.get().strip(), entry_d14.get().strip())
    }

    densidades = {}
    for pos, (antes, depois) in massas.items():
        if not antes or not depois:
            messagebox.showwarning("Erro", f"Massas faltando na posição {pos} - {nomes_posicoes[pos]}")
            return None
        try:
            densidades[pos] = f"{calcular_densidade_massa(antes, depois):.2f}"
        except Exception:
            messagebox.showwarning("Erro", f"Confira as massas da posição {pos}. Use apenas números.")
            return None

    return {
        "lote_id": lote[0],
        "codigo_lote": lote[1],
        "serial": serial,
        "data": entry_data.get().strip(),
        "resp": entry_resp.get().strip(),
        "tipo": tipo_var.get(),
        "posicao": entry_posicao.get().strip(),
        "obs": entry_obs.get("1.0", "end").strip(),
        "anexos_txt": ";".join(anexos_lista),
        "eficiencia_ok": eficiencia_var.get(),
        "valor_eficiencia": entry_valor_eficiencia.get().strip(),
        "imersao_ok": imersao_var.get(),
        "data_hora_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "massa_ptp_g": entry_ptp_mass.get().strip(),
        "massas": massas,
        "densidades": densidades
    }

# =====================================================
# SALVAR / EDITAR / EXCLUIR
# =====================================================
def salvar_tarefa():
    dados = validar_campos()
    if dados is None:
        return

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO tarefas
        (codigo_tarefa, responsavel, data_inicio, status, descricao,
         lote_entrada_id, codigo_lote, position_range, observacoes, anexos_txt,
         eficiencia_optica_ok, valor_eficiencia, imersao_criogenica_ok, data_hora_registro, massa_ptp_g)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        dados["serial"], dados["resp"], dados["data"], "Cadastrada", dados["tipo"],
        dados["lote_id"], dados["codigo_lote"], dados["posicao"], dados["obs"], dados["anexos_txt"],
        dados["eficiencia_ok"], dados["valor_eficiencia"], dados["imersao_ok"], dados["data_hora_registro"],
        dados["massa_ptp_g"]
    ))

    tarefa_id = cur.lastrowid

    for pos, (antes, depois) in dados["massas"].items():
        cur.execute("""
            INSERT INTO massa_posicoes (id_tarefa, posicao, massa_antes, massa_depois, densidade_massa_ug_cm2)
            VALUES (?, ?, ?, ?, ?)
        """, (tarefa_id, pos, antes, depois, dados["densidades"][pos]))

    conn.commit()
    conn.close()

    messagebox.showinfo("Sucesso", "Tarefa cadastrada!")
    limpar_campos()
    carregar_tarefas()


def carregar_para_edicao():
    global tarefa_em_edicao_id, anexos_lista

    item = tabela.selection()
    if not item:
        messagebox.showwarning("Warning", "Please select a task to edit")
        return

    tarefa_id = tabela.item(item[0], "values")[0]

    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT codigo_tarefa, responsavel, data_inicio, descricao,
               lote_entrada_id, codigo_lote, position_range, observacoes,
               anexos_txt, eficiencia_optica_ok, valor_eficiencia,
               imersao_criogenica_ok, massa_ptp_g
        FROM tarefas
        WHERE id = ?
    """, (tarefa_id,))
    row = cur.fetchone()

    cur.execute("SELECT posicao, massa_antes, massa_depois, densidade_massa_ug_cm2 FROM massa_posicoes WHERE id_tarefa = ?", (tarefa_id,))
    massas = {p: (a, d, dens) for p, a, d, dens in cur.fetchall()}
    conn.close()

    if not row:
        messagebox.showerror("Erro", "Registro não encontrado.")
        return

    limpar_campos()
    tarefa_em_edicao_id = tarefa_id

    serial, resp, data, tipo, lote_id, codigo_lote, posicao, obs, anexos_txt, ef_ok, val_ef, im_ok, massa_ptp = row

    atualizar_lotes()
    for idx, lote in enumerate(lotes):
        if lote[0] == lote_id or lote[1] == codigo_lote:
            combo_lotes.current(idx)
            break

    entry_serial.insert(0, serial or "")
    entry_data.delete(0, tk.END)
    entry_data.insert(0, data or "")
    entry_resp.insert(0, resp or "")
    tipo_var.set(tipo or "Substrato")
    entry_posicao.insert(0, posicao or "")
    entry_obs.insert("1.0", obs or "")

    for pos, (entry_antes, entry_depois) in {
        2: (entry_a2, entry_d2),
        3: (entry_a3, entry_d3),
        14: (entry_a14, entry_d14)
    }.items():
        if pos in massas:
            entry_antes.insert(0, massas[pos][0] or "")
            entry_depois.insert(0, massas[pos][1] or "")
            densidade_vars[pos].set(massas[pos][2] or "")

    eficiencia_var.set(ef_ok or "Não")
    entry_valor_eficiencia.insert(0, val_ef or "")
    imersao_var.set(im_ok or "Não")
    entry_ptp_mass.insert(0, massa_ptp or "")
    atualizar_densidades()

    anexos_lista = anexos_txt.split(";") if anexos_txt else []
    lbl_anexos["text"] = f"{len(anexos_lista)} arquivo(s) anexado(s)" if anexos_lista else "No files"
    lbl_modo["text"] = f"Mode: editing ID {tarefa_id}"


def editar_tarefa():
    global tarefa_em_edicao_id

    if tarefa_em_edicao_id is None:
        messagebox.showwarning("Warning", "Load a selected task for editing first.")
        return

    dados = validar_campos()
    if dados is None:
        return

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        UPDATE tarefas
        SET codigo_tarefa = ?, responsavel = ?, data_inicio = ?, descricao = ?,
            lote_entrada_id = ?, codigo_lote = ?, position_range = ?, observacoes = ?,
            anexos_txt = ?, eficiencia_optica_ok = ?, valor_eficiencia = ?,
            imersao_criogenica_ok = ?, data_hora_registro = ?, massa_ptp_g = ?
        WHERE id = ?
    """, (
        dados["serial"], dados["resp"], dados["data"], dados["tipo"],
        dados["lote_id"], dados["codigo_lote"], dados["posicao"], dados["obs"],
        dados["anexos_txt"], dados["eficiencia_ok"], dados["valor_eficiencia"],
        dados["imersao_ok"], dados["data_hora_registro"], dados["massa_ptp_g"], tarefa_em_edicao_id
    ))

    cur.execute("DELETE FROM massa_posicoes WHERE id_tarefa = ?", (tarefa_em_edicao_id,))
    for pos, (antes, depois) in dados["massas"].items():
        cur.execute("""
            INSERT INTO massa_posicoes (id_tarefa, posicao, massa_antes, massa_depois, densidade_massa_ug_cm2)
            VALUES (?, ?, ?, ?, ?)
        """, (tarefa_em_edicao_id, pos, antes, depois, dados["densidades"][pos]))

    conn.commit()
    conn.close()

    messagebox.showinfo("Sucesso", "Registro atualizado!")
    limpar_campos()
    carregar_tarefas()


def excluir_tarefa():
    item = tabela.selection()
    if not item:
        messagebox.showwarning("Warning", "Please select a task to delete")
        return

    tarefa_id = tabela.item(item[0], "values")[0]
    ok = messagebox.askyesno("Confirmar exclusão", f"Excluir a tarefa ID {tarefa_id}?")
    if not ok:
        return

    conn = conectar()
    cur = conn.cursor()
    cur.execute("DELETE FROM massa_posicoes WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM tarefas WHERE id = ?", (tarefa_id,))
    conn.commit()
    conn.close()

    messagebox.showinfo("Sucesso", "Registro excluído.")
    limpar_campos()
    carregar_tarefas()

# =====================================================
# QR CODE / DETALHES
# =====================================================
def gerar_qr():
    item = tabela.selection()
    if not item:
        messagebox.showwarning("Warning", "Please select a task")
        return

    valores = tabela.item(item[0], "values")
    tarefa_id = valores[0]
    dados = buscar_dados_qr(tarefa_id)

    if dados:
        texto = (
            f"TAREFA_ID={tarefa_id}\n"
            f"Serial={dados[0]}\n"
            f"Lote={dados[4]}\n"
            f"Data_deposicao={dados[2]}"
        )
    else:
        texto = f"TAREFA_ID={tarefa_id}"

    img = qrcode.make(texto)
    nome = f"qr_tarefa_{tarefa_id}.png"
    img.save(nome)
    messagebox.showinfo("QR gerado", f"Arquivo salvo:\n{nome}")


def abrir_detalhes_tarefa():
    item = tabela.selection()
    if not item:
        messagebox.showwarning("Warning", "Please select a task")
        return

    tarefa_id = tabela.item(item[0], "values")[0]
    dados = buscar_dados_qr(tarefa_id)

    if not dados:
        messagebox.showinfo("Info", "Nenhum dado encontrado")
        return

    win = tk.Toplevel(janela)
    win.title(f"Tarefa {dados[0]}")
    win.geometry("560x520")
    win.configure(bg="#f4f6f8")

    tk.Label(win, text="Detalhes da Tarefa", font=("Segoe UI", 14, "bold"), bg="#f4f6f8").pack(pady=12)
    frame_info = tk.Frame(win, bg="#f4f6f8", padx=20, pady=10)
    frame_info.pack(fill="both", expand=True)

    def linha(rotulo, valor):
        tk.Label(frame_info, text=rotulo, font=("Segoe UI", 10, "bold"), bg="#f4f6f8").pack(anchor="w", pady=(8, 0))
        tk.Label(frame_info, text=valor if valor else "-", font=("Segoe UI", 10), bg="#f4f6f8").pack(anchor="w")

    linha("Código da tarefa:", dados[0])
    linha("Responsável:", dados[1])
    linha("Data de deposição:", dados[2])
    linha("Descrição:", dados[3])
    linha("Lote:", dados[4])
    linha("Posições:", dados[5])
    linha("Observações:", dados[6])
    linha("Eficiência óptica medida?", dados[7])
    linha("Valor de eficiência:", dados[8])
    linha("Imersão criogênica OK?", dados[9])
    linha("Data/hora do registro:", dados[10])
    linha("PTP Mass (g):", dados[11])

    tk.Button(win, text="Fechar", command=win.destroy, bg="#2e6f95", fg="white", relief="flat", padx=14, pady=5).pack(pady=15)

# =====================================================
# INTERFACE
# =====================================================
inicializar_banco()

janela = tk.Tk()
janela.title("Deposition Control System for DUNE")
janela.geometry("1350x820")
janela.configure(bg="#f4f6f8")

style = ttk.Style()
style.theme_use("clam")
style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6)
style.configure("Titulo.TLabel", font=("Segoe UI", 14, "bold"))
style.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

# ---------- BARRA SUPERIOR ----------
barra = tk.Frame(janela, bg="#1f3a5f", height=72)
barra.pack(fill="x")
barra.pack_propagate(False)
barra.grid_columnconfigure(0, weight=1)
barra.grid_columnconfigure(1, weight=2)
barra.grid_columnconfigure(2, weight=1)

# Logos com fallback, para o sistema abrir mesmo se a imagem não estiver na pasta.
def inserir_logo(nome_arquivo, coluna, sticky):
    try:
        img = Image.open(nome_arquivo).resize((110, 48))
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(barra, image=photo, bg="#1f3a5f")
        label.image = photo
    except Exception:
        label = tk.Label(barra, text="", bg="#1f3a5f")
    label.grid(row=0, column=coluna, sticky=sticky, padx=15)

inserir_logo("esquerda.png", 0, "w")

tk.Label(
    barra,
    text="Deposition Control System for DUNE",
    fg="white",
    bg="#1f3a5f",
    font=("Segoe UI", 15, "bold")
).grid(row=0, column=1)

frame_relogio = tk.Frame(barra, bg="#1f3a5f")
frame_relogio.grid(row=0, column=2, sticky="e", padx=15)
lbl_relogio = tk.Label(frame_relogio, text="", fg="white", bg="#1f3a5f", font=("Segoe UI", 10, "bold"))
lbl_relogio.pack(anchor="e")
inserir_logo("direita.png", 2, "e")

# ---------- CONTEÚDO ----------
frame = tk.Frame(janela, bg="#f4f6f8", padx=20, pady=10)
frame.pack(fill="both", expand=True)
frame.grid_columnconfigure(1, weight=1)
frame.grid_columnconfigure(2, weight=1)

# ---------- DADOS PRINCIPAIS ----------
quadro_dados = tk.LabelFrame(frame, text="Deposition Data", bg="#f4f6f8", font=("Segoe UI", 11, "bold"), padx=15, pady=12)
quadro_dados.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=(0, 15))

# Lote
tk.Label(quadro_dados, text="Batch:", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=8)
lotes = carregar_lotes()

frame_lote = tk.Frame(quadro_dados, bg="#f4f6f8")
frame_lote.grid(row=0, column=1, sticky="w")

combo_lotes = ttk.Combobox(frame_lote, values=[texto_lote_combo(l) for l in lotes], state="readonly", width=105)
combo_lotes.pack(side="left")

ttk.Button(frame_lote, text="Select", command=selecionar_lote_em_janela).pack(side="left", padx=5)
ttk.Button(frame_lote, text="Open batch system", command=abrir_sistema_lotes).pack(side="left", padx=5)
ttk.Button(frame_lote, text="↻", width=3, command=atualizar_lotes).pack(side="left", padx=5)
combo_lotes.bind("<<ComboboxSelected>>", atualizar_info_lote_selecionado)
lbl_info_lote = tk.Label(
    quadro_dados,
    text="No batch selected",
    bg="#f4f6f8",
    fg="#1f3a5f",
    justify="left",
    anchor="w",
    font=("Segoe UI", 9)
)
lbl_info_lote.grid(row=0, column=2, rowspan=4, sticky="nw", padx=(18, 0), pady=4)

inserir_imagem_disco(quadro_dados, row=4, column=2)


tk.Label(quadro_dados, text="Serial Number:", bg="#f4f6f8").grid(row=1, column=0, sticky="w", pady=6)
entry_serial = ttk.Entry(quadro_dados, width=35)
entry_serial.grid(row=1, column=1, sticky="w", pady=6)

tk.Label(quadro_dados, text="Deposition Date:", bg="#f4f6f8").grid(row=2, column=0, sticky="w", pady=6)
entry_data = ttk.Entry(quadro_dados, width=35)
entry_data.insert(0, datetime.today().strftime("%Y-%m-%d"))
entry_data.grid(row=2, column=1, sticky="w", pady=6)

tk.Label(quadro_dados, text="Responsible:", bg="#f4f6f8").grid(row=3, column=0, sticky="w", pady=6)
entry_resp = ttk.Entry(quadro_dados, width=35)
entry_resp.grid(row=3, column=1, sticky="w", pady=6)

tk.Label(quadro_dados, text="Filter type:", bg="#f4f6f8").grid(row=4, column=0, sticky="w", pady=6)
tipo_var = tk.StringVar(value="Substrato")
frame_tipo = tk.Frame(quadro_dados, bg="#f4f6f8")
frame_tipo.grid(row=4, column=1, sticky="w")
ttk.Radiobutton(frame_tipo, text="Substrate", variable=tipo_var, value="Substrato").pack(side="left", padx=(0, 15))
ttk.Radiobutton(frame_tipo, text="Substrate + dichroic", variable=tipo_var, value="Substrato+dicroico").pack(side="left")

tk.Label(quadro_dados, text="Position (ex: 1-28):", bg="#f4f6f8").grid(row=5, column=0, sticky="w", pady=6)
entry_posicao = ttk.Entry(quadro_dados, width=35)
entry_posicao.grid(row=5, column=1, sticky="w", pady=6)

tk.Label(quadro_dados, text="Observations:", bg="#f4f6f8").grid(row=6, column=0, sticky="nw", pady=6)
entry_obs = tk.Text(quadro_dados, height=6, width=70, font=("Segoe UI", 9), bd=1, relief="solid")
entry_obs.grid(row=6, column=1, sticky="w", pady=6)

frame_anexo = tk.Frame(quadro_dados, bg="#f4f6f8")
frame_anexo.grid(row=7, column=0, columnspan=2, sticky="w", pady=6)
btn_anexo = tk.Button(frame_anexo, text="📎 Attach images / files", command=adicionar_anexo, bg="#e0e6ed", relief="flat", padx=10, pady=4)
btn_anexo.pack(side="left")
lbl_anexos = tk.Label(frame_anexo, text="No files", bg="#f4f6f8")
lbl_anexos.pack(side="left", padx=10)

# ---------- TESTE DE QUALIDADE À DIREITA ----------
quadro_qualidade = tk.LabelFrame(frame, text="Quality Test", bg="#f4f6f8", font=("Segoe UI", 11, "bold"), padx=15, pady=12)
quadro_qualidade.grid(row=0, column=2, sticky="nsew")

eficiencia_var = tk.StringVar(value="Não")
imersao_var = tk.StringVar(value="Não")

tk.Label(quadro_qualidade, text="Optical efficiency test?", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(4, 2))
frame_ef = tk.Frame(quadro_qualidade, bg="#f4f6f8")
frame_ef.grid(row=1, column=0, sticky="w", pady=(0, 10))
ttk.Radiobutton(frame_ef, text="Yes", variable=eficiencia_var, value="Sim").pack(side="left", padx=(0, 12))
ttk.Radiobutton(frame_ef, text="No", variable=eficiencia_var, value="Não").pack(side="left")

tk.Label(quadro_qualidade, text="Efficiency value:", bg="#f4f6f8").grid(row=2, column=0, sticky="w", pady=(8, 2))
entry_valor_eficiencia = ttk.Entry(quadro_qualidade, width=28)
entry_valor_eficiencia.grid(row=3, column=0, sticky="w", pady=(0, 12))

tk.Label(quadro_qualidade, text="Cryogenic immersion OK?", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(12, 2))
frame_im = tk.Frame(quadro_qualidade, bg="#f4f6f8")
frame_im.grid(row=5, column=0, sticky="w", pady=(0, 10))
ttk.Radiobutton(frame_im, text="Yes", variable=imersao_var, value="Sim").pack(side="left", padx=(0, 12))
ttk.Radiobutton(frame_im, text="No", variable=imersao_var, value="Não").pack(side="left")

lbl_modo = tk.Label(quadro_qualidade, text="Mode: new record", bg="#f4f6f8", fg="#1f3a5f", font=("Segoe UI", 10, "bold"))
lbl_modo.grid(row=6, column=0, sticky="w", pady=(25, 0))

tk.Label(quadro_qualidade, text="Current date/time:", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=7, column=0, sticky="w", pady=(20, 2))
lbl_relogio_tela = tk.Label(quadro_qualidade, text="", bg="#f4f6f8", fg="#333333", font=("Segoe UI", 10))
lbl_relogio_tela.grid(row=8, column=0, sticky="w")

def atualizar_relogio_tela():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    lbl_relogio_tela.config(text=agora)
    lbl_relogio.config(text=agora)
    janela.after(1000, atualizar_relogio_tela)

# ---------- MASSAS ----------
quadro_massas = tk.LabelFrame(frame, text="Mass Control by Position", bg="#f4f6f8", font=("Segoe UI", 11, "bold"), padx=15, pady=12)
quadro_massas.grid(row=1, column=0, columnspan=3, pady=18, sticky="ew")

tk.Label(quadro_massas, text="Position", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=20)
tk.Label(quadro_massas, text="Mass Before (g)", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=1, padx=25)
tk.Label(quadro_massas, text="Mass After (g)", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, padx=25)
tk.Label(quadro_massas, text="Mass density (µg/cm²)", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=3, padx=25)

nomes_posicoes = {2: "Center", 3: "Middle", 14: "External"}
densidade_vars = {2: tk.StringVar(), 3: tk.StringVar(), 14: tk.StringVar()}

def linha_massa(pos, row):
    texto = f"{pos} - {nomes_posicoes.get(pos, '')}"
    tk.Label(quadro_massas, text=texto, bg="#f4f6f8", font=("Segoe UI", 10)).grid(row=row, column=0, pady=8)
    a = ttk.Entry(quadro_massas, width=14)
    a.grid(row=row, column=1, pady=8)
    d = ttk.Entry(quadro_massas, width=14)
    d.grid(row=row, column=2, pady=8)

    lbl_dens = tk.Label(quadro_massas, textvariable=densidade_vars[pos], width=18,
                        bg="white", relief="solid", bd=1, font=("Segoe UI", 9))
    lbl_dens.grid(row=row, column=3, pady=8)

    a.bind("<KeyRelease>", atualizar_densidades)
    d.bind("<KeyRelease>", atualizar_densidades)
    a.bind("<FocusOut>", atualizar_densidades)
    d.bind("<FocusOut>", atualizar_densidades)
    return a, d

entry_a2, entry_d2 = linha_massa(2, 1)
entry_a3, entry_d3 = linha_massa(3, 2)
entry_a14, entry_d14 = linha_massa(14, 3)

frame_ptp_mass = tk.Frame(quadro_massas, bg="#f4f6f8")
frame_ptp_mass.grid(row=1, column=4, rowspan=3, sticky="n", padx=(45, 10), pady=6)
tk.Label(frame_ptp_mass, text="PTP Mass:", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).pack(anchor="w")
linha_ptp = tk.Frame(frame_ptp_mass, bg="#f4f6f8")
linha_ptp.pack(anchor="w", pady=(6, 0))
entry_ptp_mass = ttk.Entry(linha_ptp, width=16)
entry_ptp_mass.pack(side="left")
tk.Label(linha_ptp, text="g", bg="#f4f6f8").pack(side="left", padx=(6, 0))
tk.Label(frame_ptp_mass, text=f"Area: {AREA_FILTRO_MM2:.0f} mm² = {AREA_FILTRO_CM2:.1f} cm²", bg="#f4f6f8", fg="#555555", font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))
tk.Label(frame_ptp_mass, text="density = (after − before) / area", bg="#f4f6f8", fg="#555555", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

# ---------- BOTÕES ----------
btn = tk.Frame(frame, bg="#f4f6f8")
btn.grid(row=2, column=0, columnspan=3, pady=12)

tk.Button(btn, text="Save", command=salvar_tarefa, bg="#2e6f95", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
tk.Button(btn, text="Load for edit", command=carregar_para_edicao, bg="#1f77b4", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
tk.Button(btn, text="Edit / Update", command=editar_tarefa, bg="#ef6c00", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
tk.Button(btn, text="Clear", command=limpar_campos, bg="#607d8b", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
tk.Button(btn, text="Delete", command=excluir_tarefa, bg="#c62828", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
ttk.Button(btn, text="Generate QR Code", command=gerar_qr).pack(side="left", padx=8, ipadx=10)
ttk.Button(btn, text="View details", command=abrir_detalhes_tarefa).pack(side="left", padx=8, ipadx=10)

# ---------- TABELA ----------
cols = ("ID", "Serial", "Batch", "Responsible", "Deposition Date", "Optical Efficiency", "Cryogenic Immersion")
tabela = ttk.Treeview(frame, columns=cols, show="headings", height=12)
tabela.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=10)

for c in cols:
    tabela.heading(c, text=c)
    tabela.column(c, anchor="center", width=145)

tabela.bind("<Double-1>", lambda event: carregar_para_edicao())

frame.rowconfigure(3, weight=1)
frame.columnconfigure(1, weight=1)

carregar_tarefas()
atualizar_relogio_tela()
janela.mainloop()
