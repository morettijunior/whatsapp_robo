from fastapi import FastAPI, Request
import requests
import os
import logging
import uvicorn
import random
import string
import base64
from dotenv import load_dotenv

# Importa os serviços necessários
from service_bd import (
    buscar_cliente_por_documento, 
    salvar_ou_atualizar_senha_robo, 
    verificar_senha_robo,
    consultar_relatorio_pedidos_90_dias,
    _obter_conexao_bd,
    _consultar_pedidos_comuns,
    _consultar_pedidos_agrupados
)
from service_email import enviar_email_senha_provisoria
from service_pdf import gerar_pdf_relatorio_90_dias

# Configuração do Arquivo de Log na mesma pasta do executável
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

load_dotenv()

app = FastAPI()

EVOLUTION_URL = os.getenv("EVOLUTION_URL")
INSTANCE_NAME = os.getenv("INSTANCE_NAME")
API_KEY = os.getenv("API_KEY")
PORT = int(os.getenv("PORT", 5000))

logging.info(f"Iniciando bot (Módulo Financeiro). EVOLUTION_URL={EVOLUTION_URL}, INSTANCE={INSTANCE_NAME}")

# Dicionário para guardar o estado atual, histórico anterior e dados temporários de cada cliente
user_sessions = {}

NUMEROS_IGNORADOS = {
    "5566999847335",
    "556634210400",
    "5566999840793",
    "5566999101124",
}

def enviar_mensagem(number: str, text: str):
    """Função robusta para envio de mensagens via Evolution API"""
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "Content-Type": "application/json",
        "apikey": API_KEY
    }
    payload = {
        "number": number,
        "text": text,
        "linkPreview": False
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        logging.info(f"Resposta da Evolution (Enviar): Status {response.status_code} - {response.text}")
        return response.json()
    except Exception as e:
        logging.error(f"Erro ao enviar mensagem para a Evolution API: {e}")

def enviar_documento_evolution(number: str, caminho_pdf: str, nome_arquivo: str):
    """Envia o arquivo PDF gerado através da Evolution API"""
    url = f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE_NAME}"
    headers = {
        "Content-Type": "application/json",
        "apikey": API_KEY
    }
    
    try:
        with open(caminho_pdf, "rb") as f:
            pdf_bytes = f.read()
            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
            
        payload = {
            "number": number,
            "mediatype": "document",
            "mimetype": "application/pdf",
            "fileName": nome_arquivo,
            "media": pdf_base64,
            "caption": "📊 Segue o seu Relatório Financeiro dos últimos 90 dias."
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        logging.info(f"Resposta da Evolution (Enviar PDF): Status {response.status_code} - {response.text}")
        return response.json()
    except Exception as e:
        logging.error(f"Erro ao enviar PDF via Evolution API: {e}")

def mascarar_email(email):
    if "@" not in email:
        return "***@***.com"
    partes = email.split("@")
    usuario = partes[0]
    dominio = partes[1]
    if len(usuario) > 3:
        usuario_mascarado = usuario[:3] + "****"
    else:
        usuario_mascarado = usuario + "****"
    return f"{usuario_mascarado}@{dominio}"

def gerar_senha_aleatoria(tamanho=6):
    caracteres = string.ascii_uppercase + string.digits
    return "".join(random.choice(caracteres) for _ in range(tamanho))

def mudar_estado(session, novo_estado):
    """Atualiza o estado guardando o anterior para o mecanismo de voltar (0)"""
    estado_atual = session.get("state")
    if estado_atual and estado_atual != novo_estado:
        session["prev_state"] = estado_atual
    session["state"] = novo_estado

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        payload = await request.json()
        
        if payload.get("event") == "messages.upsert":
            data = payload.get("data", {})
            
            if data.get("key", {}).get("fromMe"):
                return {"status": "ignored"}
                
            remote_jid = data.get("key", {}).get("remoteJid")
            numero_limpo = remote_jid.split("@")[0] if remote_jid else ""
            
            NUMERO_AUTORIZADO_TESTE = "556634211496"
            if numero_limpo != NUMERO_AUTORIZADO_TESTE:
                return {"status": "ignored_test_mode"}

            if numero_limpo in NUMEROS_IGNORADOS:
                return {"status": "ignored_internal"}

            message_body = (data.get("message", {}).get("conversation") or 
                            data.get("message", {}).get("extendedTextMessage", {}).get("text", "")).strip()
            
            if not message_body:
                return {"status": "no_text"}

            logging.info(f"Mensagem recebida de {remote_jid}: {message_body}")
            
            if remote_jid not in user_sessions:
                user_sessions[remote_jid] = {"state": "menu_principal", "prev_state": "menu_principal", "dados": {}}

            session = user_sessions[remote_jid]
            current_state = session["state"]

            # Atalho global para reiniciar do zero absoluto
            if message_body.lower() in ["menu", "inicio", "início"]:
                user_sessions[remote_jid] = {"state": "menu_principal", "prev_state": "menu_principal", "dados": {}}
                enviar_mensagem(
                    remote_jid, 
                    "Olá! Seja bem-vindo ao atendimento da *Rondochassis*.\n\n"
                    "Por favor, escolha o setor desejado:\n\n"
                    "1️⃣ - Financeiro\n"
                    "2️⃣ - Vendas\n"
                    "3️⃣ - Oficina\n\n"
                    "*(Envie 0 a qualquer momento para voltar ao menu anterior)*"
                )
                return {"status": "success"}

            # ==========================================
            # TRATAMENTO GLOBAL DO "0" (VOLTAR AO ANTERIOR)
            # ==========================================
            if message_body == "0":
                if current_state == "menu_principal":
                    enviar_mensagem(remote_jid, "Você já está no menu principal.")
                    return {"status": "success"}
                
                # Mapeamento de retorno estruturado por hierarquia
                if current_state == "menu_financeiro_principal":
                    mudar_estado(session, "menu_principal")
                    enviar_mensagem(
                        remote_jid,
                        "Olá! Seja bem-vindo ao atendimento da *Rondochassis*.\n\n"
                        "Por favor, escolha o setor desejado:\n\n"
                        "1️⃣ - Financeiro\n"
                        "2️⃣ - Vendas\n"
                        "3️⃣ - Oficina\n\n"
                        "*(Envie 0 para voltar)*"
                    )
                elif current_state == "submenu_financeiro" or current_state == "contas_a_pagar_atendente":
                    mudar_estado(session, "menu_financeiro_principal")
                    enviar_mensagem(
                        remote_jid,
                        "Você selecionou o *Financeiro* da *Rondochassis*.\n\n"
                        "Escolha uma opção:\n\n"
                        "1️⃣ - Contas a Receber\n"
                        "2️⃣ - Contas a Pagar\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                elif current_state in ["menu_acesso", "atendente_financeiro"]:
                    mudar_estado(session, "submenu_financeiro")
                    enviar_mensagem(
                        remote_jid,
                        "📂 *Contas a Receber*\n\n"
                        "Escolha a opção desejada:\n\n"
                        "1️⃣ - Gestão Financeira (Notas, Boletos e Relatórios)\n"
                        "2️⃣ - Falar com Atendente Humano\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                elif current_state in ["login_aguardando_cnpj", "solicitar_senha_aguardando_cnpj", "alterar_senha_aguardando_cnpj"]:
                    mudar_estado(session, "menu_acesso")
                    enviar_mensagem(
                        remote_jid,
                        "🔐 *Gestão Financeira*\n\nIdentifique-se:\n\n"
                        "1️⃣ - Fazer Login\n"
                        "2️⃣ - Solicitar Senha\n"
                        "3️⃣ - Alterar Senha\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                elif current_state == "menu_gestao_logado":
                    mudar_estado(session, "menu_acesso")
                    enviar_mensagem(
                        remote_jid,
                        "🔐 *Gestão Financeira*\n\nIdentifique-se:\n\n"
                        "1️⃣ - Fazer Login\n"
                        "2️⃣ - Solicitar Senha\n"
                        "3️⃣ - Alterar Senha\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                elif current_state == "aguardando_selecao_pedido":
                    mudar_estado(session, "menu_gestao_logado")
                    enviar_mensagem(
                        remote_jid,
                        "🎉 *Menu Gestão Financeira:*\n\n"
                        "1️⃣ - Relatório de Pedidos em Aberto (90 dias)\n"
                        "2️⃣ - Solicitar Notas e Boletos\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                else:
                    mudar_estado(session, "menu_principal")
                    enviar_mensagem(remote_jid, "Retornando ao menu principal.")
                return {"status": "success"}

            # ==========================================
            # ETAPA 1: MENU PRINCIPAL
            # ==========================================
            if current_state == "menu_principal":
                if message_body == "1":
                    mudar_estado(session, "menu_financeiro_principal")
                    enviar_mensagem(
                        remote_jid,
                        "Você selecionou o *Financeiro* da *Rondochassis*.\n\n"
                        "Escolha uma opção:\n\n"
                        "1️⃣ - Contas a Receber\n"
                        "2️⃣ - Contas a Pagar\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                elif message_body == "2":
                    mudar_estado(session, "vendas")
                    link_vendas = "https://wa.me/556634210400?text=Ol%C3%A1%2C%20vim%20pelo%20menu%20automatizado%20e%20quero%20falar%20com%20Vendas."
                    enviar_mensagem(remote_jid, f"Você selecionou **Vendas**.\n\nPara falar com Vendas, clique no link:\n{link_vendas}")
                elif message_body == "3":
                    mudar_estado(session, "oficina")
                    link_oficina = "https://wa.me/5566999847335?text=Ol%C3%A1%2C%20vim%20pelo%20menu%20automatizado%20e%20preciso%20de%20atendimento%20na%20Oficina."
                    enviar_mensagem(remote_jid, f"Você selecionou a **Oficina**.\n\nPara falar com a Oficina, clique no link:\n{link_oficina}")
                else:
                    enviar_mensagem(
                        remote_jid,
                        "Opção inválida. Escolha o setor desejado:\n\n1️⃣ - Financeiro\n2️⃣ - Vendas\n3️⃣ - Oficina"
                    )

            # ==========================================
            # ETAPA 2: MENU FINANCEIRO PRINCIPAL
            # ==========================================
            elif current_state == "menu_financeiro_principal":
                if message_body == "1":
                    mudar_estado(session, "submenu_financeiro")
                    enviar_mensagem(
                        remote_jid,
                        "📂 *Contas a Receber*\n\n"
                        "Escolha a opção desejada:\n\n"
                        "1️⃣ - Gestão Financeira (Notas, Boletos e Relatórios)\n"
                        "2️⃣ - Falar com Atendente Humano\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                elif message_body == "2":
                    mudar_estado(session, "contas_a_pagar_atendente")
                    enviar_mensagem(remote_jid, "💳 Você selecionou *Contas a Pagar*. Um atendente foi notificado.")
                else:
                    enviar_mensagem(remote_jid, "Opção inválida. Digite 1 ou 2.")

            # ==========================================
            # ETAPA 3: SUBMENU FINANCEIRO
            # ==========================================
            elif current_state == "submenu_financeiro":
                if message_body == "1":
                    mudar_estado(session, "menu_acesso")
                    enviar_mensagem(
                        remote_jid,
                        "🔐 *Gestão Financeira*\n\nIdentifique-se:\n\n"
                        "1️⃣ - Fazer Login\n"
                        "2️⃣ - Solicitar Senha\n"
                        "3️⃣ - Alterar Senha\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                elif message_body == "2":
                    enviar_mensagem(remote_jid, "👤 Um atendente do financeiro foi notificado para lhe auxiliar.")
                else:
                    enviar_mensagem(remote_jid, "Opção inválida. Digite 1 ou 2.")

            # ==========================================
            # ETAPA 4: MENU DE ACESSO
            # ==========================================
            elif current_state == "menu_acesso":
                if message_body == "1":
                    mudar_estado(session, "login_aguardando_cnpj")
                    enviar_mensagem(remote_jid, "Por favor, digite o seu **CNPJ ou CPF**:\n\n0️⃣ - Voltar ao menu anterior")
                elif message_body == "2":
                    mudar_estado(session, "solicitar_senha_aguardando_cnpj")
                    enviar_mensagem(remote_jid, "Para solicitar sua senha provisória, digite o seu **CNPJ ou CPF**:\n\n0️⃣ - Voltar ao menu anterior")
                elif message_body == "3":
                    mudar_estado(session, "alterar_senha_aguardando_cnpj")
                    enviar_mensagem(remote_jid, "Para alterar sua senha, digite o seu **CNPJ ou CPF**:\n\n0️⃣ - Voltar ao menu anterior")
                else:
                    enviar_mensagem(remote_jid, "Opção inválida. Escolha entre 1, 2 ou 3.")

            # ==========================================
            # FLUXO DE SOLICITAR SENHA
            # ==========================================
            elif current_state == "solicitar_senha_aguardando_cnpj":
                resultado = buscar_cliente_por_documento(message_body)
                if resultado["status"] == "erro_formato":
                    enviar_mensagem(remote_jid, "❌ Formato inválido! Digite corretamente o CPF ou CNPJ:")
                elif resultado["status"] == "nao_encontrado":
                    enviar_mensagem(remote_jid, "❌ CNPJ/CPF não encontrado na base de dados.")
                    mudar_estado(session, "menu_acesso")
                elif resultado["status"] == "encontrado":
                    email_completo = resultado["email"]
                    if not email_completo:
                        mudar_estado(session, "aguardando_opcao_email_vazio")
                        enviar_mensagem(remote_jid, "⚠️ Não encontramos e-mail cadastrado. Deseja falar com o financeiro? (1 - Sim / 0 - Voltar)")
                        return {"status": "success"}
                        
                    session["dados"]["codcfo"] = resultado["codcfo"]
                    session["dados"]["nome"] = resultado["nome"]
                    session["dados"]["email"] = email_completo
                    mudar_estado(session, "solicitar_senha_confirmar_email")
                    enviar_mensagem(remote_jid, f"O e-mail cadastrado é: {mascarar_email(email_completo)}\nConfirma?\n1 - Sim\n0 - Voltar")

            elif current_state == "aguardando_opcao_email_vazio":
                if message_body == "1":
                    mudar_estado(session, "submenu_financeiro")
                    enviar_mensagem(remote_jid, "Entre em contato com o financeiro para cadastrar seu e-mail.")
                else:
                    mudar_estado(session, "menu_acesso")
                    enviar_mensagem(remote_jid, "Retornando ao menu anterior.")

            elif current_state == "solicitar_senha_confirmar_email":
                if message_body == "1":
                    codcfo = session["dados"].get("codcfo")
                    nome = session["dados"].get("nome")
                    email = session["dados"].get("email")
                    
                    nova_senha = gerar_senha_aleatoria()
                    salvar_ou_atualizar_senha_robo(codcfo, nome, email, nova_senha)
                    enviado = enviar_email_senha_provisoria(email, nome, nova_senha)
                    
                    if enviado:
                        mudar_estado(session, "submenu_financeiro")
                        enviar_mensagem(remote_jid, f"✅ Senha provisória enviada para o e-mail {mascarar_email(email)}.")
                    else:
                        enviar_mensagem(remote_jid, "❌ Falha ao enviar o e-mail. Tente novamente mais tarde.")
                        mudar_estado(session, "menu_acesso")
                else:
                    mudar_estado(session, "menu_acesso")
                    enviar_mensagem(remote_jid, "Operação cancelada.")

            # ==========================================
            # FLUXO DE LOGIN
            # ==========================================
            elif current_state == "login_aguardando_cnpj":
                resultado = buscar_cliente_por_documento(message_body)
                if resultado["status"] == "encontrado":
                    session["dados"]["codcfo"] = resultado["codcfo"]
                    session["dados"]["nome"] = resultado["nome"]
                    session["dados"]["documento"] = message_body
                    mudar_estado(session, "login_aguardando_senha")
                    enviar_mensagem(remote_jid, "Por favor, digite a sua **Senha**:\n\n0️⃣ - Voltar ao menu anterior")
                else:
                    enviar_mensagem(remote_jid, "❌ CNPJ/CPF não encontrado.")
                    mudar_estado(session, "menu_acesso")

            elif current_state == "login_aguardando_senha":
                codcfo = session["dados"].get("codcfo")
                if verificar_senha_robo(codcfo, message_body):
                    mudar_estado(session, "menu_gestao_logado")
                    enviar_mensagem(
                        remote_jid,
                        "🎉 *Login realizado com sucesso!*\n\n"
                        "Menu Gestão Financeira:\n\n"
                        "1️⃣ - Relatório de Pedidos em Aberto (90 dias)\n"
                        "2️⃣ - Solicitar Notas e Boletos\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                else:
                    mudar_estado(session, "menu_acesso")
                    enviar_mensagem(remote_jid, "❌ Senha incorreta. Retornando ao menu de acesso.")

            # ==========================================
            # FLUXO DE ALTERAR SENHA
            # ==========================================
            elif current_state == "alterar_senha_aguardando_cnpj":
                resultado = buscar_cliente_por_documento(message_body)
                if resultado["status"] == "encontrado":
                    session["dados"]["codcfo"] = resultado["codcfo"]
                    mudar_estado(session, "alterar_senha_aguardando_senha_atual")
                    enviar_mensagem(remote_jid, "Digite a sua **Senha Atual**:\n\n0️⃣ - Voltar ao menu anterior")
                else:
                    enviar_mensagem(remote_jid, "❌ CNPJ/CPF não encontrado.")
                    mudar_estado(session, "menu_acesso")

            elif current_state == "alterar_senha_aguardando_senha_atual":
                codcfo = session["dados"].get("codcfo")
                if verificar_senha_robo(codcfo, message_body):
                    mudar_estado(session, "alterar_senha_aguardando_senha_nova")
                    enviar_mensagem(remote_jid, "Digite a **Nova Senha** (exatamente 6 números):\n\n0️⃣ - Voltar ao menu anterior")
                else:
                    mudar_estado(session, "menu_acesso")
                    enviar_mensagem(remote_jid, "❌ Senha atual incorreta.")

            elif current_state == "alterar_senha_aguardando_senha_nova":
                nova_senha = message_body.strip()
                if not nova_senha.isdigit() or len(nova_senha) != 6:
                    enviar_mensagem(remote_jid, "❌ A senha deve conter exatamente 6 números. Digite novamente:")
                    return {"status": "success"}

                codcfo = session["dados"].get("codcfo")
                conn = _obter_conexao_bd()
                cursor = conn.cursor()
                cursor.execute("SELECT NOME, EMAIL FROM ROBOWHATS WHERE CODCFO = ?", (codcfo,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    nome, email = row
                    salvar_ou_atualizar_senha_robo(codcfo, nome, email, nova_senha)
                    
                mudar_estado(session, "submenu_financeiro")
                enviar_mensagem(remote_jid, "🔒 Senha alterada com sucesso!")

            # ==========================================
            # ETAPA 5: MENU GESTÃO FINANCEIRA (LOGADO)
            # ==========================================
            elif current_state == "menu_gestao_logado":
                if message_body == "1": # Relatório de Pedidos em Aberto (90 dias)
                    enviar_mensagem(
                        remote_jid,
                        "📊 Gerando seu *Relatório de Pedidos em Aberto*...\n\n"
                        "*(O documento PDF será enviado em instantes)*"
                    )
                    
                    codcfo = session["dados"].get("codcfo")
                    nome_cliente = session["dados"].get("nome", "Cliente")
                    documento_cliente = session["dados"].get("documento", "")
                    
                    pedidos = consultar_relatorio_pedidos_90_dias(codcfo)
                    
                    if not pedidos:
                        enviar_mensagem(remote_jid, "⚠️ Nenhum lançamento financeiro encontrado nos últimos 90 dias.")
                    else:
                        caminho_pdf = gerar_pdf_relatorio_90_dias(nome_cliente, documento_cliente, pedidos)
                        enviar_documento_evolution(remote_jid, caminho_pdf, "relatorio_pedidos_90_dias.pdf")
                    
                    # Mantém o usuário logado e reapresenta o menu
                    mudar_estado(session, "menu_gestao_logado")
                    enviar_mensagem(
                        remote_jid,
                        "Menu Gestão Financeira:\n\n"
                        "1️⃣ - Relatório de Pedidos em Aberto (90 dias)\n"
                        "2️⃣ - Solicitar Notas e Boletos\n\n"
                        "0️⃣ - Voltar ao menu anterior"
                    )
                        
                elif message_body == "2": # Solicitar Notas e Boletos
                    codcfo = session["dados"].get("codcfo")
                    
                    conn = _obter_conexao_bd()
                    cursor = conn.cursor()
                    comuns = _consultar_pedidos_comuns(cursor, codcfo)
                    agrupados = _consultar_pedidos_agrupados(cursor, codcfo)
                    conn.close()
                    
                    todos_pedidos = comuns + agrupados
                    todos_pedidos = sorted(todos_pedidos, key=lambda x: x.get("DATA", ""))
                    
                    if not todos_pedidos:
                        enviar_mensagem(remote_jid, "📭 Nenhum pedido encontrado nos últimos 90 dias.")
                    else:
                        session["dados"]["lista_pedidos"] = todos_pedidos
                        mudar_estado(session, "aguardando_selecao_pedido")
                        
                        pedidos_pagos = []
                        pedidos_abertos = []
                        
                        for item in todos_pedidos:
                            parcelas = item.get("PARCELAS", [])
                            tem_aberto = any(str(p.get("STATUS", "")).upper() == "ABERTO" for p in parcelas)
                            
                            if tem_aberto:
                                pedidos_abertos.append(item)
                            else:
                                pedidos_pagos.append(item)
                        
                        def montar_bloco_celula(item, idx):
                            os_val = item.get("OS")
                            pedido = item.get("PEDIDO", "-")
                            nota = item.get("NOTA", "-")
                            data = item.get("DATA", "-")
                            valor_total = item.get("VALOR_TOTAL", 0.0)
                            parcelas = item.get("PARCELAS", [])
                            
                            if isinstance(nota, str) and " " in nota.strip():
                                nota = ", ".join(nota.split())
                            
                            if os_val and str(os_val).strip() and str(os_val).strip() != "-":
                                identificador = f"O.S. {os_val}"
                            else:
                                identificador = f"Ped. {pedido}"
                            
                            bloco = f"┌─────────────────────────\n"
                            bloco += f"│ *[{idx}]* {identificador} 📅 {data}\n"
                            bloco += f"│ 🧾 NOTA: {nota}\n"
                            
                            for p in parcelas:
                                p_num = p.get("PARCELA", 1)
                                p_venc = p.get("VENCIMENTO", "--/--/----")
                                p_val = p.get("VALOR", 0.0)
                                p_status = str(p.get("STATUS", "")).upper()
                                status_txt = "PAGO" if p_status == "BAIXADO" else "ABERTO"
                                
                                bloco += f"│ PARC {p_num} VENC {p_venc}\n"
                                bloco += f"│ R$ {p_val:,.2f} - {status_txt}\n"
                            
                            bloco += f"│ 💰 TOTAL: R$ {valor_total:,.2f}\n"
                            bloco += f"└─────────────────────────\n\n"
                            return bloco

                        texto_resposta = "📋 *CONSULTA DE PEDIDOS E NOTAS*\n\n"
                        
                        texto_resposta += "🟢 *--- PEDIDOS PAGOS ---*\n\n"
                        if pedidos_pagos:
                            for item in pedidos_pagos:
                                idx = todos_pedidos.index(item) + 1
                                texto_resposta += montar_bloco_celula(item, idx)
                        else:
                            texto_resposta += "Nenhum pedido pago no período.\n\n"
                        
                        texto_resposta += "🟠 *--- PEDIDOS EM ABERTO ---*\n\n"
                        if pedidos_abertos:
                            for item in pedidos_abertos:
                                idx = todos_pedidos.index(item) + 1
                                texto_resposta += montar_bloco_celula(item, idx)
                        else:
                            texto_resposta += "Nenhum pedido em aberto no período.\n\n"
                            
                        texto_resposta += "Digite o número do item desejado (ou 0 para voltar):"
                        enviar_mensagem(remote_jid, texto_resposta)
                else:
                    enviar_mensagem(remote_jid, "Opção inválida. Digite 1 ou 2.")

            # ==========================================
            # ETAPA 6: SELEÇÃO DE PEDIDO PARA NOTAS/BOLETOS
            # ==========================================
            elif current_state == "aguardando_selecao_pedido":
                if message_body.isdigit():
                    escolha = int(message_body)
                    lista_pedidos = session["dados"].get("lista_pedidos", [])
                    
                    if 1 <= escolha <= len(lista_pedidos):
                        pedido_selecionado = lista_pedidos[escolha - 1]
                        session["dados"]["pedido_selecionado"] = pedido_selecionado
                        
                        num_ped = pedido_selecionado.get('PEDIDO')
                        num_not = pedido_selecionado.get('NOTA')
                        
                        enviar_mensagem(
                            remote_jid,
                            f"✅ Você selecionou:\nPedido: {num_ped} | Nota: {num_not}\n\n"
                            "Gerando e enviando os documentos solicitados..."
                        )
                        
                        # Aqui daremos continuidade ao envio dos anexos solicitados
                        
                        mudar_estado(session, "menu_gestao_logado")
                        enviar_mensagem(
                            remote_jid,
                            "Menu Gestão Financeira:\n\n"
                            "1️⃣ - Relatório de Pedidos em Aberto (90 dias)\n"
                            "2️⃣ - Solicitar Notas e Boletos\n\n"
                            "0️⃣ - Voltar ao menu anterior"
                        )
                    else:
                        enviar_mensagem(remote_jid, "❌ Número inválido! Escolha um item da lista ou digite 0 para voltar.")
                else:
                    enviar_mensagem(remote_jid, "❌ Digite apenas o número correspondente ao item desejado.")
                    
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Erro crítico no webhook: {e}")
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)