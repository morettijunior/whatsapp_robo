import tkinter as tk
from tkinter import messagebox, filedialog
import json
import os
import random
import string
from pathlib import Path


def obter_caminho_config():
    docs_path = Path.home() / "Documents" / "RondochassisBot"
    docs_path.mkdir(parents=True, exist_ok=True)
    return docs_path / "config_sistema.json"


CONFIG_FILE = obter_caminho_config()


def carregar_config():
    padrao = {
        "db_dsn": "Servidor:c:/tga/Dados/TGA.FDB",
        "smtp_host": "smtp.hostinger.com",
        "smtp_port": 465,
        "imap_host": "imap.hostinger.com",
        "imap_port": 993,
        "smtp_user": "financeiro@rondochassis.com.br",
        "smtp_pass": "sua_senha_aqui",
        "logo_banco": "",
        "pasta_nfe_pdf": r"\\Servidor\tga\Nfe\PDF",
        "pasta_nfe_xml": r"\\Servidor\tga\Nfe\XML",
        "pasta_nfs_pdf": r"\\Servidor\tga\NFS-e\XML",
        "numeros_ignorados": "5566999847335, 556634210400, 5566999840793, 5566999101124",
        "whatsapp_vendas": "",
        "whatsapp_oficina": ""
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
                padrao.update(dados)
        except Exception:
            pass
    return padrao


def salvar_config(
    dsn, smtp_host, smtp_port, imap_host, imap_port, user, senha,
    logo_path, pasta_nfe_pdf, pasta_nfe_xml, pasta_nfs_pdf,
    numeros_ignorados, whatsapp_vendas, whatsapp_oficina
):
    dados = {
        "db_dsn": dsn.strip(),
        "smtp_host": smtp_host.strip(),
        "smtp_port": int(smtp_port),
        "imap_host": imap_host.strip(),
        "imap_port": int(imap_port),
        "smtp_user": user.strip(),
        "smtp_pass": senha,
        "logo_banco": logo_path.strip(),
        "pasta_nfe_pdf": pasta_nfe_pdf.strip(),
        "pasta_nfe_xml": pasta_nfe_xml.strip(),
        "pasta_nfs_pdf": pasta_nfs_pdf.strip(),
        "numeros_ignorados": numeros_ignorados.strip(),
        "whatsapp_vendas": whatsapp_vendas.strip(),
        "whatsapp_oficina": whatsapp_oficina.strip()
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)
    messagebox.showinfo("Sucesso", f"Configurações salvas com sucesso em:\n{CONFIG_FILE}")


def gerar_senha_aleatoria(tamanho=6):
    caracteres = string.ascii_uppercase + string.digits
    return "".join(random.choice(caracteres) for _ in range(tamanho))


def resetar_senha_cliente_por_cnpj(doc_digitado):
    from service_bd import buscar_cliente_por_documento, salvar_ou_atualizar_senha_robo
    from service_email import enviar_email_senha_provisoria
    
    cliente = buscar_cliente_por_documento(doc_digitado)
    if cliente.get("status") == "inativo":
        messagebox.showwarning("Cadastro Inativo", "O cadastro deste CNPJ/CPF consta como INATIVO no ERP!")
        return
    if cliente.get("status") != "encontrado":
        messagebox.showerror("Erro", "CNPJ/CPF não encontrado na base de dados do ERP ou formato inválido!")
        return
        
    email = cliente.get("email")
    if not email:
        messagebox.showwarning("Atenção", "O cliente foi encontrado, mas não possui e-mail cadastrado no ERP!")
        return
        
    nova_senha = gerar_senha_aleatoria()
    codcfo = cliente.get("codcfo")
    nome = cliente.get("nome")
    
    sucesso_db = salvar_ou_atualizar_senha_robo(codcfo, nome, email, nova_senha)
    if not sucesso_db:
        messagebox.showerror("Erro", "Erro ao gravar a nova senha na tabela ROBOWHATS.")
        return
        
    sucesso_email = enviar_email_senha_provisoria(email, nome, nova_senha)
    if sucesso_email:
        messagebox.showinfo("Sucesso", f"Nova senha provisória gerada e enviada para:\n{email}")
    else:
        messagebox.showerror("Erro", "A senha foi gerada, mas houve uma falha ao enviar o e-mail SMTP.")


def mostrar_notas_lancamento(parent):
    """Exibe a janela pop-up com o release notes da versão 1.0.3"""
    top = tk.Toplevel(parent)
    top.title("Release Notes - Versão 1.0.3")
    top.geometry("500x480")
    top.minsize(440, 420)
    
    tk.Label(top, text="🚀 Bot Rondochassis - Versão 1.0.3", font=("Arial", 11, "bold")).pack(pady=(12, 5))
    tk.Label(top, text="Data de Atualização: 17/11/2026", font=("Arial", 9, "italic"), fg="#555").pack(pady=(0, 10))

    frame_txt = tk.Frame(top)
    frame_txt.pack(fill="both", expand=True, padx=15, pady=5)

    scrollbar = tk.Scrollbar(frame_txt)
    scrollbar.pack(side="right", fill="y")

    text_info = tk.Text(frame_txt, wrap="word", yscrollcommand=scrollbar.set, font=("Arial", 9), padx=8, pady=8)
    text_info.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=text_info.yview)

    changelog = (
        "📌 NOVIDADES E MELHORIAS (v1.0.3):\n\n"
        "• Estabilidade e Operação Contínua 24/7:\n"
        "  - Webhook não-bloqueante para atendimento simultâneo sem filas.\n"
        "  - Resolução automática de identificadores privados (@lid / remoteJidAlt).\n"
        "  - Filtro anti-represamento: ignora mensagens antigas (>180s) após reconexão.\n"
        "  - Pausa automática de 30 minutos quando o atendente responde pelo celular.\n"
        "  - Submenu de período (30, 60 e 90 dias) e atalho 'P' após o login.\n\n"
        "--------------------------------------------------\n"
        "📌 RECURSOS DA VERSÃO 1.0.2:\n\n"
        "• Envio Automático de NF-e (XML/PDF) e NFS-e (PDF):\n"
        "  - Busca automática de NF-e por Ano/Mês e Chave de Acesso (TNFE).\n"
        "  - Busca automática de NFS-e Nacional pelo Recibo (TNFEMUNICIPAL).\n"
        "  - Suporte completo a múltiplas notas em pedidos agrupados (faturas).\n"
        "  - Configuração dos diretórios de NF-e e NFS-e diretamente no painel.\n\n"
        "--------------------------------------------------\n"
        "📌 RECURSOS DA VERSÃO 1.0.1:\n\n"
        "• Relatório agrupado por pedido no chat do WhatsApp.\n"
        "• Atendimento humano no chat para o Setor Financeiro.\n"
        "• Redirecionamento via link direto (wa.me) para Vendas e Oficina.\n"
        "• Unificação Financeira de 90 Dias (ERP Firebird / TGA.FDB)."
    )

    text_info.insert("1.0", changelog)
    text_info.config(state="disabled")

    tk.Button(top, text="Fechar", bg="#6c757d", fg="white", font=("Arial", 9, "bold"), command=top.destroy).pack(pady=10)


def abrir_tela_config():
    config = carregar_config()

    root = tk.Tk()
    root.title("Whatsapp Robo Financeiro - v1.0.3")
    root.geometry("560x735")
    root.minsize(540, 715)

    # Topo com título e botão de release
    header_frame = tk.Frame(root)
    header_frame.pack(fill="x", padx=15, pady=(8, 4))

    tk.Label(header_frame, text="Painel Administrativo - Bot Rondochassis", font=("Arial", 12, "bold")).pack(side="left")
    
    btn_release = tk.Button(
        header_frame, text="Versão 1.0.3 ℹ️", bg="#17a2b8", fg="white",
        font=("Arial", 8, "bold"), command=lambda: mostrar_notas_lancamento(root)
    )
    btn_release.pack(side="right")

    # 1. Configurações de Conexão e E-mail
    frame_cfg = tk.LabelFrame(root, text=" Configurações de Servidor e E-mail ", padx=10, pady=6)
    frame_cfg.pack(fill="x", padx=15, pady=4)

    tk.Label(frame_cfg, text="DSN Firebird:").pack(anchor="w")
    entry_dsn = tk.Entry(frame_cfg)
    entry_dsn.pack(fill="x", pady=1)
    entry_dsn.insert(0, config.get("db_dsn", ""))

    row_hosts = tk.Frame(frame_cfg)
    row_hosts.pack(fill="x", pady=2)

    col_smtp = tk.Frame(row_hosts)
    col_smtp.pack(side="left", fill="x", expand=True, padx=(0, 8))
    tk.Label(col_smtp, text="SMTP Host / Porta:").pack(anchor="w")
    sub_smtp = tk.Frame(col_smtp)
    sub_smtp.pack(fill="x")
    entry_smtp_host = tk.Entry(sub_smtp)
    entry_smtp_host.pack(side="left", fill="x", expand=True, padx=(0, 4))
    entry_smtp_host.insert(0, config.get("smtp_host", "smtp.hostinger.com"))
    entry_smtp_port = tk.Entry(sub_smtp, width=6)
    entry_smtp_port.pack(side="left")
    entry_smtp_port.insert(0, str(config.get("smtp_port", 465)))

    col_imap = tk.Frame(row_hosts)
    col_imap.pack(side="left", fill="x", expand=True)
    tk.Label(col_imap, text="IMAP Host / Porta:").pack(anchor="w")
    sub_imap = tk.Frame(col_imap)
    sub_imap.pack(fill="x")
    entry_imap_host = tk.Entry(sub_imap)
    entry_imap_host.pack(side="left", fill="x", expand=True, padx=(0, 4))
    entry_imap_host.insert(0, config.get("imap_host", "imap.hostinger.com"))
    entry_imap_port = tk.Entry(sub_imap, width=6)
    entry_imap_port.pack(side="left")
    entry_imap_port.insert(0, str(config.get("imap_port", 993)))

    row_cred = tk.Frame(frame_cfg)
    row_cred.pack(fill="x", pady=2)

    col_user = tk.Frame(row_cred)
    col_user.pack(side="left", fill="x", expand=True, padx=(0, 8))
    tk.Label(col_user, text="E-mail Remetente (User):").pack(anchor="w")
    entry_user = tk.Entry(col_user)
    entry_user.pack(fill="x")
    entry_user.insert(0, config.get("smtp_user", ""))

    col_pass = tk.Frame(row_cred)
    col_pass.pack(side="left", fill="x", expand=True)
    tk.Label(col_pass, text="Senha do E-mail:").pack(anchor="w")
    entry_pass = tk.Entry(col_pass, show="*")
    entry_pass.pack(fill="x")
    entry_pass.insert(0, config.get("smtp_pass", ""))

    # 2. Pastas de Notas Fiscais (NF-e e NFS-e)
    frame_notas = tk.LabelFrame(root, text=" Diretórios de Notas Fiscais (NF-e e NFS-e) ", padx=10, pady=6)
    frame_notas.pack(fill="x", padx=15, pady=4)

    def criar_linha_pasta(parent, label_txt, valor_inicial):
        tk.Label(parent, text=label_txt).pack(anchor="w")
        row = tk.Frame(parent)
        row.pack(fill="x", pady=(0, 3))
        ent = tk.Entry(row, font=("Arial", 9))
        ent.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ent.insert(0, valor_inicial)

        def escolher_pasta():
            pasta = filedialog.askdirectory(title=f"Selecionar - {label_txt}")
            if pasta:
                ent.delete(0, tk.END)
                ent.insert(0, pasta)

        tk.Button(row, text="Procurar...", font=("Arial", 8), command=escolher_pasta).pack(side="left")
        return ent

    entry_nfe_pdf = criar_linha_pasta(
        frame_notas,
        "Pasta Base NF-e PDF (Ex: \\\\Servidor\\tga\\Nfe\\PDF ou C:\\tga\\Nfe\\PDF):",
        config.get("pasta_nfe_pdf", r"\\Servidor\tga\Nfe\PDF")
    )
    entry_nfe_xml = criar_linha_pasta(
        frame_notas,
        "Pasta Base NF-e XML (Ex: \\\\Servidor\\tga\\Nfe\\XML ou C:\\tga\\Nfe\\XML):",
        config.get("pasta_nfe_xml", r"\\Servidor\tga\Nfe\XML")
    )
    entry_nfs_pdf = criar_linha_pasta(
        frame_notas,
        "Pasta Base NFS-e PDF (Ex: \\\\Servidor\\tga\\NFS-e\\XML ou C:\\tga\\NFS-e\\XML):",
        config.get("pasta_nfs_pdf", r"\\Servidor\tga\NFS-e\XML")
    )

    # 3. Logo do Banco (Boleto)
    frame_logo = tk.LabelFrame(root, text=" Configuração da Logo do Banco (Boleto PDF) ", padx=10, pady=6)
    frame_logo.pack(fill="x", padx=15, pady=4)

    row_logo = tk.Frame(frame_logo)
    row_logo.pack(fill="x", pady=1)

    entry_logo_path = tk.Entry(row_logo, font=("Arial", 9))
    entry_logo_path.pack(side="left", fill="x", expand=True, padx=(0, 6))
    entry_logo_path.insert(0, config.get("logo_banco", ""))

    def procurar_logo():
        caminho = filedialog.askopenfilename(
            title="Selecionar Logo do Banco",
            filetypes=[("Arquivos de Imagem", "*.bmp;*.png;*.jpg;*.jpeg"), ("Todos os arquivos", "*.*")]
        )
        if caminho:
            entry_logo_path.delete(0, tk.END)
            entry_logo_path.insert(0, caminho)

    tk.Button(row_logo, text="Procurar...", font=("Arial", 8), command=procurar_logo).pack(side="left")

    # 4. Redirecionamento de Setores (Vendas e Oficina)
    frame_setores = tk.LabelFrame(root, text=" Redirecionamento de Setores (Ex: 5566999999999) ", padx=10, pady=6)
    frame_setores.pack(fill="x", padx=15, pady=4)

    row_setores = tk.Frame(frame_setores)
    row_setores.pack(fill="x")

    col_vendas = tk.Frame(row_setores)
    col_vendas.pack(side="left", fill="x", expand=True, padx=(0, 8))
    tk.Label(col_vendas, text="WhatsApp Vendas:").pack(anchor="w")
    entry_vendas = tk.Entry(col_vendas, font=("Arial", 9))
    entry_vendas.pack(fill="x")
    entry_vendas.insert(0, config.get("whatsapp_vendas", ""))

    col_oficina = tk.Frame(row_setores)
    col_oficina.pack(side="left", fill="x", expand=True)
    tk.Label(col_oficina, text="WhatsApp Oficina:").pack(anchor="w")
    entry_oficina = tk.Entry(col_oficina, font=("Arial", 9))
    entry_oficina.pack(fill="x")
    entry_oficina.insert(0, config.get("whatsapp_oficina", ""))

    # 5. Números Ignorados
    frame_ign = tk.LabelFrame(root, text=" Números Ignorados pelo Bot (separados por vírgula) ", padx=10, pady=6)
    frame_ign.pack(fill="x", padx=15, pady=4)

    entry_ign = tk.Entry(frame_ign, font=("Arial", 9))
    entry_ign.pack(fill="x")
    entry_ign.insert(0, config.get("numeros_ignorados", ""))

    # 6. Reset Manual de Senha
    frame_reset = tk.LabelFrame(root, text=" Reset Manual de Senha (CNPJ ou CPF) ", padx=10, pady=6)
    frame_reset.pack(fill="x", padx=15, pady=4)

    row_reset = tk.Frame(frame_reset)
    row_reset.pack(fill="x")
    
    entry_doc_reset = tk.Entry(row_reset, font=("Arial", 9))
    entry_doc_reset.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def botao_reset_click():
        doc = entry_doc_reset.get().strip()
        if not doc:
            messagebox.showwarning("Aviso", "Digite o CNPJ ou CPF para resetar a senha.")
            return
        resetar_senha_cliente_por_cnpj(doc)

    tk.Button(
        row_reset, text="Gerar e Enviar Nova Senha", bg="#007bff", fg="white",
        font=("Arial", 8, "bold"), command=botao_reset_click
    ).pack(side="left")

    def botao_salvar_click():
        salvar_config(
            entry_dsn.get(),
            entry_smtp_host.get(),
            entry_smtp_port.get(),
            entry_imap_host.get(),
            entry_imap_port.get(),
            entry_user.get(),
            entry_pass.get(),
            entry_logo_path.get(),
            entry_nfe_pdf.get(),
            entry_nfe_xml.get(),
            entry_nfs_pdf.get(),
            entry_ign.get(),
            entry_vendas.get(),
            entry_oficina.get()
        )

    tk.Button(
        root, text="Salvar Configurações", bg="#28a745", fg="white",
        font=("Arial", 10, "bold"), command=botao_salvar_click
    ).pack(pady=8)

    root.mainloop()


if __name__ == "__main__":
    abrir_tela_config()