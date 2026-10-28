import tkinter as tk
from tkinter import messagebox
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
        "smtp_pass": "sua_senha_aqui"
    }

def salvar_config(dsn, smtp_host, smtp_port, imap_host, imap_port, user, senha):
    dados = {
        "db_dsn": dsn,
        "smtp_host": smtp_host,
        "smtp_port": int(smtp_port),
        "imap_host": imap_host,
        "imap_port": int(imap_port),
        "smtp_user": user,
        "smtp_pass": senha
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

def abrir_tela_config():
    config = carregar_config()

    root = tk.Tk()
    root.title("Painel do Financeiro - Configurações e Reset")
    root.geometry("500x520")
    root.minsize(500, 520)

    tk.Label(root, text="Painel Administrativo - Bot Rondochassis", font=("Arial", 12, "bold")).pack(pady=10)

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

    def botao_salvar_click():
        salvar_config(
            entry_dsn.get(),
            entry_smtp_host.get(),
            entry_smtp_port.get(),
            entry_imap_host.get(),
            entry_imap_port.get(),
            entry_user.get(),
            entry_pass.get()
        )

    tk.Button(frame_cfg, text="Salvar Configurações", bg="#28a745", fg="white", font=("Arial", 9, "bold"), command=botao_salvar_click).pack(pady=5)

    # Frame Reset Manual de Senha
    frame_reset = tk.LabelFrame(root, text=" Reset Manual de Senha (Caso o cliente solicite) ", padx=10, pady=10)
    frame_reset.pack(fill="x", padx=15, pady=10)

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

    root.mainloop()

if __name__ == "__main__":
    abrir_tela_config()