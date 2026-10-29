import os
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import qrcode
from datetime import datetime
import csv
import math

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
conn = sqlite3.connect(DB_NAME)
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

registro_em_edicao = None

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


def calcular_caixas_menores():
    """
    Mantém separadas as duas informações:
    1) total_filtros = número total de filtros no lote geral;
    2) numero_caixas_menores = quantas caixas menores existem dentro do lote maior.

    A capacidade fixa de cada caixa menor é 28 filtros.
    O cálculo serve apenas como sugestão automática, podendo ser ajustado manualmente
    caso a OPTO envie uma organização diferente.
    """
    texto = entry_total_filtros.get().strip()
    if not texto:
        lbl_calculo.config(text="Small boxes: --")
        return

    try:
        total = int(texto)
        if total < 0:
            raise ValueError
    except ValueError:
        lbl_calculo.config(text="Small boxes: invalid total")
        return

    caixas = math.ceil(total / SMALL_BOX_CAPACITY) if total > 0 else 0
    completas = total // SMALL_BOX_CAPACITY
    restante = total % SMALL_BOX_CAPACITY

    entry_numero_caixas.delete(0, tk.END)
    entry_numero_caixas.insert(0, str(caixas))

    if restante == 0 and total > 0:
        detalhe = f"{caixas} small box(es), all complete ({SMALL_BOX_CAPACITY} filters each)."
    elif total == 0:
        detalhe = "0 small boxes."
    else:
        detalhe = (
            f"{caixas} small box(es): {completas} complete + "
            f"1 partial with {restante} filter(s)."
        )
    lbl_calculo.config(text=detalhe)


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

    for i in range(1, numero_caixas + 1):
        # Estima a quantidade em cada caixa: as anteriores completas e a última com o restante, se houver.
        if i < numero_caixas:
            filtros_na_caixa = capacidade
        else:
            restante = total_filtros - capacidade * (numero_caixas - 1)
            filtros_na_caixa = restante if restante > 0 else capacidade

        caixa_id = f"{tracking_id}-BOX-{i:02d}"
        conteudo = "\n".join([
            f"Tracking ID: {tracking_id}",
            f"Small Box ID: {caixa_id}",
            f"Small Box: {i:02d}/{numero_caixas:02d}",
            f"General Batch: {dados.get('lote_geral', '')}",
            f"Supplier Batch: {dados.get('lote_fornecedor', '')}",
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
        messagebox.showwarning("Warning", "Enter the total number of filters in the general batch.")
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
        if caixas < 0:
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

        qr_path = gerar_qrcode(registro_id, tracking_id, {
            "Tracking ID": tracking_id,
            "General Batch": dados["lote_geral"],
            "Supplier Batch": dados["lote_fornecedor"],
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
    entry_lote_geral.insert(0, row[1] or "")
    entry_lote_fornecedor.insert(0, row[2] or "")
    entry_data.insert(0, row[3] or "")
    entry_resp.insert(0, row[4] or "")
    entry_fornecedor.insert(0, row[5] or "")
    entry_total_filtros.insert(0, row[6] or "")
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


def limpar():
    global registro_em_edicao
    registro_em_edicao = None
    for entry in [
        entry_lote_geral, entry_lote_fornecedor, entry_data, entry_resp,
        entry_fornecedor, entry_total_filtros, entry_numero_caixas,
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


def atualizar_tabela():
    for i in tabela.get_children():
        tabela.delete(i)

    cursor.execute("""
        SELECT id, tracking_id, lote_geral, lote_fornecedor, fornecedor,
               total_filtros, numero_caixas_menores, data_recebimento,
               responsavel, resultado_inspecao, data_hora_registro
        FROM lotes
        ORDER BY id DESC
    """)
    for row in cursor.fetchall():
        tabela.insert("", tk.END, values=row)


def buscar():
    termo = entry_busca.get().strip()
    for i in tabela.get_children():
        tabela.delete(i)

    cursor.execute("""
        SELECT id, tracking_id, lote_geral, lote_fornecedor, fornecedor,
               total_filtros, numero_caixas_menores, data_recebimento,
               responsavel, resultado_inspecao, data_hora_registro
        FROM lotes
        WHERE tracking_id LIKE ? OR lote_geral LIKE ? OR lote_fornecedor LIKE ?
              OR fornecedor LIKE ? OR responsavel LIKE ?
        ORDER BY id DESC
    """, tuple(['%' + termo + '%'] * 5))
    for row in cursor.fetchall():
        tabela.insert("", tk.END, values=row)


def exportar_csv():
    caminho = filedialog.asksaveasfilename(defaultextension=".csv")
    if not caminho:
        return

    cursor.execute("""
        SELECT id, tracking_id, lote_geral, lote_fornecedor, data_recebimento,
               responsavel, fornecedor, total_filtros, numero_caixas_menores,
               capacidade_caixa_menor, material, dimensoes, espessura,
               tipo_acabamento, filtros_quebrados, quantidade_confere,
               procedimento_limpeza, resultado_inspecao, arquivo_controle,
               observacoes, qr_code_path, qrcodes_caixas_dir, data_hora_registro
        FROM lotes
        ORDER BY id DESC
    """)
    dados = cursor.fetchall()

    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "Tracking ID", "General Batch", "Supplier Batch", "Arrival Date",
            "Responsible", "Supplier", "Total Number of Filters",
            "Number of Small Boxes", "Small Box Capacity", "Material", "Dimensions",
            "Thickness", "Finishing Type", "Broken Filters?", "Quantity Matches?",
            "Cleaning Procedure Verified?", "Inspection Result", "Supplier Control File",
            "Observations", "General Batch QR Code", "Small Boxes QR Code Folder", "Record Date/Time"
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
    conn.commit()
    atualizar_tabela()
    limpar()
    messagebox.showinfo("Success", "Record deleted.")


# ===============================
# JANELA PRINCIPAL
# ===============================
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
    ("General Batch ID", "entry_lote_geral"),
    ("Supplier Batch", "entry_lote_fornecedor"),
    ("Arrival Date", "entry_data"),
    ("Responsible", "entry_resp"),
    ("Supplier / Company", "entry_fornecedor"),
    ("Total Number of Filters", "entry_total_filtros"),
]

entry_lote_geral = tk.Entry(frame_lote, width=28)
entry_lote_fornecedor = tk.Entry(frame_lote, width=28)
entry_data = tk.Entry(frame_lote, width=28)
entry_resp = tk.Entry(frame_lote, width=28)
entry_fornecedor = tk.Entry(frame_lote, width=28)
entry_total_filtros = tk.Entry(frame_lote, width=28)

entries = [entry_lote_geral, entry_lote_fornecedor, entry_data, entry_resp, entry_fornecedor, entry_total_filtros]
for idx, ((label, _), entry) in enumerate(zip(labels_entries, entries)):
    tk.Label(frame_lote, text=label).grid(row=idx, column=0, sticky="e", padx=5, pady=3)
    entry.grid(row=idx, column=1, sticky="w", padx=5, pady=3)

entry_total_filtros.bind("<KeyRelease>", lambda event: calcular_caixas_menores())

# -------- CAIXAS MENORES --------
frame_caixas = tk.LabelFrame(frame_cad, text="Small Boxes Inside the General Batch", padx=10, pady=10)
frame_caixas.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

tk.Label(frame_caixas, text="Small Box Capacity").grid(row=0, column=0, sticky="e", padx=5, pady=3)
entry_capacidade_caixa = tk.Entry(frame_caixas, width=18)
entry_capacidade_caixa.grid(row=0, column=1, sticky="w", padx=5, pady=3)
entry_capacidade_caixa.insert(0, str(SMALL_BOX_CAPACITY))
entry_capacidade_caixa.config(state="normal")

tk.Label(frame_caixas, text="Number of Small Boxes in General Batch").grid(row=1, column=0, sticky="e", padx=5, pady=3)
entry_numero_caixas = tk.Entry(frame_caixas, width=18)
entry_numero_caixas.grid(row=1, column=1, sticky="w", padx=5, pady=3)

tk.Button(frame_caixas, text="Calculate from total filters", command=calcular_caixas_menores).grid(row=2, column=0, columnspan=2, pady=6)
lbl_calculo = tk.Label(frame_caixas, text="Small boxes: --", fg="#1565c0", font=("Segoe UI", 9, "bold"))
lbl_calculo.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

tk.Label(
    frame_caixas,
    text="Note: the general batch keeps the total number of filters.\nThis section records how many 28-filter small boxes are inside it.",
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
    "ID", "Tracking ID", "General Batch", "Supplier Batch", "Supplier",
    "Total Filters", "Small Boxes", "Arrival Date", "Responsible",
    "Inspection", "Record Date/Time"
)
tabela = ttk.Treeview(frame_tabela, columns=colunas, show="headings")

larguras = {
    "ID": 60,
    "Tracking ID": 150,
    "General Batch": 140,
    "Supplier Batch": 140,
    "Supplier": 110,
    "Total Filters": 110,
    "Small Boxes": 110,
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

janela.mainloop()
