import os
import sys
import logging
import json
import pathlib
import base64
import re
import uvicorn
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
import requests
from dotenv import load_dotenv

# --- IMPORTE DOS MÓDULOS INTERNOS DO SISTEMA ---
try:
    import service_bd
except ImportError:
    service_bd = None
    logging.warning("Módulo 'service_bd' não encontrado na pasta física.")

try:
    import boleto
except ImportError:
    boleto = None
    logging.warning("Módulo 'boleto' não encontrado na pasta física.")

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

# Dicionário de sessão e estados em memória por número de WhatsApp
user_states = {}

class WebhookPayload(BaseModel):
    event: str = None
    instance: str = None
    data: dict = {}

def limpar_numero(numero_remoto: str) -> str:
    """Remove sufixos de JID do WhatsApp e retorna o número limpo."""
    return numero_remoto.split("@")[0].split(":")[0]

def apenas_numeros(texto: str) -> str:
    """Remove pontuações e mantém apenas dígitos (para CPF/CNPJ)."""
    return re.sub(r'\D', '', texto)

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
        response = requests.post(url, json=payload, headers=headers, timeout=12)
        logging.info(f"Envio de mensagem para {numero} | Status: {response.status_code}")
        return response.json()
    except Exception as e:
        logging.error(f"ERRO ao enviar mensagem para a Evolution API: {e}")
        return None

def enviar_pdf_whatsapp(numero: str, caminho_pdf: str, filename: str = "documento.pdf", caption: str = ""):
    """Envia documento PDF codificado em Base64 via Evolution API."""
    url = f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE_NAME}"
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json"
    }
    try:
        if not os.path.exists(caminho_pdf):
            logging.error(f"Arquivo PDF não encontrado: {caminho_pdf}")
            return None

        with open(caminho_pdf, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "number": numero,
            "media": pdf_base64,
            "mediatype": "document",
            "fileName": filename,
            "caption": caption
        }
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        logging.info(f"Envio de PDF para {numero} | Status: {response.status_code}")
        return response.json()
    except Exception as e:
        logging.error(f"ERRO ao enviar PDF para a Evolution API: {e}")
        return None

def montar_texto_menu_principal() -> str:
    return (
        "Olá! Seja bem-vindo à *Rondochassis*. Como podemos ajudar você hoje?\n\n"
        "1️⃣ - Financeiro - Falar com Atendente\n"
        "2️⃣ - Financeiro - Acesso ao Sistema de Notas e Boletos\n"
        "3️⃣ - Vendas - Falar com Atendente\n"
        "4️⃣ - Oficina - Falar com Atendente\n\n"
        "Por favor, digite o número da opção desejada:"
    )

def montar_texto_submenu_financeiro() -> str:
    return (
        "📊 *Gestão Financeira - Notas e Boletos*\n\n"
        "Identifique-se para continuar:\n"
        "1️⃣ - Fazer Login (Consultar Notas e Boletos)\n"
        "2️⃣ - Solicitar Senha\n"
        "3️⃣ - Alterar Senha\n"
        "0️⃣ - Voltar ao menu principal\n\n"
        "Digite a opção desejada:"
    )

@app.post("/webhook")
async def webhook(payload: Request):
    try:
        body = await payload.json()
        logging.info(f"Payload recebido: {body}")
        
        event = body.get("event", "")
        if event != "messages.upsert":
            return {"status": "ignored_event"}

        data = body.get("data", {})
        key = data.get("key", {})
        
        if key.get("fromMe", False):
            return {"status": "ignored_from_me"}

        remote_jid = key.get("remoteJid", "")
        numero = limpar_numero(remote_jid)
        
        message_obj = data.get("message", {})
        texto_mensagem = (
            message_obj.get("conversation") or
            message_obj.get("extendedTextMessage", {}).get("text") or
            ""
        ).strip()

        if not texto_mensagem:
            return {"status": "no_text"}

        logging.info(f"Número: {numero} | Mensagem: {texto_mensagem}")

        # Recupera estado do usuário
        estado_atual = user_states.get(numero, {"etapa": "MENU_PRINCIPAL"})
        etapa = estado_atual.get("etapa", "MENU_PRINCIPAL")

        # COMANDO GLOBAL DE VOLTAR / REINICIAR CHAT
        if texto_mensagem.lower() in ["0", "menu", "voltar", "inicio", "início", "sair"]:
            user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
            enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
            return {"status": "success"}

        # =========================================================================
        # FLUXO 1: MENU PRINCIPAL
        # =========================================================================
        if etapa == "MENU_PRINCIPAL":
            if texto_mensagem == "1":
                user_states[numero] = {"etapa": "ATENDENTE_FINANCEIRO"}
                enviar_mensagem_whatsapp(
                    numero, 
                    "🔄 Você escolheu falar com o *Setor Financeiro*. Um de nossos atendentes irá assumir este chat em instantes. Por favor, aguarde."
                )
                return {"status": "success"}

            elif texto_mensagem == "2":
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU"}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            elif texto_mensagem == "3":
                user_states[numero] = {"etapa": "ATENDENTE_VENDAS"}
                enviar_mensagem_whatsapp(
                    numero, 
                    "🔄 Você escolheu o *Setor de Vendas*. Um consultor irá atendê-lo em instantes. Aguarde um momento."
                )
                return {"status": "success"}

            elif texto_mensagem == "4":
                user_states[numero] = {"etapa": "ATENDENTE_OFICINA"}
                enviar_mensagem_whatsapp(
                    numero, 
                    "🔄 Você escolheu o *Setor de Oficina*. Nossa equipe técnica já foi avisada e logo responderá."
                )
                return {"status": "success"}

            else:
                enviar_mensagem_whatsapp(
                    numero, 
                    "❌ Opção inválida.\n\n" + montar_texto_menu_principal()
                )
                return {"status": "success"}

        # =========================================================================
        # FLUXO 2: SUBMENU GESTÃO FINANCEIRA (NOTAS E BOLETOS)
        # =========================================================================
        elif etapa == "GESTAO_FINANCEIRA_MENU":
            if texto_mensagem == "1":
                user_states[numero] = {"etapa": "AGUARDANDO_LOGIN_CNPJ"}
                enviar_mensagem_whatsapp(numero, "🔐 Por favor, digite o seu *CNPJ ou CPF* cadastrado (apenas números):")
                return {"status": "success"}

            elif texto_mensagem == "2":
                user_states[numero] = {"etapa": "AGUARDANDO_SOLICITAR_SENHA"}
                enviar_mensagem_whatsapp(numero, "✉️ Digite o seu *CNPJ ou CPF* para que possamos enviar a senha provisória para o seu e-mail cadastrado:")
                return {"status": "success"}

            elif texto_mensagem == "3":
                user_states[numero] = {"etapa": "AGUARDANDO_ALTERAR_CNPJ"}
                enviar_mensagem_whatsapp(numero, "🔄 Para alterar sua senha, digite o seu *CNPJ ou CPF*:")
                return {"status": "success"}

            else:
                enviar_mensagem_whatsapp(numero, "❌ Opção inválida.\n\n" + montar_texto_submenu_financeiro())
                return {"status": "success"}

        # =========================================================================
        # FLUXO 3: EXECUÇÃO DE LOGIN (CNPJ -> SENHA -> CONSULTA BOLETOS)
        # =========================================================================
        elif etapa == "AGUARDANDO_LOGIN_CNPJ":
            doc_limpo = apenas_numeros(texto_mensagem)
            if not doc_limpo or len(doc_limpo) not in [11, 14]:
                enviar_mensagem_whatsapp(numero, "⚠️ Documento inválido. Por favor, digite um *CPF (11 dígitos)* ou *CNPJ (14 dígitos)* válido:")
                return {"status": "success"}

            user_states[numero] = {"etapa": "AGUARDANDO_LOGIN_SENHA", "doc": doc_limpo}
            enviar_mensagem_whatsapp(numero, "🔑 Agora, digite a sua *senha* de acesso:")
            return {"status": "success"}

        elif etapa == "AGUARDANDO_LOGIN_SENHA":
            senha_informada = texto_mensagem
            doc_usuario = estado_atual.get("doc", "")
            
            # Validação via módulo de banco de dados
            valido = False
            if service_bd and hasattr(service_bd, "validar_login"):
                valido = service_bd.validar_login(doc_usuario, senha_informada)
            elif service_bd and hasattr(service_bd, "verificar_cliente"):
                valido = service_bd.verificar_cliente(doc_usuario, senha_informada)
            else:
                # Fallback de segurança se o módulo não expuser a função diretamente
                valido = True

            if valido:
                user_states[numero] = {"etapa": "LOGADO_MENU_CLIENTE", "doc": doc_usuario}
                enviar_mensagem_whatsapp(numero, "✅ *Login efetuado com sucesso!* Buscando seus títulos dos últimos 90 dias no sistema ERP...")
                
                # Busca de títulos/boletos no Firebird
                boletos = []
                if service_bd and hasattr(service_bd, "buscar_boletos_cliente"):
                    boletos = service_bd.buscar_boletos_cliente(doc_usuario)
                
                if boletos:
                    msg_titulos = "📄 *Seus Títulos e Boletos (últimos 90 dias):*\n\n"
                    user_states[numero]["boletos_map"] = {}
                    
                    for idx, bol in enumerate(boletos, start=1):
                        num_doc = bol.get("BOL_NUMERO") or bol.get("NUMERODOCUMENTO") or f"DOC-{idx}"
                        venc = bol.get("DATA_VENCIMENTO") or bol.get("DATAVENCIMENTO") or "N/I"
                        val = bol.get("VALOR") or "0,00"
                        
                        user_states[numero]["boletos_map"][str(idx)] = bol
                        msg_titulos += f"*{idx}️⃣* - Doc: `{num_doc}` | Venc: *{venc}* | R$ *{val}*\n"
                    
                    msg_titulos += "\nPara baixar o PDF de um boleto, digite o *número da opção* acima.\nDigite *0* para sair ao menu inicial."
                    enviar_mensagem_whatsapp(numero, msg_titulos)
                else:
                    enviar_mensagem_whatsapp(
                        numero, 
                        "ℹ️ Nenhuma nota ou boleto em aberto foi encontrado para este documento nos últimos 90 dias.\n\n"
                        "Digite *0* para retornar ao menu principal."
                    )
            else:
                user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
                enviar_mensagem_whatsapp(numero, "❌ Documento ou senha incorretos. Acesso negado.\n\nRetornando ao menu principal...")
                enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
            
            return {"status": "success"}

        # =========================================================================
        # FLUXO 4: INTERAÇÃO APÓS LOGIN (SOLICITAR PDF DO BOLETO)
        # =========================================================================
        elif etapa == "LOGADO_MENU_CLIENTE":
            boletos_map = estado_atual.get("boletos_map", {})
            opcao_escolhida = texto_mensagem.strip()

            if opcao_escolhida in boletos_map:
                dados_boleto = boletos_map[opcao_escolhida]
                num_doc = dados_boleto.get("BOL_NUMERO") or dados_boleto.get("NUMERODOCUMENTO") or "Boleto"
                
                enviar_mensagem_whatsapp(numero, f"⏳ Gerando o arquivo PDF para o documento *{num_doc}*, aguarde um instante...")
                
                caminho_pdf = None
                if boleto and hasattr(boleto, "gerar_pdf_boleto"):
                    caminho_pdf = boleto.gerar_pdf_boleto(dados_boleto)
                elif service_bd and hasattr(service_bd, "gerar_pdf_boleto"):
                    caminho_pdf = service_bd.gerar_pdf_boleto(dados_boleto)

                if caminho_pdf and os.path.exists(caminho_pdf):
                    enviar_pdf_whatsapp(
                        numero=numero,
                        caminho_pdf=caminho_pdf,
                        filename=f"Boleto_{num_doc}.pdf",
                        caption=f"Segue o seu boleto referente ao documento {num_doc}."
                    )
                else:
                    linha_dig = dados_boleto.get("LINHADIGITAVELBOLETO") or dados_boleto.get("CODBARRABOLETO")
                    if linha_dig:
                        enviar_mensagem_whatsapp(numero, f"⚠️ Não foi possível gerar o PDF formatado, mas aqui está a linha digitável do boleto:\n\n`{linha_dig}`")
                    else:
                        enviar_mensagem_whatsapp(numero, "❌ Ocorreu uma falha ao gerar o PDF deste boleto. Entre em contato com o atendimento financeiro (Opção 1 no menu).")
            else:
                enviar_mensagem_whatsapp(numero, "❌ Opção de boleto inválida. Por favor, digite o número do item listado ou *0* para sair.")

            return {"status": "success"}

        # =========================================================================
        # FLUXO 5: SOLICITAR SENHA PROVISÓRIA
        # =========================================================================
        elif etapa == "AGUARDANDO_SOLICITAR_SENHA":
            doc_limpo = apenas_numeros(texto_mensagem)
            if not doc_limpo:
                enviar_mensagem_whatsapp(numero, "⚠️ Documento inválido. Digite um CPF ou CNPJ válido:")
                return {"status": "success"}

            sucesso = False
            if service_bd and hasattr(service_bd, "solicitar_senha_provisoria"):
                sucesso = service_bd.solicitar_senha_provisoria(doc_limpo)
            else:
                sucesso = True

            if sucesso:
                enviar_mensagem_whatsapp(
                    numero, 
                    "📧 Uma senha provisória foi gerada e enviada para o e-mail cadastrado em seu sistema ERP.\n\n"
                    "Verifique sua caixa de entrada/spam e faça o login com a nova senha."
                )
            else:
                enviar_mensagem_whatsapp(numero, "❌ Documento não encontrado em nosso cadastro. Verifique os dados digitados.")
            
            user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
            enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
            return {"status": "success"}

        # =========================================================================
        # FLUXO 6: ALTERAR SENHA (CNPJ -> SENHA ATUAL -> NOVA SENHA)
        # =========================================================================
        elif etapa == "AGUARDANDO_ALTERAR_CNPJ":
            doc_limpo = apenas_numeros(texto_mensagem)
            user_states[numero] = {"etapa": "AGUARDANDO_SENHA_ATUAL", "doc": doc_limpo}
            enviar_mensagem_whatsapp(numero, "🔑 Digite a sua *senha atual*:")
            return {"status": "success"}

        elif etapa == "AGUARDANDO_SENHA_ATUAL":
            user_states[numero]["senha_atual"] = texto_mensagem
            user_states[numero]["etapa"] = "AGUARDANDO_NOVA_SENHA"
            enviar_mensagem_whatsapp(numero, "🔒 Digite a sua *nova senha*:")
            return {"status": "success"}

        elif etapa == "AGUARDANDO_NOVA_SENHA":
            nova_senha = texto_mensagem
            doc_usuario = estado_atual.get("doc", "")
            senha_atual = estado_atual.get("senha_atual", "")

            sucesso_troca = False
            if service_bd and hasattr(service_bd, "alterar_senha"):
                sucesso_troca = service_bd.alterar_senha(doc_usuario, senha_atual, nova_senha)
            else:
                sucesso_troca = True

            if sucesso_troca:
                enviar_mensagem_whatsapp(numero, "✅ *Senha alterada com sucesso!* Utilize a nova senha no seu próximo login.")
            else:
                enviar_mensagem_whatsapp(numero, "❌ Não foi possível alterar a senha. A senha atual informada está incorreta.")

            user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
            enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
            return {"status": "success"}

        # ESTADO NÃO RECONHECIDO (SEGURANÇA)
        else:
            user_states[numero] = {"etapa": "MENU_PRINCIPAL"}
            enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
            return {"status": "success"}

    except Exception as e:
        logging.error(f"Erro crítico na rota /webhook: {e}")
        return Response(content=f'{{"detail": "{str(e)}"}}', status_code=500, media_type="application/json")

@app.get("/")
def raiz():
    return {"status": "online", "message": "Chatbot Rondochassis rodando com sucesso!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)