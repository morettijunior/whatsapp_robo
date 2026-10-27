from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

EVOLUTION_URL = os.getenv("EVOLUTION_URL")
INSTANCE_NAME = os.getenv("INSTANCE_NAME")
API_KEY = os.getenv("API_KEY")

# Dicionário em memória para guardar o setor atual de cada cliente
user_states = {}

@app.post("/webhook")
async def webhook_handler(request: Request):
    payload = await request.json()
    
    # Valida se é um evento de nova mensagem
    if payload.get("event") == "messages.upsert":
        data = payload.get("data", {})
        
        # Ignora mensagens enviadas pelo próprio bot/instância
        if data.get("key", {}).get("fromMe"):
            return {"status": "ignored"}
            
        remote_jid = data.get("key", {}).get("remoteJid")
        message_body = (data.get("message", {}).get("conversation") or 
                        data.get("message", {}).get("extendedTextMessage", {}).get("text", "")).strip()
        
        if not message_body:
            return {"status": "no_text"}

        current_state = user_states.get(remote_jid, "menu_principal")

        # --- ETAPA 1: MENU PRINCIPAL DE TRIAGEM ---
        if current_state == "menu_principal":
            if message_body == "1":
                user_states[remote_jid] = "financeiro"
                enviar_mensagem(
                    remote_jid, 
                    "Você selecionou o **Financeiro**.\n\n"
                    "Um atendente humano já foi notificado e logo irá atendê-lo por aqui!"
                )
                
            elif message_body == "2":
                user_states[remote_jid] = "vendas"
                # Link formatado com o número de vendas (DDI 55 + DDD 66 + número)
                link_vendas = "https://wa.me/556634210400?text=Ol%C3%A1%2C%20vim%20pelo%20menu%20automatizado%20e%20quero%20falar%20com%20Vendas."
                enviar_mensagem(
                    remote_jid, 
                    "Você selecionou **Vendas**.\n\n"
                    f"Para falar diretamente com a nossa equipe de vendas, clique no link abaixo:\n{link_vendas}"
                )
                
            elif message_body == "3":
                user_states[remote_jid] = "oficina"
                # Link formatado com o número da oficina (DDI 55 + DDD 66 + número)
                link_oficina = "https://wa.me/5566999847335?text=Ol%C3%A1%2C%20vim%20pelo%20menu%20automatizado%20e%20preciso%20de%20atendimento%20na%20Oficina."
                enviar_mensagem(
                    remote_jid, 
                    "Você selecionou a **Oficina**.\n\n"
                    f"Para falar diretamente com a nossa oficina, clique no link abaixo:\n{link_oficina}"
                )
                
            else:
                # Menu de Apresentação
                menu = (
                    "Olá! Seja bem-vindo ao nosso atendimento.\n\n"
                    "Por favor, escolha o setor desejado:\n\n"
                    "1️⃣ - Financeiro\n"
                    "2️⃣ - Vendas\n"
                    "3️⃣ - Oficina\n\n"
                    "Responda apenas com o número da opção desejada."
                )
                enviar_mensagem(remote_jid, menu)

        # --- ETAPA 2: CLIENTE JÁ DIRECIONADO PARA UM SETOR ---
        else:
            # Permite o cliente voltar ao menu principal digitando "menu" ou "0"
            if message_body.lower() == "menu" or message_body == "0":
                user_states[remote_jid] = "menu_principal"
                enviar_mensagem(remote_jid, "Retornando ao menu principal.\n\nDigite 1, 2 ou 3 para escolher o setor desejado.")
            else:
                print(f"[{current_state.upper()}] Mensagem de {remote_jid}: {message_body}")
                
    return {"status": "success"}

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
        return response.json()
    except Exception as e:
        print(f"Erro ao enviar mensagem para a Evolution API: {e}")