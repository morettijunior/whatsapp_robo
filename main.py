from fastapi import FastAPI, Request
import requests
import os
import logging
import uvicorn
from dotenv import load_dotenv

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

# Dicionário para guardar o estado atual e dados temporários de cada cliente
user_sessions = {}

# Lista de números que o bot deve ignorar (com DDI 55 + DDD + Número)
NUMEROS_IGNORADOS = {
    "5566999847335",
    "556634210400",
    "5566999840793",
    "5566999101124",
    # ----------------------------------------------------
    # Números de teste abaixo: desativados com # para permitirem testes agora.
    # Quando terminar os testes, basta remover o # de cada linha.
    # ----------------------------------------------------
    # "556634211496",
    # "5566999972762",
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

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        payload = await request.json()
        
        if payload.get("event") == "messages.upsert":
            data = payload.get("data", {})
            
            if data.get("key", {}).get("fromMe"):
                return {"status": "ignored"}
                
            remote_jid = data.get("key", {}).get("remoteJid")
            
            # Extrai apenas os números do JID (ex: "5566999998888@s.whatsapp.net" vira "5566999998888")
            numero_limpo = remote_jid.split("@")[0] if remote_jid else ""
            
            # Se o número estiver na lista de ignorados, o bot ignora e não responde
            if numero_limpo in NUMEROS_IGNORADOS:
                logging.info(f"Mensagem ignorada do número interno: {numero_limpo}")
                return {"status": "ignored_internal"}

            message_body = (data.get("message", {}).get("conversation") or 
                            data.get("message", {}).get("extendedTextMessage", {}).get("text", "")).strip()
            
            if not message_body:
                return {"status": "no_text"}

            logging.info(f"Mensagem recebida de {remote_jid}: {message_body}")
            
            # Inicializa a sessão do usuário se não existir
            if remote_jid not in user_sessions:
                user_sessions[remote_jid] = {"state": "menu_principal", "dados": {}}

            session = user_sessions[remote_jid]
            current_state = session["state"]

            # Atalho global para voltar ao menu principal
            if message_body.lower() in ["menu", "0", "olá", "ola", "oi", "inicio", "início"]:
                user_sessions[remote_jid] = {"state": "menu_principal", "dados": {}}
                enviar_mensagem(
                    remote_jid, 
                    "Olá! Seja bem-vindo ao atendimento da *Rondochassis*.\n\n"
                    "Por favor, escolha o setor desejado:\n\n"
                    "1️⃣ - Financeiro\n"
                    "2️⃣ - Vendas\n"
                    "3️⃣ - Oficina\n\n"
                    "*(Envie 0 ou menu a qualquer momento para voltar)*"
                )
                return {"status": "success"}

            # ==========================================
            # ETAPA 1: MENU PRINCIPAL DE TRIAGEM
            # ==========================================
            if current_state == "menu_principal":
                if message_body == "1": # Financeiro
                    session["state"] = "menu_financeiro_principal"
                    enviar_mensagem(
                        remote_jid,
                        "Você selecionou o *Financeiro* da *Rondochassis*.\n\n"
                        "Escolha uma opção:\n\n"
                        "1️⃣ - Contas a Receber\n"
                        "2️⃣ - Contas a Pagar\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif message_body == "2": # Vendas
                    session["state"] = "vendas"
                    link_vendas = "https://wa.me/556634210400?text=Ol%C3%A1%2C%20vim%20pelo%20menu%20automatizado%20e%20quero%20falar%20com%20Vendas."
                    enviar_mensagem(
                        remote_jid, 
                        "Você selecionou **Vendas**.\n\n"
                        f"Para falar diretamente com a nossa equipe de vendas, clique no link abaixo:\n{link_vendas}\n\n"
                        "💡 Para voltar ao menu principal, envie *0* ou *menu* aqui."
                    )
                elif message_body == "3": # Oficina
                    session["state"] = "oficina"
                    link_oficina = "https://wa.me/5566999847335?text=Ol%C3%A1%2C%20vim%20pelo%20menu%20automatizado%20e%20preciso%20de%20atendimento%20na%20Oficina."
                    enviar_mensagem(
                        remote_jid, 
                        "Você selecionou a **Oficina**.\n\n"
                        f"Para falar diretamente com a nossa oficina, clique no link abaixo:\n{link_oficina}\n\n"
                        "💡 Para voltar ao menu principal, envie *0* ou *menu* aqui."
                    )
                else:
                    enviar_mensagem(
                        remote_jid,
                        "Opção inválida. Por favor, escolha o setor desejado:\n\n"
                        "1️⃣ - Financeiro\n"
                        "2️⃣ - Vendas\n"
                        "3️⃣ - Oficina\n\n"
                        "Responda apenas com o número da opção desejada."
                    )

            # ==========================================
            # ETAPA 2: MENU FINANCEIRO PRINCIPAL
            # ==========================================
            elif current_state == "menu_financeiro_principal":
                if message_body == "1": # Contas a Receber -> Submenu Financeiro
                    session["state"] = "submenu_financeiro"
                    enviar_mensagem(
                        remote_jid,
                        "📂 *Contas a Receber*\n\n"
                        "Escolha a opção desejada:\n\n"
                        "1️⃣ - Gestão Financeira (Notas, Boletos e Relatórios)\n"
                        "2️⃣ - Falar com Atendente Humano"
                    )
                elif message_body == "2": # Contas a Pagar
                    session["state"] = "contas_a_pagar_atendente"
                    enviar_mensagem(
                        remote_jid,
                        "💳 Você selecionou *Contas a Pagar*.\n\n"
                        "Um atendente do setor financeiro já foi notificado e logo irá atendê-lo por aqui!"
                    )
                else:
                    enviar_mensagem(remote_jid, "Opção inválida. Digite *1* para Contas a Receber ou *2* para Contas a Pagar.")

            # ==========================================
            # ETAPA 3: SUBMENU FINANCEIRO
            # ==========================================
            elif current_state == "submenu_financeiro":
                if message_body == "1": # Gestão Financeira
                    session["state"] = "menu_acesso"
                    enviar_mensagem(
                        remote_jid,
                        "🔐 *Gestão Financeira*\n\n"
                        "Para sua segurança, identifique-se:\n\n"
                        "1️⃣ - Fazer Login\n"
                        "2️⃣ - Solicitar Senha (Primeiro Acesso)\n"
                        "3️⃣ - Alterar Senha"
                    )
                elif message_body == "2": # Falar com Atendente
                    enviar_mensagem(
                        remote_jid,
                        "👤 Um atendente do financeiro foi notificado para lhe auxiliar com Contas a Receber."
                    )
                else:
                    enviar_mensagem(remote_jid, "Opção inválida. Digite *1* para Gestão Financeira ou *2* para Falar com Atendente.")

            # ==========================================
            # ETAPA 4: MENU DE ACESSO
            # ==========================================
            elif current_state == "menu_acesso":
                if message_body == "1": # Fazer Login
                    session["state"] = "login_aguardando_cnpj"
                    enviar_mensagem(remote_jid, "Por favor, digite o seu **CNPJ** (apenas números):")
                elif message_body == "2": # Solicitar Senha
                    session["state"] = "solicitar_senha_aguardando_cnpj"
                    enviar_mensagem(remote_jid, "Para solicitar sua senha provisória, digite o seu **CNPJ** (apenas números):")
                elif message_body == "3": # Alterar Senha
                    session["state"] = "alterar_senha_aguardando_cnpj"
                    enviar_mensagem(remote_jid, "Para alterar sua senha, digite o seu **CNPJ**:")
                else:
                    enviar_mensagem(remote_jid, "Opção inválida. Escolha entre *1*, *2* ou *3*.")

            # --- FLUXO DE SOLICITAR SENHA ---
            elif current_state == "solicitar_senha_aguardando_cnpj":
                session["dados"]["cnpj"] = message_body
                session["state"] = "solicitar_senha_aguardando_email"
                enviar_mensagem(remote_jid, "Agora, digite o seu **E-mail cadastrado**:")

            elif current_state == "solicitar_senha_aguardando_email":
                cnpj = session["dados"].get("cnpj")
                email = message_body
                session["state"] = "submenu_financeiro"
                enviar_mensagem(
                    remote_jid, 
                    f"✅ Verificação concluída para o CNPJ {cnpj}.\n"
                    f"Uma senha provisória foi enviada para o e-mail: {email}.\n\n"
                    "Retornando ao submenu financeiro. Escolha 1 para Gestão Financeira e faça seu login."
                )

            # --- FLUXO DE FAZER LOGIN ---
            elif current_state == "login_aguardando_cnpj":
                session["dados"]["cnpj"] = message_body
                session["state"] = "login_aguardando_senha"
                enviar_mensagem(remote_jid, "Digite a sua **Senha**:")

            elif current_state == "login_aguardando_senha":
                cnpj = session["dados"].get("cnpj")
                senha = message_body
                login_sucesso = True # Simulado por enquanto
                
                if login_sucesso:
                    session["state"] = "menu_gestao_logado"
                    enviar_mensagem(
                        remote_jid,
                        "🎉 *Login realizado com sucesso!*\n\n"
                        "Menu Gestão Financeira:\n\n"
                        "1️⃣ - Relatório de Pedidos em Aberto\n"
                        "2️⃣ - Solicitar Notas e Boletos\n\n"
                        "*(Digite 0 ou menu para sair)*"
                    )
                else:
                    session["state"] = "menu_acesso"
                    enviar_mensagem(remote_jid, "❌ CNPJ ou Senha inválidos. Tente novamente no menu de acesso.")

            # --- FLUXO DE ALTERAR SENHA ---
            elif current_state == "alterar_senha_aguardando_cnpj":
                session["dados"]["cnpj"] = message_body
                session["state"] = "alterar_senha_aguardando_senha_atual"
                enviar_mensagem(remote_jid, "Digite a sua **Senha Atual** (ou a provisória que recebeu por e-mail):")

            elif current_state == "alterar_senha_aguardando_senha_atual":
                session["dados"]["senha_atual"] = message_body
                session["state"] = "alterar_senha_aguardando_senha_nova"
                enviar_mensagem(remote_jid, "Digite a **Nova Senha** desejada:")

            elif current_state == "alterar_senha_aguardando_senha_nova":
                cnpj = session["dados"].get("cnpj")
                senha_atual = session["dados"].get("senha_atual")
                senha_nova = message_body
                session["state"] = "submenu_financeiro"
                enviar_mensagem(
                    remote_jid,
                    "🔒 *Senha alterada com sucesso!*\n\n"
                    "Agora você já pode fazer o login com sua nova senha.\n\n"
                    "Retornando ao submenu financeiro."
                )

            # ==========================================
            # ETAPA 5: MENU GESTÃO FINANCEIRA (LOGADO)
            # ==========================================
            elif current_state == "menu_gestao_logado":
                if message_body == "1": # Relatório de Pedidos em Aberto
                    enviar_mensagem(
                        remote_jid,
                        "📊 Gerando seu *Relatório de Pedidos em Aberto*...\n\n"
                        "*(O documento PDF será enviado em instantes)*"
                    )
                elif message_body == "2": # Solicitar Notas e Boletos
                    enviar_mensagem(
                        remote_jid,
                        "📄 Buscando suas *Notas Fiscais e Boletos* disponíveis...\n\n"
                        "*(Os arquivos serão enviados por aqui)*"
                    )
                else:
                    enviar_mensagem(remote_jid, "Opção inválida no menu logado. Digite *1* ou *2*.")
                    
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Erro crítico no webhook: {e}")
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)