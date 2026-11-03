"""Traduções para o português (chave = texto em inglês da tela). Usado por i18n.py.

Os termos técnicos ficam em inglês: sample, batch, OPTO batch, internal lot, cleaning lot, run, PID, tracking ID,
Final QA sign-off, PTP, Admin/Operator, os nomes dos testes (Deposition, Visual inspection, Cryogenic immersion,
Optical efficiency, Mass control), os status (Incomplete, To be reviewed, Completed) e os resultados (Approved,
Rejected). Nada de aspas duplas nas traduções: elas vão também dentro de atributos HTML (title=, data-texto=).
"""

PT = {
    # ---------------- barra superior, menus, rodapé ----------------
    "Samples": "Samples",
    "Batches": "Batches",
    "Users": "Usuários",
    "Audit log": "Audit log",
    "Search batch, tracking ID, internal lot…": "Buscar batch, tracking ID, internal lot…",
    "Search run, PID, batch, responsible…": "Buscar run, PID, batch, responsável…",
    "change my password": "trocar minha senha",
    "Log out": "Sair",
    "Quit": "Fechar",
    "Close the Deposition Control browser app?": "Fechar o Deposition Control no navegador?",
    "Stop the program (closing the tab keeps it running)": "Encerra o programa (fechar a aba não o encerra)",
    "Language of the screens (reports and PDFs stay in English)": "Idioma das telas (relatórios e PDFs ficam em inglês)",
    "Inspection result": "Resultado da inspeção",
    "All batches": "Todos os batches",
    "No batch registered yet": "Nenhum batch cadastrado ainda",
    "All samples": "Todas as samples",
    "Samples without a batch": "Samples sem batch",
    "No batch yet": "Ainda sem batch",
    "Delete": "Excluir",
    "This cannot be undone.": "Isto não pode ser desfeito.",
    "Confirm with your password ({user})": "Confirme com a sua senha ({user})",
    "Cancel": "Cancelar",
    "LEPTONS Laboratory · Unicamp · Deposition Control System for DUNE · read at {hora}":
        "Laboratório LEPTONS · Unicamp · Deposition Control System para o DUNE · lido em {hora}",

    # ---------------- palavras e botões comuns ----------------
    "Save": "Salvar",
    "Update": "Atualizar",
    "New": "Novo",
    "Edit": "Editar",
    "Close": "Fechar",
    "Done": "Concluir",
    "Apply": "Aplicar",
    "Today": "Hoje",
    "Search": "Buscar",
    "search": "busca",
    "show all": "mostrar todos",
    "All": "Todas",
    "or": "ou",
    " or ": " ou ",
    "to": "a",
    "Yes": "Sim",
    "No": "Não",
    "In progress": "Em andamento",
    "Not filled": "Não preenchido",
    "Date": "Data",
    "Name": "Nome",
    "Responsible": "Responsável",
    "Notes": "Notas",
    "Observations": "Observações",
    "Filters": "Filtros",
    "filters": "filtros",
    "Filter": "Filtro",
    "Box": "Caixa",
    "Origin": "Origem",
    "Result": "Resultado",
    "Procedure": "Procedimento",
    "Inspection": "Inspeção",
    "Company": "Empresa",
    "Supplier": "Fornecedor",
    "Position": "Posição",
    "Density": "Densidade",
    "Area": "Área",
    "Before": "Antes",
    "After": "Depois",
    "Pass": "Passou",
    "Comments": "Comentários",
    "Class": "Classe",
    "Class.": "Classe",
    "Condition": "Condição",
    "Tested": "Testada",
    "Tested?": "Testada?",
    "Approved?": "Aprovado?",
    "Review": "Revisão",
    "Reviewed": "Revisada",
    "reviewed": "revisada",
    "NEW": "NOVA",
    "Error": "Erro",
    "Not found.": "Não encontrado.",
    "Back to the sample list": "Voltar para a lista de samples",
    "Only an Admin can open this page.": "Só um Admin pode abrir esta página.",
    "Only an Admin can delete records.": "Só um Admin pode excluir registros.",
    "Password not confirmed – nothing was deleted.": "Senha não confirmada – nada foi excluído.",
    "The password is incorrect.": "A senha está incorreta.",
    "Could not write the file. Close the PDF if it is open and try again: {caminho}":
        "Não foi possível gravar o arquivo. Feche o PDF se ele estiver aberto e tente de novo: {caminho}",
    "last saved": "gravado pela última vez em",
    "record ID": "ID do registro",
    "no PID yet": "ainda sem PID",
    "no run": "sem run",
    "(no PID)": "(sem PID)",
    "Click to edit": "Clique para editar",
    "Print report (PDF)": "Imprimir relatório (PDF)",
    "Open report": "Abrir relatório",
    "Backup now": "Fazer backup agora",

    # ---------------- lista de samples ----------------
    "Deposition samples": "Samples de deposição",
    "{n} samples": "{n} samples",
    "showing {n} of {total} samples": "mostrando {n} de {total} samples",
    "ID = run number": "ID = número da run",
    "more than one sample": "mais de uma sample",
    "New sample": "Nova sample",
    "Generate the PDF report of all {n} depositions? This may take a minute.":
        "Gerar o relatório em PDF de todas as {n} deposições? Isso pode levar um minuto.",
    "Export all PDFs": "Exportar todos os PDFs",
    "No sample matches this filter.": "Nenhuma sample corresponde a este filtro.",

    # ---------------- página da sample ----------------
    "Signed off: saving changes removes the Final QA sign-off":
        "Com sign-off: gravar alterações remove o Final QA sign-off",
    "Edit sample": "Editar sample",
    "Signed off (Final QA) – only an Admin can change a completed sample":
        "Com sign-off (Final QA) – só um Admin pode alterar uma sample Completed",
    "Review sample": "Revisar sample",
    "Generate QR Code": "Gerar QR Code",
    "Export sample (JSON)": "Exportar sample (JSON)",
    "Delete sample ID {n}": "Excluir a sample ID {n}",
    "Sample {pid} and everything recorded for it (deposition, visual inspection, cryogenic immersion, optical efficiency, review) will be deleted.":
        "A sample {pid} e tudo o que foi registrado nela (deposition, visual inspection, cryogenic immersion, "
        "optical efficiency, revisão) serão excluídos.",
    "Delete sample": "Excluir sample",
    "Batch decision": "Decisão do batch",
    "Missing information": "Informações faltando",
    "needed before the sample can be reviewed": "necessárias antes de a sample poder ser revisada",
    "Deposition date": "Data da deposição",
    "Filter type": "Tipo de filtro",
    "arrived": "chegou em",
    "no filter assigned": "nenhum filtro atribuído",
    "{n} of {total} filters without origin – use <b>Edit sample › Filter origin…</b>":
        "{n} de {total} filtros sem origem – use <b>Editar sample › Origem dos filtros…</b>",
    "Attached files": "Arquivos anexados",
    "area {a} cm² · density = (after − before) / area": "área {a} cm² · densidade = (depois − antes) / área",
    "classified": "classificados",
    "Inspection date": "Data da inspeção",
    "Performed by": "Realizado por",
    "Supervisor review": "Revisão do supervisor",
    "Test date": "Data do teste",
    "Mass of the control substrates · max. loss {n} %": "Massa dos substratos de controle · perda máx. {n} %",
    "pass: x ≥ {x}": "passa: x ≥ {x}",
    "Reference substrate": "Substrato de referência",
    "installed": "instalado em",
    "Room": "Sala",
    "Signed off by": "Sign-off por",
    "Completed: only an Admin can change this sample, and any change removes this sign-off – the sample goes back to “To be reviewed” and needs a new Final QA sign-off.":
        "Completed: só um Admin pode alterar esta sample, e qualquer alteração remove este sign-off – a sample volta "
        "para “To be reviewed” e precisa de um novo Final QA sign-off.",

    # ---------------- formulário da sample ----------------
    "Edit run {n}": "Editar run {n}",
    "Reviewed and signed": "Revisado e assinado",
    "The decision is final only after the Technical Supervisor signs the record.":
        "A decisão só é final depois que o Technical Supervisor assina o registro.",
    "{por} on {data}": "{por} em {data}",
    "everything is saved together with <b>Save</b>": "tudo é gravado junto com <b>Salvar</b>",
    "Save anyway": "Salvar mesmo assim",
    "This sample was signed off (Final QA) by <b>{por}</b> on {data}.":
        "Esta sample recebeu o sign-off (Final QA) de <b>{por}</b> em {data}.",
    "Saving changes removes the sign-off: the sample goes back to “To be reviewed” and needs a new Final QA sign-off.":
        "Gravar alterações remove o sign-off: a sample volta para “To be reviewed” e precisa de um novo Final QA sign-off.",
    "Deposition data": "Dados da deposição",
    "Arrival / cleaned": "Chegada / limpeza",
    "No batch selected": "Nenhum batch selecionado",
    "Add batch / internal lot…": "Adicionar batch / internal lot…",
    "The filters of this deposition came from more than one box or batch: assign where each filter came from":
        "Os filtros desta deposição vieram de mais de uma caixa ou batch: indique de onde veio cada filtro",
    "Filter origin…": "Origem dos filtros…",
    "Opens the Batches tab in a new browser tab. After registering the batch, use “Add batch / internal lot…” again.":
        "Abre a aba Batches em outra aba do navegador. Depois de cadastrar o batch, use “Adicionar batch / internal lot…” de novo.",
    "Register a new batch ↗": "Cadastrar um novo batch ↗",
    "Position (ex: 1-28)": "Posição (ex: 1-28)",
    "Attached images / files": "Imagens / arquivos anexados",
    "Remove from the sample": "Remover da sample",
    "PTP mass (g)": "Massa de PTP (g)",
    "Area: {mm} mm² = {cm} cm² · density = (after − before) / area":
        "Área: {mm} mm² = {cm} cm² · densidade = (depois − antes) / área",
    "Filled by the “Reviewed” button on the Review sample page (Admin only).":
        "Preenchido pelo botão “Revisada” da página Revisar sample (só Admin).",
    "Performed by (operator)": "Realizado por (operador)",
    "Clear table": "Limpar tabela",
    "Clear this row": "Limpar esta linha",
    "Mass control of the control substrates": "Mass control dos substratos de controle",
    "Difference (after − before)": "Diferença (depois − antes)",
    "Condition (loss ≤ {n} %)": "Condição (perda ≤ {n} %)",
    "Mass loss (%) = (mass after − mass before) / mass before × 100. Loss ≤ {lim} % → Approved; loss &gt; {lim} % → Rejected (non-conforming). The overall result is APPROVED only if all {n} control substrates are approved and all {itens} inspection items below are Yes.":
        "Perda de massa (%) = (massa depois − massa antes) / massa antes × 100. Perda ≤ {lim} % → Approved; perda &gt; "
        "{lim} % → Rejected (não conforme). O resultado geral só é APPROVED se os {n} substratos de controle forem "
        "aprovados e os {itens} itens de inspeção abaixo forem Sim.",
    "compares the Deposition Control and Efficiency Test tabs with every saved sample (matched by run, e.g. DUNE_EVAP_#0002#). Save this sample first.":
        "compara as abas Deposition Control e Efficiency Test com todas as samples gravadas (pela run, ex.: "
        "DUNE_EVAP_#0002#). Grave esta sample antes.",
    "Test data": "Dados do teste",
    "Reference substrate ID": "ID do substrato de referência",
    "Installation date": "Data de instalação",
    "Mean room temperature (°C)": "Temperatura média da sala (°C)",
    "Mean relative humidity (%)": "Umidade relativa média (%)",
    "QC samples – mass and area (same columns as the Leptons Control Sheet)":
        "QC samples – massa e área (mesmas colunas da Leptons Control Sheet)",
    "Tested? = Yes when the control sample was tested in this run; only those are evaluated. x = UV transmission efficiency relative to the reference substrate: x ≥ {lim} → Approved, below → Rejected (no upper bound). The batch is approved only if at least {n} samples are tested and every tested sample passes. Density (µg/cm²) = (mass after − mass before) × 10⁶ / area (cm²).":
        "Testada? = Sim quando a sample de controle foi testada nesta run; só essas são avaliadas. x = eficiência de "
        "transmissão UV relativa ao substrato de referência: x ≥ {lim} → Approved, abaixo → Rejected (sem limite "
        "superior). O batch só é aprovado se pelo menos {n} samples forem testadas e todas as testadas passarem. "
        "Densidade (µg/cm²) = (massa depois − massa antes) × 10⁶ / área (cm²).",
    "No unsaved changes": "Nenhuma alteração não gravada",
    "Select batch and internal lot": "Escolher batch e internal lot",
    "1) Select the OPTO batch": "1) Escolha o OPTO batch",
    "Arrival": "Chegada",
    "Small boxes": "Caixas menores",
    "2) Select the internal lot(s) used in this deposition (small boxes, e.g. DUNE-CX-0004)":
        "2) Escolha o(s) internal lot(s) usados nesta deposição (caixas menores, ex.: DUNE-CX-0004)",
    "Select a batch above.": "Escolha um batch acima.",
    "Leptons cleaning lots: material that went through PTP removal and a new cleaning at Leptons Lab":
        "Leptons cleaning lots: material que passou por remoção de PTP e nova limpeza no Leptons Lab",
    "PTP removed": "PTP removido",
    "PTP removed?": "PTP removido?",
    "Add selected": "Adicionar selecionados",
    "Filter origin": "Origem dos filtros",
    "This deposition used more than one box or batch. Choose where each of the {n} filters came from: type a range below, or pick each filter in the grid.":
        "Esta deposição usou mais de uma caixa ou batch. Indique de onde veio cada um dos {n} filtros: digite uma "
        "faixa abaixo ou escolha cada filtro na grade.",
    "come from": "vêm de",
    "Clear all": "Limpar tudo",

    # mensagens ao gravar a sample
    "Sample saved.": "Sample gravada.",
    "Sample updated.": "Sample atualizada.",
    "Status: {status} – {n} item(s) of information still missing (listed on the sample page).":
        "Status: {status} – ainda faltam {n} informação(ões) (listadas na página da sample).",
    "Status: {status} – all the information is filled. An Admin can now review it.":
        "Status: {status} – todas as informações estão preenchidas. Um Admin já pode revisá-la.",
    "ID {n} (run {run}) is already used by another sample ({outras}). The ID comes from the run number, so two samples would show the same ID. Click Save anyway to keep it.":
        "O ID {n} (run {run}) já é usado por outra sample ({outras}). O ID vem do número da run, então duas samples "
        "mostrariam o mesmo ID. Clique em Salvar mesmo assim para manter.",
    "This sample was signed off. Saving removes the Final QA sign-off; confirm when saving.":
        "Esta sample tem sign-off. Gravar remove o Final QA sign-off; confirme ao gravar.",
    "This sample was signed off (Final QA) by {por} on {data}. Only an Admin can change a completed sample.":
        "Esta sample recebeu o sign-off (Final QA) de {por} em {data}. Só um Admin pode alterar uma sample Completed.",
    "Sample ID {n} ({pid}) deleted.": "Sample ID {n} ({pid}) excluída.",
    "Select at least one batch.": "Escolha pelo menos um batch.",
    "Enter the PID.": "Informe o PID.",
    "Mass control: masses missing at position {p} – {nome}.": "Mass control: faltam as massas na posição {p} – {nome}.",
    "Mass control: check the masses at position {p} – use numbers only.":
        "Mass control: confira as massas na posição {p} – use só números.",

    # informações que faltam (lista da página da sample e da revisão)
    "PID": "PID",
    "deposition date": "data da deposição",
    "responsible": "responsável",
    "batch / internal lot": "batch / internal lot",
    "position filters": "posição dos filtros",
    "PTP mass": "massa de PTP",
    "position {pos}": "posição {pos}",
    "run evaporation": "run evaporation",
    "inspector": "inspetor",
    "P02 PID": "PID da P02",
    "P03 PID": "PID da P03",
    "P14 PID": "PID da P14",
    "inspection date": "data da inspeção",
    "performed by": "realizado por",
    "{n} of {total} filters not fully classified": "{n} de {total} filtros sem classificação completa",
    "test date": "data do teste",
    "masses of {amostras}": "massas de {amostras}",
    "{n} of {total} post-immersion checks": "{n} de {total} verificações pós-imersão",
    "reference substrate ID": "ID do substrato de referência",
    "reference installation date": "data de instalação da referência",
    "room temperature": "temperatura da sala",
    "relative humidity": "umidade relativa",
    "Tested? not answered": "Testada? sem resposta",
    "mass before": "massa antes",
    "mass after": "massa depois",
    "area": "área",
    "relative efficiency": "eficiência relativa",
    "at least {n} tested samples": "pelo menos {n} samples testadas",

    # ---------------- revisão ----------------
    "Missing information – complete the sample before it can be reviewed.":
        "Faltam informações – complete a sample antes de ela poder ser revisada.",
    "All the information is filled. Check it in the report, then click Reviewed.":
        "Todas as informações estão preenchidas. Confira no relatório e clique em Revisada.",
    "Reviewed by {por} on {data}.": "Revisada por {por} em {data}.",
    "Mark sample {pid} as reviewed?\n\nFinal QA Sign-Off by: {nome}\nDate: {data}":
        "Marcar a sample {pid} como revisada?\n\nFinal QA Sign-Off por: {nome}\nData: {data}",
    "Only {perfis} users can mark a sample as reviewed.": "Só usuários {perfis} podem marcar uma sample como revisada.",
    "Only {perfis} users can review samples.": "Só usuários {perfis} podem revisar samples.",
    "This sample is not ready for review (or was already reviewed).":
        "Esta sample não está pronta para revisão (ou já foi revisada).",
    "Sample {pid} reviewed – status: {status}.": "Sample {pid} revisada – status: {status}.",

    # ---------------- QR code e PDFs ----------------
    "Scan to open the report options": "Escaneie para abrir as opções do relatório",
    "Copy link": "Copiar link",
    "Download QR image": "Baixar imagem do QR",
    "Report files saved in: {pasta}. Publish this folder at {url} so the QR link works.":
        "Arquivos do relatório gravados em: {pasta}. Publique esta pasta em {url} para o link do QR funcionar.",
    "The link works on devices connected to the same network as this computer, while this program is open. If it does not open, allow Python through the firewall for private networks.":
        "O link funciona em aparelhos conectados à mesma rede deste computador, enquanto este programa estiver "
        "aberto. Se não abrir, libere o Python no firewall para redes privadas.",
    "The report server could not start on port {porta} (port in use – is the desktop program open? It serves the same links while it is open).":
        "O servidor de relatórios não pôde iniciar na porta {porta} (porta em uso – o programa de mesa está aberto? "
        "Ele atende os mesmos links enquanto estiver aberto).",
    "{n} PDF(s) saved": "{n} PDF(s) gravado(s)",
    "Folder on this computer:": "Pasta neste computador:",
    "{n} failed": "{n} com erro",
    "Download all (ZIP)": "Baixar todos (ZIP)",

    # ---------------- importar .json ----------------
    "Import sample": "Importar sample",
    "Import sample (JSON)": "Importar sample (JSON)",
    "A sample with PID {pid} already exists (ID {ids})": "Já existe uma sample com o PID {pid} (ID {ids})",
    "The file is loaded into the sample form for review; nothing is saved until you click Save.":
        "O arquivo é carregado no formulário da sample para revisão; nada é gravado até você clicar em Salvar.",
    "Load over sample ID {n}": "Carregar sobre a sample ID {n}",
    "Load as a new sample": "Carregar como uma nova sample",
    "Choose a file created by <b>Export sample (JSON)</b> (in this app or in the desktop program). The sample opens in the form for review; it is saved only when you click Save.":
        "Escolha um arquivo criado por <b>Exportar sample (JSON)</b> (neste app ou no programa de mesa). A sample "
        "abre no formulário para revisão; só é gravada quando você clicar em Salvar.",
    "Load": "Carregar",
    "Choose a .json file.": "Escolha um arquivo .json.",
    "Could not read the file: ": "Não foi possível ler o arquivo: ",
    "The imported file is no longer available – import it again.":
        "O arquivo importado não está mais disponível – importe de novo.",
    "Import it as a new sample instead.": "Importe como uma nova sample.",
    "Could not load the sample from the file: ": "Não foi possível carregar a sample do arquivo: ",
    "Sample {pid} loaded from {arquivo}. Review the data, then click Save to create it.":
        "Sample {pid} carregada de {arquivo}. Confira os dados e clique em Salvar para criá-la.",
    "Sample {pid} loaded from {arquivo}. Review the data, then click Save to overwrite sample ID {n}.":
        "Sample {pid} carregada de {arquivo}. Confira os dados e clique em Salvar para substituir a sample ID {n}.",
    "These batches are not registered on this computer (they are kept with their codes): ":
        "Estes batches não estão cadastrados neste computador (são mantidos com os seus códigos): ",

    # ---------------- Sync Leptons Control Sheet ----------------
    "Compares the <b>Deposition Control</b> and <b>Efficiency Test</b> tabs of DUNE_Control.xlsx with every saved sample (matched by run, e.g. DUNE_EVAP_#0002#) and shows only what changed before applying.":
        "Compara as abas <b>Deposition Control</b> e <b>Efficiency Test</b> do DUNE_Control.xlsx com todas as samples "
        "gravadas (pela run, ex.: DUNE_EVAP_#0002#) e mostra só o que mudou antes de aplicar.",
    "Upload the spreadsheet": "Enviar a planilha",
    "Read it from this computer (path)": "Ler deste computador (caminho)",
    "The path is remembered for the next sync. An uploaded file is used only once.":
        "O caminho fica guardado para o próximo sync. Um arquivo enviado é usado só uma vez.",
    "Compare": "Comparar",
    "File not found: {caminho}": "Arquivo não encontrado: {caminho}",
    "Choose the spreadsheet file.": "Escolha o arquivo da planilha.",
    "Could not read the spreadsheet: ": "Não foi possível ler a planilha: ",
    "Everything is up to date: no differences between {abas} and the {n} saved samples.":
        "Tudo em dia: nenhuma diferença entre {abas} e as {n} samples gravadas.",
    "These changes were already applied or expired – run the sync again.":
        "Estas alterações já foram aplicadas ou expiraram – rode o sync de novo.",
    "Synced from {arquivo}: {n} change(s) applied": "Sync de {arquivo}: {n} alteração(ões) aplicada(s)",
    ", {n} new sample(s) created": ", {n} sample(s) nova(s) criada(s)",
    "Not changed (signed off – only an Admin can change them): {runs}.":
        "Não alteradas (com sign-off – só um Admin pode alterá-las): {runs}.",
    "changes": "alterações",
    "Changes": "Alterações",
    "Changes from {arquivo}": "Alterações de {arquivo}",
    "{n} saved samples checked · {mud} change(s) in {exist} existing sample(s); {novas} run(s) not in the app yet. Only the fields that differ are listed.":
        "{n} samples gravadas conferidas · {mud} alteração(ões) em {exist} sample(s) existente(s); {novas} run(s) "
        "ainda fora do app. Só os campos diferentes são listados.",
    "The sheet never erases saved values: empty cells are ignored, Position and Observations are only filled when empty, and '#' in MASS BEFORE (Efficiency Test) marks a sample as not tested only if it has no measurements yet. Visual Inspection and Cryogenic Immersion are not read from the sheet.":
        "A planilha nunca apaga valores gravados: células vazias são ignoradas, Position e Observations só são "
        "preenchidos quando estão vazios, e '#' em MASS BEFORE (Efficiency Test) marca uma sample como não testada só "
        "se ela ainda não tiver medidas. Visual Inspection e Cryogenic Immersion não são lidos da planilha.",
    "Already signed off – applying removes the Final QA sign-off, so they need a new sign-off:":
        "Já com sign-off – aplicar remove o Final QA sign-off, e elas precisam de um novo sign-off:",
    "Signed off (Completed) – only an Admin can change them, so these are skipped:":
        "Com sign-off (Completed) – só um Admin pode alterá-las, então estas são puladas:",
    "Create {n} new sample(s) for the runs that are not in the app yet (they stay Incomplete until batch, responsible and tests are filled)":
        "Criar {n} sample(s) nova(s) para as runs que ainda não estão no app (ficam Incomplete até batch, responsável "
        "e testes serem preenchidos)",
    "{n} change(s)": "{n} alteração(ões)",
    "Field": "Campo",
    "Current": "Atual",
    "New (sheet)": "Novo (planilha)",
    "Sheet row": "Linha da planilha",
    "(empty)": "(vazio)",
    "Apply changes": "Aplicar alterações",

    # ---------------- backup ----------------
    "Backup saved in {pasta}: ": "Backup gravado em {pasta}: ",
    "Backup warning: ": "Aviso do backup: ",
    "No database found to back up.": "Nenhum banco de dados encontrado para o backup.",

    # ---------------- batches ----------------
    "{n} batch": "{n} batch",
    "{n} batches": "{n} batches",
    "showing {n} of {total} batches": "mostrando {n} de {total} batches",
    "general batches received from OPTO, each split in small boxes (internal lots <span class=\"mono\">DUNE-CX-000X</span>)":
        "batches gerais recebidos da OPTO, cada um dividido em caixas menores (internal lots "
        "<span class=\"mono\">DUNE-CX-000X</span>)",
    "New batch": "Novo batch",
    "Total filters": "Total de filtros",
    "internal lots registered / small boxes": "internal lots cadastrados / caixas menores",
    "Arrival date": "Data de chegada",
    "Record date/time": "Data/hora do registro",
    "No batch matches this filter.": "Nenhum batch corresponde a este filtro.",
    "No batch registered yet – click <b>New batch</b>.": "Nenhum batch cadastrado ainda – clique em <b>Novo batch</b>.",
    "no tracking ID": "sem tracking ID",
    "no tracking ID yet": "ainda sem tracking ID",
    "Edit batch": "Editar batch",
    "Edit batch {lote}": "Editar batch {lote}",
    "Samples from this batch": "Samples deste batch",
    "Open supplier control file": "Abrir o arquivo de controle do fornecedor",
    "Delete batch {lote}": "Excluir o batch {lote}",
    "Batch {lote} (record ID {id}) and its {n} internal lot(s) will be deleted.":
        "O batch {lote} (ID do registro {id}) e os seus {n} internal lot(s) serão excluídos.",
    "{n} deposition sample(s) used it: they keep the batch codes in their records.":
        "{n} sample(s) de deposição o usaram: elas mantêm os códigos do batch nos seus registros.",
    "Delete batch": "Excluir batch",
    "filters per box": "filtros por caixa",
    "Internal lots registered": "Internal lots cadastrados",
    "General OPTO batch information": "Informações gerais do OPTO batch",
    "Supplier / company": "Fornecedor / empresa",
    "Recorded": "Registrado",
    "Supplier batch (old records)": "Batch do fornecedor (registros antigos)",
    "Internal lots (small boxes)": "Internal lots (caixas menores)",
    "filters in the registered boxes:": "filtros nas caixas cadastradas:",
    "No internal lot registered – use <b>Edit batch</b> to register the small boxes.":
        "Nenhum internal lot cadastrado – use <b>Editar batch</b> para cadastrar as caixas menores.",
    "Whole batch (no internal lot chosen)": "Batch inteiro (nenhum internal lot escolhido)",
    "{n} small box(es) without an internal lot code: they cannot be chosen for deposition.":
        "{n} caixa(s) menor(es) sem código de internal lot: não podem ser escolhidas para deposição.",
    "Substrate information": "Informações do substrato",
    "Dimensions": "Dimensões",
    "Thickness": "Espessura",
    "Finishing type": "Tipo de acabamento",
    "Arrival inspection": "Inspeção de chegada",
    "Broken filters?": "Filtros quebrados?",
    "Quantity matches supplier?": "A quantidade confere com o fornecedor?",
    "Cleaning procedure verified?": "Procedimento de limpeza verificado?",
    "Traceability and notes": "Rastreabilidade e notas",
    "Supplier control file": "Arquivo de controle do fornecedor",
    "file not found on this computer": "arquivo não encontrado neste computador",
    "Batch {lote} ({tracking}) saved.": "Batch {lote} ({tracking}) gravado.",
    "Batch {lote} ({tracking}) updated.": "Batch {lote} ({tracking}) atualizado.",
    "Batch {lote} ({tracking}) deleted.": "Batch {lote} ({tracking}) excluído.",

    # formulário do batch
    "OPTO batch arrival record · everything is saved together with <b>Save</b>":
        "registro de chegada do OPTO batch · tudo é gravado junto com <b>Salvar</b>",
    "{n} of {total} small boxes have no internal lot code ({prefixo}000X).":
        "{n} de {total} caixas menores não têm código de internal lot ({prefixo}000X).",
    "Boxes without a code cannot be chosen for deposition. Register them in the table below, or:":
        "Caixas sem código não podem ser escolhidas para deposição. Cadastre-as na tabela abaixo, ou:",
    "Fill them with the box numbers and save": "Preencher com os números das caixas e salvar",
    "Save without them": "Salvar sem elas",
    "OPTO batch (general batch ID)": "OPTO batch (ID do batch geral)",
    "Total number of filters (calculated)": "Número total de filtros (calculado)",
    "Small boxes inside the general batch": "Caixas menores dentro do batch geral",
    "Small box capacity (filters per box)": "Capacidade da caixa menor (filtros por caixa)",
    "Number of small boxes in the batch": "Número de caixas menores no batch",
    "Recalculate (capacity × boxes)": "Recalcular (capacidade × caixas)",
    "Small boxes:": "Caixas menores:",
    "Total filters = capacity × number of small boxes (the count can be changed per box below). Each small box is registered as {prefixo}000X (internal lot) under the OPTO batch.":
        "Total de filtros = capacidade × número de caixas menores (a contagem pode ser mudada por caixa abaixo). Cada "
        "caixa menor é cadastrada como {prefixo}000X (internal lot) dentro do OPTO batch.",
    "Internal lots (one per small box)": "Internal lots (um por caixa menor)",
    "Register each small box as {prefixo}000X (type only the number). The OPTO batch name is fixed; the internal lot is chosen in the sample form (Add batch / internal lot…).":
        "Cadastre cada caixa menor como {prefixo}000X (digite só o número). O nome do OPTO batch é fixo; o internal lot "
        "é escolhido no formulário da sample (Adicionar batch / internal lot…).",
    "OPTO batch (fixed)": "OPTO batch (fixo)",
    "Internal lot code": "Código do internal lot",
    "Enter the small box capacity and the number of small boxes.":
        "Informe a capacidade da caixa menor e o número de caixas menores.",
    "Fill empty rows ({prefixo}0001…)": "Preencher linhas vazias ({prefixo}0001…)",
    "Clear codes": "Limpar códigos",
    "Traceability document": "Documento de rastreabilidade",
    "Supplier control file (path on this computer)": "Arquivo de controle do fornecedor (caminho neste computador)",
    "Upload a new file": "Enviar um novo arquivo",
    "PDF, Excel, CSV, Word or text. An uploaded file is copied to the <span class=\"mono\">arquivos_lotes</span> folder and replaces the path above.":
        "PDF, Excel, CSV, Word ou texto. Um arquivo enviado é copiado para a pasta "
        "<span class=\"mono\">arquivos_lotes</span> e substitui o caminho acima.",
    "Open the saved file": "Abrir o arquivo gravado",
    "Box {i:02d}: type only the number (digits), e.g. 0004.": "Caixa {i:02d}: digite só o número (dígitos), ex.: 0004.",
    "Filters in box {i:02d} must be an integer.": "Os filtros da caixa {i:02d} devem ser um número inteiro.",
    "Internal lot code '{codigo}' is used by boxes {a:02d} and {b:02d}.":
        "O código de internal lot '{codigo}' é usado pelas caixas {a:02d} e {b:02d}.",
    "Enter the OPTO batch (general batch ID).": "Informe o OPTO batch (ID do batch geral).",
    "Number of small boxes must be an integer greater than zero.":
        "O número de caixas menores deve ser um inteiro maior que zero.",
    "Small box capacity must be an integer greater than zero.":
        "A capacidade da caixa menor deve ser um inteiro maior que zero.",
    "Enter the small box capacity and the number of small boxes (the total number of filters is calculated from them).":
        "Informe a capacidade da caixa menor e o número de caixas menores (o número total de filtros é calculado a "
        "partir deles).",

    # cleaning lots
    "Material that went through PTP removal and a new cleaning at Leptons Lab. Each cleaning lot becomes an internal lot (<span class=\"mono\">{prefixo}000X</span>) that can be chosen in the sample form.":
        "Material que passou por remoção de PTP e nova limpeza no Leptons Lab. Cada cleaning lot vira um internal lot "
        "(<span class=\"mono\">{prefixo}000X</span>) que pode ser escolhido no formulário da sample.",
    "Print list (PDF)": "Imprimir lista (PDF)",
    "Edit cleaning lot": "Editar cleaning lot",
    "New cleaning lot": "Novo cleaning lot",
    "Cleaning lot code": "Código do cleaning lot",
    "Cleaning date": "Data da limpeza",
    "Number of filters": "Número de filtros",
    "Result after cleaning": "Resultado após a limpeza",
    "Origin (previous PID / lot)": "Origem (PID / lote anterior)",
    "Cleaning procedure": "Procedimento de limpeza",
    "Delete cleaning lot {codigo}": "Excluir o cleaning lot {codigo}",
    "Depositions that already used it keep the code in their records.":
        "As deposições que já o usaram mantêm o código nos seus registros.",
    "No cleaning lot registered yet.": "Nenhum cleaning lot cadastrado ainda.",
    "Cleaning lot {codigo} saved.": "Cleaning lot {codigo} gravado.",
    "Cleaning lot {codigo} deleted. Depositions that already used it keep the code in their records.":
        "Cleaning lot {codigo} excluído. As deposições que já o usaram mantêm o código nos seus registros.",
    "Type only the number of the cleaning lot (e.g. 0001).": "Digite só o número do cleaning lot (ex.: 0001).",
    "Enter the cleaning date and the responsible.": "Informe a data da limpeza e o responsável.",
    "Number of filters must be an integer greater than zero.": "O número de filtros deve ser um inteiro maior que zero.",
    "Select the result after cleaning.": "Escolha o resultado após a limpeza.",
    "The cleaning lot {codigo} already exists.": "O cleaning lot {codigo} já existe.",

    # ---------------- usuários e senhas ----------------
    "Manage users": "Gerenciar usuários",
    "The same users as the desktop programs (usuarios.db). New users choose their own password at the first login.":
        "Os mesmos usuários dos programas de mesa (usuarios.db). Usuários novos escolhem a própria senha no primeiro login.",
    "Full name": "Nome completo",
    "Role": "Perfil",
    "Active": "Ativo",
    "Last login": "Último login",
    "Reset password": "Redefinir senha",
    "Temporary password": "Senha temporária",
    "Repeat": "Repetir",
    "Set": "Definir",
    "Deactivate user {user}?\nRecords made by this user are kept.":
        "Desativar o usuário {user}?\nOs registros feitos por ele são mantidos.",
    "Activate user {user}?\nRecords made by this user are kept.":
        "Ativar o usuário {user}?\nOs registros feitos por ele são mantidos.",
    "Deactivate": "Desativar",
    "Activate": "Ativar",
    "New user": "Novo usuário",
    "3 to 30 letters, numbers, dot, dash or underscore": "3 a 30 letras, números, ponto, hífen ou sublinhado",
    "Temporary password (min. {n})": "Senha temporária (mín. {n})",
    "Repeat password": "Repetir senha",
    "Create": "Criar",
    "User created. The person must choose a new password at the first login.":
        "Usuário criado. A pessoa deve escolher uma nova senha no primeiro login.",
    "User {user} updated.": "Usuário {user} atualizado.",
    "Temporary password set for {user}. The user must change it at the next login.":
        "Senha temporária definida para {user}. O usuário deve trocá-la no próximo login.",
    "You cannot deactivate your own account.": "Você não pode desativar a sua própria conta.",
    "User {user} deactivated.": "Usuário {user} desativado.",
    "User {user} activated.": "Usuário {user} ativado.",
    "Change password": "Trocar senha",
    "Change my password": "Trocar minha senha",
    "Current password": "Senha atual",
    "New password (min. {n})": "Nova senha (mín. {n})",
    "Repeat new password": "Repetir a nova senha",
    "Password changed.": "Senha trocada.",
    "The passwords do not match.": "As senhas não conferem.",
    # mensagens do leptons_auth (módulo dos programas de mesa)
    "Current password is incorrect.": "A senha atual está incorreta.",
    "The new passwords do not match.": "As novas senhas não conferem.",
    "Choose a password different from the current one.": "Escolha uma senha diferente da atual.",
    "The password cannot be the same as the username.": "A senha não pode ser igual ao nome de usuário.",
    "Enter the full name.": "Informe o nome completo.",
    "Invalid role.": "Perfil inválido.",
    "This username already exists.": "Este nome de usuário já existe.",
    "Invalid username or password.": "Usuário ou senha inválidos.",
    "User not found.": "Usuário não encontrado.",
    "There must be at least one active Admin.": "Deve haver pelo menos um Admin ativo.",

    # ---------------- login, entrada, saída ----------------
    "No users are registered yet. Open the desktop program once to create the first administrator account, then reload this page.":
        "Ainda não há usuários cadastrados. Abra o programa de mesa uma vez para criar a primeira conta de "
        "administrador e recarregue esta página.",
    "Choose a new password before continuing.": "Escolha uma nova senha antes de continuar.",
    "Sign in with your lab username and password.": "Entre com o seu usuário e senha do laboratório.",
    "Save and sign in": "Salvar e entrar",
    "Password": "Senha",
    "Log in": "Entrar",
    "Quit program": "Fechar o programa",
    "Starting": "Iniciando",
    "Welcome, {nome}": "Bem-vindo(a), {nome}",
    "Checking the databases…": "Conferindo os bancos de dados…",
    "Try again": "Tentar de novo",
    "Continue anyway": "Continuar mesmo assim",
    "Could not prepare the session: ": "Não foi possível preparar a sessão: ",
    "Ready": "Pronto",
    "{n} deposition samples found": "{n} samples de deposição encontradas",
    "{n} batch(es) in the batch database": "{n} batch(es) no banco de batches",
    "Batch database not readable": "Não foi possível ler o banco de batches",
    "Batch database not found": "Banco de batches não encontrado",
    "Closed": "Fechado",
    "Deposition Control closed": "Deposition Control fechado",
    "You can close this tab. Run <span class=\"mono\">python leptons_web.py</span> to open it again.":
        "Você pode fechar esta aba. Rode <span class=\"mono\">python leptons_web.py</span> para abrir de novo.",

    # ---------------- audit log ----------------
    "Who did what, in the desktop programs and in this app · latest 2000 matching entries":
        "Quem fez o quê, nos programas de mesa e neste app · últimas 2000 entradas encontradas",
    "Search user, action, details, date…": "Buscar usuário, ação, detalhes, data…",
    "When": "Quando",
    "User": "Usuário",
    "Program": "Programa",
    "Action": "Ação",
    "Details": "Detalhes",
    "No entries.": "Nenhuma entrada.",

    # ---------------- aba Statistics ----------------
    "Statistics": "Estatísticas",
    "Process statistics": "Estatísticas do processo",
    "all {n} samples": "todas as {n} samples",
    "{n} of {total} samples": "{n} de {total} samples",
    "deposited": "depositadas",
    "from": "de",
    "{n} without a deposition date": "{n} sem data de deposição",
    "All time": "Tudo",
    "Last 30 days": "Últimos 30 dias",
    "Last 90 days": "Últimos 90 dias",
    "This year": "Este ano",
    "From": "De",
    "To": "Até",
    "Clear": "Limpar",
    "Table": "Tabela",
    "No data in this selection.": "Nenhum dado nesta seleção.",
    "{n} filters deposited ({por} per sample)": "{n} filtros depositados ({por} por sample)",
    "Mass density · Center (P02)": "Densidade de massa · Center (P02)",
    "mean ± s.d. of {n} samples": "média ± desvio padrão de {n} samples",
    "{n} filters classified": "{n} filtros classificados",
    "post-immersion checks answered": "verificações pós-imersão respondidas",
    "measurements ≥ {x} (acceptance)": "medidas ≥ {x} (aceitação)",
    "{n} filters received": "{n} filtros recebidos",
    "Samples deposited per week": "Samples depositadas por semana",
    "Samples deposited per month": "Samples depositadas por mês",
    "by deposition date": "pela data de deposição",
    "Mass density · {pos}": "Densidade de massa · {pos}",
    "µg/cm², one value per sample": "µg/cm², um valor por sample",
    "Mass density per run": "Densidade de massa por run",
    "µg/cm² at the three positions; a jump shows a change in the process":
        "µg/cm² nas três posições; um salto indica uma mudança no processo",
    "Radial uniformity": "Uniformidade radial",
    "External (P14) ÷ Center (P02) mass density; 1 = uniform":
        "densidade de massa External (P14) ÷ Center (P02); 1 = uniforme",
    "External ÷ Center": "External ÷ Center",
    "ratio": "razão",
    "Samples per internal lot": "Samples por internal lot",
    "box (DUNE-CX-000X) or cleaning lot the filters came from": "caixa (DUNE-CX-000X) ou cleaning lot de onde vieram os filtros",
    "Classification": "Classificação",
    "filters per class": "filtros por classe",
    "Defects found": "Defeitos encontrados",
    "filters with each defect, of {n} inspected": "filtros com cada defeito, de {n} inspecionados",
    "Mass change after immersion": "Variação de massa após a imersão",
    "Mass change": "Variação de massa",
    "% per sample (P02, P03, P14); acceptance within ±{x} %": "% por sample (P02, P03, P14); aceitação dentro de ±{x} %",
    "Relative efficiency": "Eficiência relativa",
    "tested samples; acceptance ≥ {x}": "samples testadas; aceitação ≥ {x}",
    "limit {x}": "limite {x}",
    "Witness sample density": "Densidade das samples testemunha",
    "µg/cm², samples measured for optical efficiency": "µg/cm², samples medidas na optical efficiency",
    "n = {n} · mean {media} · s.d. {dp} · min {min} · max {max}":
        "n = {n} · média {media} · d.p. {dp} · mín. {min} · máx. {max}",
    "no data": "sem dados",
    "count": "quantidade",
    "month": "mês",
    "week of": "semana de",
    "week of {d}": "semana de {d}",
    "samples": "samples",
}

# mensagens com números no meio, vindas do leptons_auth: (expressão regular, modelo da tradução)
PADROES = [
    (r"The password must have at least (\d+) characters\.", r"A senha deve ter pelo menos \1 caracteres."),
    (r"Too many failed attempts\. Try again in (\d+) min\.", r"Tentativas demais com erro. Tente de novo em \1 min."),
    (r"Too many failed attempts\. Account locked for (\d+) min\.",
     r"Tentativas demais com erro. Conta bloqueada por \1 min."),
]

# textos do JavaScript (editar.js, lote.js e os pequenos scripts das páginas): T("texto {n}", {n: ...})
PT_JS = {
    "In progress": "Em andamento",
    "Not filled": "Não preenchido",
    "Unsaved changes": "Alterações não gravadas",
    "No unsaved changes": "Nenhuma alteração não gravada",
    "Leave without saving? The changes will be lost.": "Sair sem salvar? As alterações serão perdidas.",
    "This sample was signed off (Final QA) by {por}.\n\nSaving changes removes the sign-off: the sample goes back to 'To be reviewed' and needs a new Final QA sign-off. Continue?":
        "Esta sample recebeu o sign-off (Final QA) de {por}.\n\nGravar alterações remove o sign-off: a sample volta "
        "para 'To be reviewed' e precisa de um novo Final QA sign-off. Continuar?",
    "{n}/{total} filters complete": "{n}/{total} filtros completos",
    "Clear all {n} rows of the inspection table?": "Limpar as {n} linhas da tabela de inspeção?",
    "reviewed": "revisado",
    "pending supervisor review": "aguardando revisão do supervisor",
    "Overall result: APPROVED ({rev})": "Resultado geral: APPROVED ({rev})",
    "Overall result: REJECTED ({rev})": "Resultado geral: REJECTED ({rev})",
    "Overall result: in progress ({n}/{total} filled)": "Resultado geral: em andamento ({n}/{total} preenchidos)",
    "Overall result: in progress ({n}/{total} samples measured)":
        "Resultado geral: em andamento ({n}/{total} samples medidas)",
    "Overall result: not evaluated": "Resultado geral: não avaliado",
    "Not tested": "Não testada",
    "installation date is after the test date": "a data de instalação é depois da data do teste",
    "reference in use for {n} days (limit: 6 months)": "referência em uso há {n} dias (limite: 6 meses)",
    "Reference in use for {n} days (limit: 6 months)": "Referência em uso há {n} dias (limite: 6 meses)",
    "Remove this file from the sample? (The file itself is not deleted.)":
        "Remover este arquivo da sample? (O arquivo em si não é apagado.)",
    "No batch selected – add at least one.": "Nenhum batch selecionado – adicione pelo menos um.",
    "Remove from this deposition": "Remover desta deposição",
    "Internal lot used: ": "Internal lot usado: ",
    "Internal lots used: ": "Internal lots usados: ",
    "No internal lot selected": "Nenhum internal lot selecionado",
    "{n} selected": "{n} selecionado(s)",
    "Total filters: ": "Total de filtros: ",
    "No batch selected": "Nenhum batch selecionado",
    "whole batch": "batch inteiro",
    "Filter origin: ": "Origem dos filtros: ",
    "{n}/{total} assigned": "{n}/{total} atribuídos",
    "not assigned yet – click Filter origin…": "ainda não atribuída – clique em Origem dos filtros…",
    "of {n} in the box": "de {n} na caixa",
    "{n} filter(s)": "{n} filtro(s)",
    "more than the box had": "mais do que a caixa tinha",
    "{n}/{total} filters assigned": "{n}/{total} filtros atribuídos",
    "Enter the first and the last filter (1 to {n}).": "Informe o primeiro e o último filtro (1 a {n}).",
    "Selected in this deposition": "Escolhido nesta deposição",
    "Used in PID {pid}": "Usado no PID {pid}",
    "Available": "Disponível",
    "No OPTO batches registered in lotes.db.": "Nenhum OPTO batch cadastrado no lotes.db.",
    "No internal lots are registered for this batch. Register them in the Batches tab (Edit batch), or click Add selected to add the batch without an internal lot.":
        "Nenhum internal lot cadastrado para este batch. Cadastre-os na aba Batches (Editar batch), ou clique em "
        "Adicionar selecionados para adicionar o batch sem internal lot.",
    "No Leptons cleaning lots are registered. Register them in the Batches tab (Leptons cleaning lots).":
        "Nenhum Leptons cleaning lot cadastrado. Cadastre-os na aba Batches (Leptons cleaning lots).",
    "Select a batch first.": "Escolha um batch antes.",
    "Select at least one internal lot.": "Escolha pelo menos um internal lot.",
    "Internal lot {codigo} was already used (PID {pid}).\n\nUse it again in this deposition?":
        "O internal lot {codigo} já foi usado (PID {pid}).\n\nUsar de novo nesta deposição?",
    "Select at least one cleaning lot.": "Escolha pelo menos um cleaning lot.",
    "Cleaning lot {codigo} has result '{res}'.\n\nUse it in this deposition anyway?":
        "O cleaning lot {codigo} tem resultado '{res}'.\n\nUsar nesta deposição mesmo assim?",
    "Cleaning lot {codigo} was already used (PID {pid}).\n\nUse it again in this deposition?":
        "O cleaning lot {codigo} já foi usado (PID {pid}).\n\nUsar de novo nesta deposição?",
    "Loading batches…": "Carregando os batches…",
    "Could not read the batch database: ": "Não foi possível ler o banco de batches: ",
    "Enter the capacity and the number of small boxes.": "Informe a capacidade e o número de caixas menores.",
    "{n} small box(es) × {cap} filters = {total} filters.": "{n} caixa(s) menor(es) × {cap} filtros = {total} filtros.",
    "{n} small box(es), {total} filters (custom count in some boxes).":
        "{n} caixa(s) menor(es), {total} filtros (contagem própria em algumas caixas).",
    "Internal lots: {n}/{total} registered": "Internal lots: {n}/{total} cadastrados",
    "Enter the OPTO batch first.": "Informe o OPTO batch antes.",
    "Enter the number of small boxes.": "Informe o número de caixas menores.",
    "Generating PDFs…": "Gerando os PDFs…",
    "Copied": "Copiado",
    "sample": "sample",
    "samples": "samples",
}
