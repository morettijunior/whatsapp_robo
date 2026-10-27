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

logging.info(f"Iniciando bot. EVOLUTION_URL={EVOLUTION_URL}, INSTANCE={INSTANCE_NAME}")

user_states = {}

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        payload = await request.json()
        logging.info("Webhook recebido com sucesso.")
        
        if payload.get("event") == "messages.upsert":
            data = payload.get("data", {})
            
            if data.get("key", {}).get("fromMe"):
                return {"status": "ignored"}
                
            remote_jid = data.get("key", {}).get("remoteJid")
            message_body = (data.get("message", {}).get("conversation") or 
                            data.get("message", {}).get("extendedTextMessage", {}).get("text", "")).strip()
            
            if not message_body:
                return {"status": "no_text"}

            logging.info(f"Mensagem recebida de {remote_jid}: {message_body}")
            current_state = user_states.get(remote_jid, "menu_principal")

            # --- ETAPA 1: MENU PRINCIPAL DE TRIAGEM ---
            if current_state == "menu_principal":
                if message_body == "1":
                    user_states[remote_jid] = "financeiro"
                    enviar_mensagem(
                        remote_jid, 
                        "Você selecionou o *Financeiro*.\n\n"
                        "Um atendente humano já foi notificado e logo irá atendê-lo por aqui!\n\n"
                        "💡 *Dica:* Se precisar retornar ao menu principal a qualquer momento, digite *0* ou *menu*."
                    )
                elif message_body == "2":
                    user_states[remote_jid] = "vendas"
                    link_vendas = "https://wa.me/556634210400?text=Ol%C3%A1%2C%20vim%20pelo%20menu%20automatizado%20e%20quero%20falar%20com%20Vendas."
                    enviar_mensagem(
                        remote_jid, 
                        "Você selecionou **Vendas**.\n\n"
                        f"Para falar diretamente com a nossa equipe de vendas, clique no link abaixo:\n{link_vendas}\n\n"
                        "💡 Para voltar ao menu principal, envie *0* ou *menu* aqui."
                    )
                elif message_body == "3":
                    user_states[remote_jid] = "oficina"
                    link_oficina = "https://wa.me/5566999847335?text=Ol%C3%A1%2C%20vim%20pelo%20menu%20automatizado%20e%20preciso%20de%20atendimento%20na%20Oficina."
                    enviar_mensagem(
                        remote_jid, 
                        "Você selecionou a **Oficina**.\n\n"
                        f"Para falar diretamente com a nossa oficina, clique no link abaixo:\n{link_oficina}\n\n"
                        "💡 Para voltar ao menu principal, envie *0* ou *menu* aqui."
                    )
                else:
                    menu = (
                        "Olá! Seja bem-vindo ao atendimento da *Rondochassis*.\n\n"
                        "Por favor, escolha o setor desejado:\n\n"
                        "1️⃣ - Financeiro\n"
                        "2️⃣ - Vendas\n"
                        "3️⃣ - Oficina\n\n"
                        "Responda apenas com o número da opção desejada."
                    )
                    enviar_mensagem(remote_jid, menu)

            # --- ETAPA 2: CLIENTE JÁ DIRECIONADO PARA UM SETOR ---
            else:
                if message_body.lower() == "menu" or message_body == "0":
                    user_states[remote_jid] = "menu_principal"
                    menu_retorno = (
                        "Retornando ao menu principal da *Rondochassis*.\n\n"
                        "Por favor, escolha o setor desejado:\n\n"
                        "1️⃣ - Financeiro\n"
                        "2️⃣ - Vendas\n"
                        "3️⃣ - Oficina"
                    )
                    enviar_mensagem(remote_jid, menu_retorno)
                else:
                    logging.info(f"[{current_state.upper()}] Mensagem de {remote_jid}: {message_body}")
                    
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Erro crítico no webhook: {e}")
        return {"status": "error", "detail": str(e)}

def enviar_mensagem(number: str, text: str):
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)