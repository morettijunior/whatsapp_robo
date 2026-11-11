import os
import sys
import logging
import json
import pathlib
import uvicorn
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
import requests
from dotenv import load_dotenv

# --- CORREÇÃO PARA AMBIENTE SEM CONSOLE (--noconsole) ---
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- CARREGAR VARIÁVEIS DE AMBIENTE (.env) ---
caminho_env = pathlib.Path(__file__).parent / ".env"
load_dotenv(dotenv_path=caminho_env)

EVOLUTION_URL = os.getenv("EVOLUTION_URL", "http://localhost:8080")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "rondochassis")
API_KEY = os.getenv("API_KEY", "")
PORT = int(os.getenv("PORT", 5000))

app = FastAPI()

# Armazenamento temporário de estados e sessões dos clientes em memória
# (Em produção avançada pode ser Redis/Firebird, mantido em dicionário simples para o bot)
user_states = {}

class WebhookPayload(BaseModel):
    event: str = None
    instance: str = None
    data: dict = {}

def limpar_numero(numero_remoto: str) -> str:
    """Remove sufixos de JID do WhatsApp e formata o número limpo."""
    return numero_remoto.split("@")[0].split(":")[0]

def enviar_mensagem_whatsapp(numero: str, texto: str):
    """Envia mensagem de texto via Evolution API."""
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": numero,
        "text": texto
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        logging.info(f"Resposta Evolution API para {numero}: {response.status_code}")
        return response.json()
    except Exception as e:
        logging.error(f"ERRO ao enviar mensagem para a Evolution API: {e}")
        return None

@app.post("/webhook")
async def webhook(payload: Request):
    try:
        body = await payload.json()
        logging.info(f"Payload recebido: {body}")
        
        # Filtra apenas o evento de mensagens recebidas
        event = body.get("event", "")
        if event != "messages.upsert":
            return {"status": "ignored_event"}

        data = body.get("data", {})
        key = data.get("key", {})
        
        # Ignora mensagens enviadas pelo próprio bot
        if key.get("fromMe", False):
            return {"status": "ignored_from_me"}

        remote_jid = key.get("remoteJid", "")
        numero = limpar_numero(remote_jid)
        
        # Extração de texto da mensagem (suporta diferentes estruturas da Evolution)
        message_obj = data.get("message", {})
        texto_mensagem = (
            message_obj.get("conversation") or
            message_obj.get("extendedTextMessage", {}).get("text") or
            ""
        ).strip()

        if not texto_mensagem:
            return {"status": "no_text"}

        logging.info(f"Número: {numero} | Mensagem: {texto_mensagem}")

        # Recupera ou inicializa o estado do usuário
        estado_atual = user_states.get(numero, {"etapa": "MENU_PRINCIPAL"})
        etapa = estado_atual.get("etapa", "MENU_PRINCIPAL")

        # ==========================================
        # FLUXO 1: MENU PRINCIPAL REESTRUTURADO
        # ==========================================
        if etapa == "MENU_PRINCIPAL":
            # Se o usuário digitar '0' ou palavra de reinício a qualquer momento
            if texto_mensagem in ["0", "menu", "voltar", "inicio"]:
                menu_texto = (
                    "Olá! Seja bem-vindo à *Rondochassis*. Como podemos ajudar você hoje?\n\n"
                    "1️⃣ - Financeiro - Falar com Atendente\n"
                    "2️⃣ - Financeiro - Acesso ao Sistema de Notas e Boletos\n"
                    "3️⃣ - Vendas - Falar com Atendente\n"
                    "4️⃣ - Oficina - Falar com Atendente\n\n"
                    "Por favor, digite o número da opção desejada:"
                )
                user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
                enviar_mensagem_whatsapp(numero, menu_texto)
                return {"status": "success"}

            if texto_mensagem == "1":
                # Direciona para atendente financeiro
                user_states[numero] = {"etapa": "ATENDENTE_FINANCEIRO"}
                enviar_mensagem_whatsapp(
                    numero, 
                    "🔄 Você escolheu falar com o *Setor Financeiro*. Um de nossos atendentes irá assumir este chat em instantes. Por favor, aguarde."
                )
                # Aqui você pode acionar notificação interna se necessário
                return {"status": "success"}

            elif texto_mensagem == "2":
                # Entra no subnicho de Gestão Financeira (Notas e Boletos)
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU"}
                submenu_texto = (
                    "📊 *Gestão Financeira - Notas e Boletos*\n\n"
                    "Identifique-se para continuar:\n"
                    "1️⃣ - Fazer Login (Consultar Notas e Boletos)\n"
                    "2️⃣ - Solicitar Senha\n"
                    "3️⃣ - Alterar Senha\n"
                    "0️⃣ - Voltar ao menu principal\n\n"
                    "Digite a opção desejada:"
                )
                enviar_mensagem_whatsapp(numero, submenu_texto)
                return {"status": "success"}

            elif texto_mensagem == "3":
                # Direciona para vendas
                user_states[numero] = {"etapa": "ATENDENTE_VENDAS"}
                enviar_mensagem_whatsapp(
                    numero, 
                    "🔄 Você escolheu o *Setor de Vendas*. Um consultor irá atendê-lo em instantes. Aguarde um momento."
                )
                return {"status": "success"}

            elif texto_mensagem == "4":
                # Direciona para oficina
                user_states[numero] = {"etapa": "ATENDENTE_OFICINA"}
                enviar_mensagem_whatsapp(
                    numero, 
                    "🔄 Você escolheu o *Setor de Oficina*. Nossa equipe técnica já foi avisada e logo responderá."
                )
                return {"status": "success"}

            else:
                enviar_mensagem_whatsapp(
                    numero, 
                    "❌ Opção inválida. Por favor, digite um número de *1 a 4* correspondente à opção desejada."
                )
                return {"status": "success"}

        # ==========================================
        # FLUXO 2: SUBMENU DE GESTÃO FINANCEIRA (Opção 2)
        # ==========================================
        elif etapa == "GESTAO_FINANCEIRA_MENU":
            if texto_mensagem == "1":
                user_states[numero] = {"etapa": "AGUARDANDO_LOGIN_CNPJ"}
                enviar_mensagem_whatsapp(numero, "🔐 Por favor, digite o seu *CNPJ ou CPF* cadastrado:")
                return {"status": "success"}

            elif texto_mensagem == "2":
                user_states[numero] = {"etapa": "AGUARDANDO_SOLICITAR_SENHA"}
                enviar_mensagem_whatsapp(numero, "✉️ Digite o seu *CNPJ ou CPF* para que possamos enviar a senha provisória para o seu e-mail cadastrado:")
                return {"status": "success"}

            elif texto_mensagem == "3":
                user_states[numero] = {"etapa": "AGUARDANDO_ALTERAR_CNPJ"}
                enviar_mensagem_whatsapp(numero, "🔄 Para alterar sua senha, digite o seu *CNPJ ou CPF*:")
                return {"status": "success"}

            elif texto_mensagem == "0":
                # Volta ao menu principal
                user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
                menu_texto = (
                    "Como podemos ajudar você hoje?\n\n"
                    "1️⃣ - Financeiro - Falar com Atendente\n"
                    "2️⃣ - Financeiro - Acesso ao Sistema de Notas e Boletos\n"
                    "3️⃣ - Vendas - Falar com Atendente\n"
                    "4️⃣ - Oficina - Falar com Atendente\n\n"
                    "Digite o número da opção desejada:"
                )
                enviar_mensagem_whatsapp(numero, menu_texto)
                return {"status": "success"}

            else:
                enviar_mensagem_whatsapp(numero, "❌ Opção inválida. Escolha de 1 a 3 ou digite 0 para voltar.")
                return {"status": "success"}

        # ==========================================
        # FLUXO DE LOGIN (EXEMPLO DE INTEGRAÇÃO JÁ EXISTENTE)
        # ==========================================
        elif etapa == "AGUARDANDO_LOGIN_CNPJ":
            # Aqui entra a captura do CNPJ e transição para senha (mantendo seu código Firebird/ERP)
            cnpj_informado = texto_mensagem
            user_states[numero] = {"etapa": "AGUARDANDO_LOGIN_SENHA", "cnpj": cnpj_informado}
            enviar_mensagem_whatsapp(numero, "🔑 Agora, digite a sua *senha* de acesso:")
            return {"status": "success"}

        elif etapa == "AGUARDANDO_LOGIN_SENHA":
            senha_informada = texto_mensagem
            cnpj_usuario = estado_atual.get("cnpj")
            
            # --- [AQUI ENTRA SUA VALIDAÇÃO NO FIREBIRD / ERP] ---
            # Exemplo simulado de sucesso no login:
            login_sucesso = True 
            
            if login_sucesso:
                user_states[numero] = {"etapa": "LOGADO_MENU_CLIENTE"}
                enviar_mensagem_whatsapp(
                    numero, 
                    "✅ Login realizado com sucesso!\n\n"
                    "Aqui estão suas últimas notas e boletos dos últimos 90 dias...\n"
                    "(Digite '0' a qualquer momento para voltar ao menu inicial)."
                )
            else:
                user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
                enviar_mensagem_whatsapp(numero, "❌ CNPJ ou senha incorretos. Retornando ao menu principal.")
            
            return {"status": "success"}

        # Caso caia em algum estado não mapeado
        else:
            user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
            enviar_mensagem_whatsapp(numero, "🔄 O chat foi reiniciado por segurança. Digite qualquer mensagem para ver o menu principal.")
            return {"status": "success"}

    except Exception as e:
        logging.error(f"Erro crítico no webhook: {e}")
        return Response(content=f'{{"detail": "{str(e)}"}}', status_code=500, media_type="application/json")

@app.get("/")
def raiz():
    return {"status": "online", "message": "Chatbot Rondochassis rodando com sucesso!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)