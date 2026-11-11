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
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "db_dsn": "Servidor:c:/tga/Dados/TGA.FDB",
        "smtp_host": "smtp.hostinger.com",
        "smtp_port": 465,
        "imap_host": "imap.hostinger.com",
        "imap_port": 993,
        "smtp_user": "financeiro@rondochassis.com.br",
        "smtp_pass": "sua_senha_aqui",
        "logo_banco": "",
        "numeros_ignorados": "5566999847335, 556634210400, 5566999840793, 5566999101124"
    }

def salvar_config(dsn, smtp_host, smtp_port, imap_host, imap_port, user, senha, logo_path, numeros_ignorados):
    dados = {
        "db_dsn": dsn,
        "smtp_host": smtp_host,
        "smtp_port": int(smtp_port),
        "imap_host": imap_host,
        "imap_port": int(imap_port),
        "smtp_user": user,
        "smtp_pass": senha,
        "logo_banco": logo_path,
        "numeros_ignorados": numeros_ignorados
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
    """Exibe a janela pop-up com o release notes da versão 1.0.1"""
    top = tk.Toplevel(parent)
    top.title("Release Notes - Versão 1.0.1")
    top.geometry("480x450")
    top.minsize(420, 400)
    
    tk.Label(top, text="🚀 Bot Rondochassis - Versão 1.0.1", font=("Arial", 11, "bold")).pack(pady=(12, 5))
    tk.Label(top, text="Data de Atualização: Novembro de 2026", font=("Arial", 9, "italic"), fg="#555").pack(pady=(0, 10))

    frame_txt = tk.Frame(top)
    frame_txt.pack(fill="both", expand=True, padx=15, pady=5)

    scrollbar = tk.Scrollbar(frame_txt)
    scrollbar.pack(side="right", fill="y")

    text_info = tk.Text(frame_txt, wrap="word", yscrollcommand=scrollbar.set, font=("Arial", 9), padx=8, pady=8)
    text_info.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=text_info.yview)

    changelog = (
        "📌 NOVIDADES E CORREÇÕES (v1.0.1):\n\n"
        "• Reestruturação do Menu Principal (WhatsApp):\n"
        "  - Menu principal simplificado de 4 opções direcionadas.\n"
        "  - Eliminação da confusão anterior entre Contas a Pagar/Receber.\n"
        "  - Redirecionamento direto para Atendentes (Financeiro, Vendas, Oficina).\n"
        "  - Agrupamento do fluxo de Login/Senhas/Boletos no submenu de Gestão Financeira.\n\n"
        "• Correções de Comunicação & Webhook:\n"
        "  - Tratamento do esquema de URL HTTP (http://) no carregamento de variáveis .env.\n"
        "  - Estabilização da rota do webhook para conexões via IP / Docker (host.docker.internal).\n"
        "  - Tratamento aprimorado de eventos do WhatsApp para evitar respostas sem texto (no_text).\n\n"
        "--------------------------------------------------\n"
        "📌 RECURSOS DA VERSÃO 1.0.0:\n\n"
        "• Unificação Financeira de 90 Dias (ERP Firebird / TGA.FDB).\n"
        "• Automação de Boleto & Pix via WhatsApp (Sicoob / Evolution API).\n"
        "• Painel Administrativo em Tkinter para reset manual de senhas e configurações de servidor."
    )

    text_info.insert("1.0", changelog)
    text_info.config(state="disabled")

    tk.Button(top, text="Fechar", bg="#6c757d", fg="white", font=("Arial", 9, "bold"), command=top.destroy).pack(pady=10)

def abrir_tela_config():
    config = carregar_config()

    root = tk.Tk()
    root.title("Whatsapp Robo Financeiro - v1.0.1")
    root.geometry("500x720")
    root.minsize(500, 700)

    # Topo com título e botão de release
    header_frame = tk.Frame(root)
    header_frame.pack(fill="x", padx=15, pady=10)

    tk.Label(header_frame, text="Painel Administrativo - Bot Rondochassis", font=("Arial", 12, "bold")).pack(side="left")
    
    btn_release = tk.Button(header_frame, text="Versão 1.0.1 ℹ️", bg="#17a2b8", fg="white", font=("Arial", 8, "bold"), command=lambda: mostrar_notas_lancamento(root))
    btn_release.pack(side="right")

    # Frame Configurações de Conexão e SMTP/IMAP
    frame_cfg = tk.LabelFrame(root, text=" Configurações de Servidor e E-mail ", padx=10, pady=10)
    frame_cfg.pack(fill="x", padx=15, pady=5)

    tk.Label(frame_cfg, text="DSN Firebird:").pack(anchor="w")
    entry_dsn = tk.Entry(frame_cfg, width=55)
    entry_dsn.pack(fill="x", pady=2)
    entry_dsn.insert(0, config.get("db_dsn", ""))

    tk.Label(frame_cfg, text="SMTP Host / Porta:").pack(anchor="w")
    row_smtp = tk.Frame(frame_cfg)
    row_smtp.pack(fill="x", pady=2)
    entry_smtp_host = tk.Entry(row_smtp, width=35)
    entry_smtp_host.pack(side="left", padx=(0, 5))
    entry_smtp_host.insert(0, config.get("smtp_host", "smtp.hostinger.com"))
    
    entry_smtp_port = tk.Entry(row_smtp, width=10)
    entry_smtp_port.pack(side="left")
    entry_smtp_port.insert(0, str(config.get("smtp_port", 465)))

    tk.Label(frame_cfg, text="IMAP Host / Porta:").pack(anchor="w")
    row_imap = tk.Frame(frame_cfg)
    row_imap.pack(fill="x", pady=2)
    entry_imap_host = tk.Entry(row_imap, width=35)
    entry_imap_host.pack(side="left", padx=(0, 5))
    entry_imap_host.insert(0, config.get("imap_host", "imap.hostinger.com"))
    
    entry_imap_port = tk.Entry(row_imap, width=10)
    entry_imap_port.pack(side="left")
    entry_imap_port.insert(0, str(config.get("imap_port", 993)))

    tk.Label(frame_cfg, text="E-mail Remetente (User):").pack(anchor="w")
    entry_user = tk.Entry(frame_cfg, width=55)
    entry_user.pack(fill="x", pady=2)
    entry_user.insert(0, config.get("smtp_user", ""))

    tk.Label(frame_cfg, text="Senha do E-mail:").pack(anchor="w")
    entry_pass = tk.Entry(frame_cfg, width=55, show="*")
    entry_pass.pack(fill="x", pady=2)
    entry_pass.insert(0, config.get("smtp_pass", ""))

    # Frame Números Ignorados
    frame_ign = tk.LabelFrame(root, text=" Números Ignorados pelo Bot (separados por vírgula) ", padx=10, pady=10)
    frame_ign.pack(fill="x", padx=15, pady=8)

    entry_ign = tk.Entry(frame_ign, width=55, font=("Arial", 9))
    entry_ign.pack(fill="x", pady=2)
    entry_ign.insert(0, config.get("numeros_ignorados", ""))

    # Frame Reset Manual de Senha
    frame_reset = tk.LabelFrame(root, text=" Reset Manual de Senha (Caso o cliente solicite) ", padx=10, pady=10)
    frame_reset.pack(fill="x", padx=15, pady=8)

    tk.Label(frame_reset, text="Digite o CNPJ ou CPF do Cliente:").pack(anchor="w")
    row_reset = tk.Frame(frame_reset)
    row_reset.pack(fill="x", pady=5)
    
    entry_doc_reset = tk.Entry(row_reset, width=32, font=("Arial", 10))
    entry_doc_reset.pack(side="left", padx=(0, 10))

    def botao_reset_click():
        doc = entry_doc_reset.get().strip()
        if not doc:
            messagebox.showwarning("Aviso", "Digite o CNPJ ou CPF para resetar a senha.")
            return
        resetar_senha_cliente_por_cnpj(doc)

    tk.Button(row_reset, text="Gerar e Enviar Nova Senha", bg="#007bff", fg="white", font=("Arial", 9, "bold"), command=botao_reset_click).pack(side="left")

    # Frame Logo do Banco (Boleto)
    frame_logo = tk.LabelFrame(root, text=" Configuração da Logo do Banco (Boleto PDF) ", padx=10, pady=10)
    frame_logo.pack(fill="x", padx=15, pady=8)

    tk.Label(frame_logo, text="Arquivo de Logo (Ex: 756.bmp):").pack(anchor="w")
    row_logo = tk.Frame(frame_logo)
    row_logo.pack(fill="x", pady=5)

    entry_logo_path = tk.Entry(row_logo, width=35, font=("Arial", 9))
    entry_logo_path.pack(side="left", padx=(0, 10))
    entry_logo_path.insert(0, config.get("logo_banco", ""))

    def procurar_logo():
        caminho = filedialog.askopenfilename(
            title="Selecionar Logo do Banco",
            filetypes=[("Arquivos de Imagem", "*.bmp;*.png;*.jpg;*.jpeg"), ("Todos os arquivos", "*.*")]
        )
        if caminho:
            entry_logo_path.delete(0, tk.END)
            entry_logo_path.insert(0, caminho)

    tk.Button(row_logo, text="Procurar...", font=("Arial", 9), command=procurar_logo).pack(side="left")

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
            entry_ign.get()
        )

    tk.Button(root, text="Salvar Configurações", bg="#28a745", fg="white", font=("Arial", 10, "bold"), command=botao_salvar_click).pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    abrir_tela_config()