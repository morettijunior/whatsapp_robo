import smtplib
import imaplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
import json
from pathlib import Path

def _obter_caminho_config_json():
    docs_path = Path.home() / "Documents" / "RondochassisBot"
    docs_path.mkdir(parents=True, exist_ok=True)
    return docs_path / "config_sistema.json"

def carregar_config():
    config_file = _obter_caminho_config_json()
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    # Padrão Hostinger caso o arquivo não exista
    return {
        "smtp_host": "smtp.hostinger.com",
        "smtp_port": 465,
        "imap_host": "imap.hostinger.com",
        "imap_port": 993,
        "smtp_user": "financeiro@rondochassis.com.br",
        "smtp_pass": "sua_senha_aqui"
    }

def enviar_email_senha_provisoria(email_destino, nome_cliente, senha_provisoria):
    """
    Envia o e-mail de senha provisória utilizando SMTP Hostinger (porta 465 SSL) 
    e salva uma cópia na pasta de Enviados via IMAP.
    """
    config = carregar_config()
    
    smtp_host = config.get("smtp_host", "smtp.hostinger.com")
    smtp_port = int(config.get("smtp_port", 465))
    imap_host = config.get("imap_host", "imap.hostinger.com")
    imap_port = int(config.get("imap_port", 993))
    
    remetente = config.get("smtp_user")
    senha = config.get("smtp_pass")
    
    if not remetente or not senha or senha == "sua_senha_aqui":
        print("Erro: Credenciais de e-mail não configuradas corretamente no config_sistema.json.")
        return False
        
    assunto = "Rondochassis - Senha Provisória do Robô WhatsApp"
    
    corpo_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333333; font-size: 14px; line-height: 1.5;">
        <p>Prezado(a) <b>{nome_cliente}</b>,</p>
        <p>Você solicitou acesso ao atendimento automatizado da <b>Rondochassis</b> (Módulo Financeiro).</p>
        
        <p style="background-color: #f3f4f6; padding: 12px; border-left: 4px solid #2563eb;">
        Sua senha provisória de acesso é: <b style="font-size: 16px; color: #1d4ed8;">{senha_provisoria}</b>
        </p>
        
        <p>Utilize esta senha para fazer o seu login no WhatsApp. Recomendamos que você altere sua senha assim que acessar o sistema.</p>
        
        <p>Caso não tenha solicitado esta senha, por gentileza desconsidere esta mensagem.<br>
        Agradecemos pela atenção!</p>
        
        <p>Atenciosamente,<br><b>RONDOCHASSIS SERVIÇOS LTDA</b></p>
    </body>
    </html>
    """
    
    # Montagem da mensagem
    msg = MIMEMultipart('alternative')
    msg['From'] = remetente
    msg['To'] = email_destino
    msg['Subject'] = assunto
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid()
    
    msg.attach(MIMEText(corpo_html, 'html', 'utf-8'))
    
    # 1. Envio via SMTP (Hostinger Porta 465 com SSL)
    try:
        contexto = smtplib.ssl.create_default_context()
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=contexto, timeout=30) as server:
                server.login(remetente, senha)
                server.sendmail(remetente, [email_destino], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.starttls(context=contexto)
                server.login(remetente, senha)
                server.sendmail(remetente, [email_destino], msg.as_string())
    except Exception as e:
        print(f"Erro ao enviar e-mail via SMTP Hostinger: {e}")
        return False

    # 2. Salvamento na pasta de Enviados via IMAP
    try:
        with imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30) as imap:
            imap.login(remetente, senha)
            # Tenta salvar em 'INBOX.Sent' ou 'Sent'
            try:
                imap.append('INBOX.Sent', '(\\Seen)', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            except Exception:
                imap.append('Sent', '(\\Seen)', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    except Exception as imap_erro:
        print(f"⚠️ Aviso: E-mail enviado com sucesso, mas houve erro ao salvar em Enviados via IMAP: {imap_erro}")

    return True