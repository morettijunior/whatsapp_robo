import os
import sys
import time
import random
import string
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

# --- TEMPO DE INATIVIDADE PARA RESETAR O CHAT AO MENU INICIAL (EM SEGUNDOS) ---
TEMPO_EXPIRACAO_SEGUNDOS = 30 * 60  # 30 minutos

# --- MODO TESTE (Comente a linha abaixo com # para liberar o bot para todos) ---
#NUMEROS_PERMITIDOS_TESTE = ["556634211496"]

# --- DIRETÓRIO BASE REAL (FUNCIONA TANTO EM .PY QUANTO EM .EXE --ONEFILE) ---
if getattr(sys, "frozen", False):
    DIRETORIO_BASE = pathlib.Path(sys.executable).parent
else:
    DIRETORIO_BASE = pathlib.Path(__file__).parent

# --- CORREÇÃO PARA AMBIENTE SEM CONSOLE (--noconsole) ---
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# --- CONFIGURAÇÃO DE LOGS ---
caminho_log = DIRETORIO_BASE / "bot.log"
handlers_log = [logging.FileHandler(str(caminho_log), encoding="utf-8")]

if not getattr(sys, "frozen", False) and sys.stdout is not None:
    handlers_log.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=handlers_log
)

# --- IMPORTE DOS MÓDULOS INTERNOS DO SISTEMA ---
try:
    import service_bd
except ImportError:
    service_bd = None
    logging.warning("Módulo 'service_bd' não encontrado na pasta física.")

try:
    import service_email
except ImportError:
    service_email = None
    logging.warning("Módulo 'service_email' não encontrado na pasta física.")

try:
    import service_pdf
except ImportError:
    service_pdf = None
    logging.warning("Módulo 'service_pdf' não encontrado na pasta física.")

try:
    import boleto
except ImportError:
    boleto = None
    logging.warning("Módulo 'boleto' não encontrado na pasta física.")

try:
    import notas
except ImportError:
    notas = None
    logging.warning("Módulo 'notas' não encontrado na pasta física.")

# --- CARREGAR VARIÁVEIS DE AMBIENTE (.env) ---
caminho_env = DIRETORIO_BASE / ".env"
load_dotenv(dotenv_path=caminho_env, override=True)

EVOLUTION_URL = os.getenv("EVOLUTION_URL", "http://localhost:8080").strip().rstrip("/")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "rondochassis").strip()
API_KEY = os.getenv("API_KEY", "").strip()
PORT = int(os.getenv("PORT", "5000").strip())

logging.info(
    f"Inicializando Bot | .env encontrado: {caminho_env.exists()} | "
    f"URL: {EVOLUTION_URL} | Instância: {INSTANCE_NAME} | "
    f"API_KEY carregada: {'SIM' if API_KEY else 'NÃO (VAZIA)'} | "
    f"Modo Teste: {'ATIVO' if 'NUMEROS_PERMITIDOS_TESTE' in globals() and NUMEROS_PERMITIDOS_TESTE else 'DESATIVADO'}"
)

app = FastAPI()

# Dicionário de sessão e estados em memória por número de WhatsApp
user_states = {}

# Registro dos IDs de mensagens enviadas pelo próprio bot para diferenciá-las das enviadas pelo atendente
mensagens_enviadas_bot = {}


class WebhookPayload(BaseModel):
    event: str = None
    instance: str = None
    data: dict = {}


def limpar_numero(numero_remoto: str) -> str:
    """Remove sufixos de JID do WhatsApp e retorna o número limpo."""
    return numero_remoto.split("@")[0].split(":")[0]


def apenas_numeros(texto: str) -> str:
    """Remove pontuações e mantém apenas dígitos (para CPF/CNPJ/Telefone)."""
    return re.sub(r'\D', '', texto)


def formatar_numero_emoji(numero: int) -> str:
    """Converte cada dígito para emoji de tecla (ex: 1 -> 1️⃣, 10 -> 1️⃣0️⃣)."""
    return "".join(f"{d}\ufe0f\u20e3" for d in str(numero))


def gerar_senha_provisoria(tamanho: int = 6) -> str:
    """Gera senha alfanumérica maiúscula aleatória."""
    caracteres = string.ascii_uppercase + string.digits
    return "".join(random.choice(caracteres) for _ in range(tamanho))


def mascarar_email(email: str) -> str:
    """Mascara um endereço de e-mail preservando iniciais (ex: mo****@hot***.com)."""
    if not email or "@" not in email:
        return "***@***.***"
    usuario, dominio = email.strip().split("@", 1)
    prefixo_user = usuario[:2] if len(usuario) > 2 else usuario[:1]
    usuario_masc = f"{prefixo_user}****"

    if "." in dominio:
        provedor, extensao = dominio.split(".", 1)
        prefixo_prov = provedor[:3] if len(provedor) > 3 else provedor[:1]
        dominio_masc = f"{prefixo_prov}***.{extensao}"
    else:
        dominio_masc = f"{dominio[:2]}***"

    return f"{usuario_masc}@{dominio_masc}"


def obter_config_sistema() -> dict:
    """Carrega o arquivo config_sistema.json gerado pela GUI."""
    config_file = pathlib.Path.home() / "Documents" / "RondochassisBot" / "config_sistema.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erro ao ler config_sistema.json: {e}")
    return {}


def obter_numeros_ignorados() -> set:
    """Lê a lista de números ignorados configurada na GUI (config_sistema.json)."""
    dados = obter_config_sistema()
    bruto = dados.get("numeros_ignorados", "")
    return {apenas_numeros(n) for n in bruto.split(",") if apenas_numeros(n)}


def obter_numero_setor(chave: str) -> str:
    """Lê e formata o número de WhatsApp de Vendas ou Oficina para link wa.me."""
    dados = obter_config_sistema()
    numero_limpo = apenas_numeros(dados.get(chave, ""))
    if numero_limpo and len(numero_limpo) in [10, 11]:
        numero_limpo = "55" + numero_limpo
    return numero_limpo


def _registrar_id_mensagem_bot(resposta_json: dict):
    """Armazena temporariamente o ID da mensagem enviada pela API do bot."""
    if not isinstance(resposta_json, dict):
        return
    msg_id = (
        resposta_json.get("key", {}).get("id")
        or resposta_json.get("data", {}).get("key", {}).get("id")
        or resposta_json.get("id")
    )
    if msg_id:
        agora = time.time()
        mensagens_enviadas_bot[msg_id] = agora
        # Limpa registros com mais de 5 minutos para não acumular memória
        expirados = [k for k, ts in mensagens_enviadas_bot.items() if agora - ts > 300]
        for k in expirados:
            mensagens_enviadas_bot.pop(k, None)


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
        dados_resp = response.json()
        _registrar_id_mensagem_bot(dados_resp)
        return dados_resp
    except Exception as e:
        logging.error(f"ERRO ao enviar mensagem para a Evolution API: {e}")
        return None


def enviar_documento_whatsapp(numero: str, caminho_arquivo: str, filename: str = None, caption: str = ""):
    """Envia documento (PDF ou XML) codificado em Base64 via Evolution API."""
    url = f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE_NAME}"
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json"
    }
    try:
        if not os.path.exists(caminho_arquivo):
            logging.error(f"Arquivo não encontrado para envio: {caminho_arquivo}")
            return None

        nome_final = filename or os.path.basename(caminho_arquivo)
        ext = os.path.splitext(nome_final)[1].lower()
        mimetype = "application/xml" if ext == ".xml" else "application/pdf"

        with open(caminho_arquivo, "rb") as f:
            arquivo_base64 = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "number": numero,
            "media": arquivo_base64,
            "mediatype": "document",
            "mimetype": mimetype,
            "fileName": nome_final,
            "caption": caption
        }
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        logging.info(f"Envio de documento ({nome_final}) para {numero} | Status: {response.status_code}")
        dados_resp = response.json()
        _registrar_id_mensagem_bot(dados_resp)
        return dados_resp
    except Exception as e:
        logging.error(f"ERRO ao enviar documento para a Evolution API: {e}")
        return None


def enviar_pdf_whatsapp(numero: str, caminho_pdf: str, filename: str = "documento.pdf", caption: str = ""):
    """Wrapper para envio de documentos PDF."""
    return enviar_documento_whatsapp(numero, caminho_pdf, filename=filename, caption=caption)


def montar_texto_menu_principal() -> str:
    return (
        "Olá! Seja bem-vindo à *Rondochassis*. Como podemos ajudar você hoje?\n\n"
        "1️⃣ - Financeiro - Falar com Atendente\n"
        "2️⃣ - Vendas - Falar com Atendente\n"
        "3️⃣ - Oficina - Falar com Atendente\n\n"
        "4️⃣ - Financeiro - Gestão de Notas e Boletos\n\n"
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


def montar_texto_submenu_periodo() -> str:
    return (
        "📅 *Selecione o período para consulta:*\n\n"
        "0️⃣1️⃣ - Últimos 30 dias\n"
        "0️⃣2️⃣ - Últimos 60 dias\n"
        "0️⃣3️⃣ - Últimos 90 dias\n"
        "0️⃣ - Voltar\n\n"
        "Digite a opção desejada:"
    )


def formatar_bloco_pedido_chat(indice: int, ped: dict) -> str:
    """Formata um pedido para exibição no chat no mesmo padrão do relatório PDF."""
    linhas = [f"{formatar_numero_emoji(indice)}"]

    os_num = str(ped.get("OS") or "").strip()
    if os_num and os_num != "-":
        linhas.append(f"O.S. *{os_num}*")

    ped_num = str(ped.get("PEDIDO") or ped.get("NUMERO_PEDIDO") or "").strip()
    if ped_num and ped_num != "-":
        linhas.append(f"PEDIDO *{ped_num}*")

    nota_raw = str(ped.get("NOTA") or "").strip()
    partes_notas = [p.strip() for p in nota_raw.split() if p.strip() and p.strip() != "-"]
    nfs_mun = str(ped.get("NUMERO_NFS_MUNICIPAL") or "").strip()
    if nfs_mun and nfs_mun != "-" and nfs_mun not in partes_notas:
        partes_notas.append(nfs_mun)

    if partes_notas:
        linhas.append(f"NOTAS *{'/'.join(partes_notas)}*")

    for parc in ped.get("PARCELAS", []):
        num_p = parc.get("PARCELA", 1)
        venc = parc.get("VENCIMENTO") or "N/I"
        val_float = float(parc.get("VALOR") or 0.0)
        val_fmt = f"{val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        status_raw = str(parc.get("STATUS") or "").strip().upper()
        status_txt = "PAGO" if status_raw == "BAIXADO" else "ABERTO"
        linhas.append(f"VENC {num_p} {venc} R${val_fmt} *{status_txt}*")

    return "\n".join(linhas)


@app.post("/webhook")
def webhook(body: dict):
    try:
        logging.info(f"Payload recebido: {body}")
        
        event = body.get("event", "")
        if event != "messages.upsert":
            return {"status": "ignored_event"}

        data = body.get("data", {})
        key = data.get("key", {})

        remote_jid = key.get("remoteJid", "")
        remote_jid_alt = key.get("remoteJidAlt", "")

        # Quando o WhatsApp envia ID privado (@lid), usa remoteJidAlt se disponível
        jid_efetivo = remote_jid_alt if ("@lid" in remote_jid and "@s.whatsapp.net" in remote_jid_alt) else remote_jid

        if "@g.us" in jid_efetivo or "status@broadcast" in jid_efetivo:
            return {"status": "ignored_group"}

        if "@lid" in jid_efetivo:
            logging.warning(f"Mensagem recebida apenas com @lid sem número real ({jid_efetivo}). Ignorando envio.")
            return {"status": "ignored_lid_without_phone"}

        numero = limpar_numero(jid_efetivo)

        # Ignora mensagens antigas represadas pela fila da Evolution API (mais de 3 minutos de atraso)
        msg_ts = data.get("messageTimestamp")
        if msg_ts and not key.get("fromMe", False):
            try:
                atraso_segundos = time.time() - int(msg_ts)
                if atraso_segundos > 180:
                    logging.warning(f"Mensagem antiga ignorada ({int(atraso_segundos)}s de atraso) de {numero}.")
                    return {"status": "ignored_stale_message"}
            except Exception:
                pass

        # Se a mensagem partiu do próprio número da empresa (fromMe = True)
        if key.get("fromMe", False):
            msg_id = key.get("id", "")
            # Se o ID foi gerado pela própria API do bot, ignora apenas o eco
            if msg_id and msg_id in mensagens_enviadas_bot:
                return {"status": "ignored_bot_echo"}

            # Caso contrário, foi enviada manualmente pelo atendente (celular ou WhatsApp Web):
            # pausa o bot para este cliente e inicia/renova o cronômetro de 30 minutos
            agora_atendente = time.time()
            user_states[numero] = {
                "etapa": "ATENDENTE_FINANCEIRO",
                "ultima_interacao": agora_atendente,
            }
            logging.info(f"Atendente iniciou/respondeu conversa com {numero}. Bot pausado por 30 min.")
            return {"status": "human_initiated_pause"}

        # Trava do Modo Teste (atua apenas enquanto NUMEROS_PERMITIDOS_TESTE não estiver comentado)
        if "NUMEROS_PERMITIDOS_TESTE" in globals() and NUMEROS_PERMITIDOS_TESTE:
            permitidos = {apenas_numeros(n) for n in NUMEROS_PERMITIDOS_TESTE}
            if apenas_numeros(numero) not in permitidos:
                logging.info(f"Modo Teste ativo - Número não autorizado ignorado: {numero}")
                return {"status": "ignored_test_mode"}

        # Verifica lista de números ignorados configurada na GUI
        if apenas_numeros(numero) in obter_numeros_ignorados():
            logging.info(f"Número ignorado conforme configuração da GUI: {numero}")
            return {"status": "ignored_number"}
        
        message_obj = data.get("message", {})
        texto_mensagem = (
            message_obj.get("conversation") or
            message_obj.get("extendedTextMessage", {}).get("text") or
            ""
        ).strip()

        if not texto_mensagem:
            return {"status": "no_text"}

        logging.info(f"Número: {numero} | Mensagem: {texto_mensagem}")

        # Controle de expiração de sessão por inatividade
        agora = time.time()
        sessao = user_states.get(numero)

        if sessao and (agora - sessao.get("ultima_interacao", 0) > TEMPO_EXPIRACAO_SEGUNDOS):
            logging.info(f"Sessão expirada por inatividade para {numero}. Reiniciando fluxo.")
            user_states.pop(numero, None)
            sessao = None

        primeiro_contato = sessao is None
        estado_atual = sessao if sessao else {"etapa": "MENU_PRINCIPAL"}
        etapa = estado_atual.get("etapa", "MENU_PRINCIPAL")

        # Etapas filhas do submenu Gestão Financeira onde "0" retorna ao submenu
        etapas_filhas_financeiro = {
            "AGUARDANDO_LOGIN_CNPJ",
            "AGUARDANDO_LOGIN_SENHA",
            "AGUARDANDO_PERIODO_RELATORIO",
            "AGUARDANDO_SOLICITAR_SENHA",
            "AGUARDANDO_ALTERAR_CNPJ",
            "AGUARDANDO_SENHA_ATUAL",
            "AGUARDANDO_NOVA_SENHA"
        }

        # COMANDO GLOBAL DE VOLTAR / REINICIAR CHAT
        if texto_mensagem.lower() in ["0", "menu", "voltar", "inicio", "início", "sair"]:
            if texto_mensagem == "0" and etapa in etapas_filhas_financeiro:
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            user_states[numero] = {"etapa": "MENU_PRINCIPAL", "ultima_interacao": agora}
            enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
            return {"status": "success"}

        # =========================================================================
        # FLUXO 1: MENU PRINCIPAL
        # =========================================================================
        if etapa == "MENU_PRINCIPAL":
            if texto_mensagem == "1":
                user_states[numero] = {"etapa": "ATENDENTE_FINANCEIRO", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(
                    numero, 
                    "🔄 Você escolheu falar com o *Setor Financeiro*. Um de nossos atendentes irá assumir este chat em instantes. Por favor, aguarde.\n\n"
                    "_(Caso queira retornar ao menu automático a qualquer momento, digite *0*)_"
                )
                return {"status": "success"}

            elif texto_mensagem == "2":
                user_states[numero] = {"etapa": "MENU_PRINCIPAL", "ultima_interacao": agora}
                num_vendas = obter_numero_setor("whatsapp_vendas")
                if num_vendas:
                    enviar_mensagem_whatsapp(
                        numero,
                        f"🛒 *Setor de Vendas - Rondochassis*\n\n"
                        f"Para falar diretamente com nossa equipe de Vendas, clique no link abaixo:\n"
                        f"👉 https://wa.me/{num_vendas}"
                    )
                else:
                    enviar_mensagem_whatsapp(
                        numero,
                        "⚠️ O número direto do *Setor de Vendas* ainda não foi configurado no sistema. Por favor, tente novamente mais tarde."
                    )
                enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
                return {"status": "success"}

            elif texto_mensagem == "3":
                user_states[numero] = {"etapa": "MENU_PRINCIPAL", "ultima_interacao": agora}
                num_oficina = obter_numero_setor("whatsapp_oficina")
                if num_oficina:
                    enviar_mensagem_whatsapp(
                        numero,
                        f"🔧 *Setor de Oficina - Rondochassis*\n\n"
                        f"Para falar diretamente com nossa equipe da Oficina, clique no link abaixo:\n"
                        f"👉 https://wa.me/{num_oficina}"
                    )
                else:
                    enviar_mensagem_whatsapp(
                        numero,
                        "⚠️ O número direto do *Setor de Oficina* ainda não foi configurado no sistema. Por favor, tente novamente mais tarde."
                    )
                enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
                return {"status": "success"}

            elif texto_mensagem == "4":
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            else:
                user_states[numero] = {"etapa": "MENU_PRINCIPAL", "ultima_interacao": agora}
                if primeiro_contato:
                    enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
                else:
                    enviar_mensagem_whatsapp(
                        numero, 
                        "❌ Opção inválida.\n\n" + montar_texto_menu_principal()
                    )
                return {"status": "success"}

        # =========================================================================
        # ATENDIMENTO HUMANO FINANCEIRO EM ANDAMENTO (SILENCIA O BOT E RENOVA TIMER)
        # =========================================================================
        elif etapa == "ATENDENTE_FINANCEIRO":
            user_states[numero]["ultima_interacao"] = agora
            logging.info(f"Chat de {numero} em atendimento humano ({etapa}). Bot aguardando.")
            return {"status": "in_human_attendance"}

        # =========================================================================
        # FLUXO 2: SUBMENU GESTÃO FINANCEIRA (NOTAS E BOLETOS)
        # =========================================================================
        elif etapa == "GESTAO_FINANCEIRA_MENU":
            user_states[numero]["ultima_interacao"] = agora
            if texto_mensagem == "1":
                user_states[numero] = {"etapa": "AGUARDANDO_LOGIN_CNPJ", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(
                    numero,
                    "🔐 Por favor, digite o seu *CNPJ ou CPF* cadastrado (apenas números):\n\n"
                    "Digite *0* para retornar."
                )
                return {"status": "success"}

            elif texto_mensagem == "2":
                user_states[numero] = {"etapa": "AGUARDANDO_SOLICITAR_SENHA", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(
                    numero,
                    "✉️ Digite o seu *CNPJ ou CPF* para que possamos enviar a senha provisória para o seu e-mail cadastrado:\n\n"
                    "Digite *0* para retornar."
                )
                return {"status": "success"}

            elif texto_mensagem == "3":
                user_states[numero] = {"etapa": "AGUARDANDO_ALTERAR_CNPJ", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(
                    numero,
                    "🔄 Para alterar sua senha, digite o seu *CNPJ ou CPF*:\n\n"
                    "Digite *0* para retornar."
                )
                return {"status": "success"}

            else:
                enviar_mensagem_whatsapp(numero, "❌ Opção inválida.\n\n" + montar_texto_submenu_financeiro())
                return {"status": "success"}

        # =========================================================================
        # FLUXO 3: EXECUÇÃO DE LOGIN (CNPJ -> SENHA -> PERÍODO -> RELATÓRIO)
        # =========================================================================
        elif etapa == "AGUARDANDO_LOGIN_CNPJ":
            user_states[numero]["ultima_interacao"] = agora
            doc_limpo = apenas_numeros(texto_mensagem)
            if not doc_limpo or len(doc_limpo) not in [11, 14]:
                enviar_mensagem_whatsapp(
                    numero,
                    "⚠️ Documento inválido. Por favor, digite um *CPF (11 dígitos)* ou *CNPJ (14 dígitos)* válido:\n\n"
                    "Digite *0* para retornar."
                )
                return {"status": "success"}

            if not service_bd:
                enviar_mensagem_whatsapp(numero, "❌ Erro interno: módulo de banco de dados indisponível.")
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            cliente = service_bd.buscar_cliente_por_documento(doc_limpo)
            status_cli = cliente.get("status")

            if status_cli == "inativo":
                enviar_mensagem_whatsapp(
                    numero,
                    "⚠️ O seu cadastro consta como *INATIVO* em nosso sistema.\n\n"
                    "Por favor, consulte o setor financeiro (Opção *1* no menu inicial) para regularizar."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            if status_cli != "encontrado":
                enviar_mensagem_whatsapp(
                    numero,
                    "❌ Não existe esse CPF/CNPJ cadastrado em nosso sistema.\n\n"
                    "Caso precise de ajuda, entre em contato com o setor financeiro."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            user_states[numero] = {
                "etapa": "AGUARDANDO_LOGIN_SENHA",
                "doc": doc_limpo,
                "codcfo": cliente.get("codcfo"),
                "nome": cliente.get("nome"),
                "ultima_interacao": agora
            }
            enviar_mensagem_whatsapp(
                numero,
                f"👤 Cadastro localizado: *{cliente.get('nome')}*\n"
                "🔑 Agora, digite a sua *senha* de acesso:\n\n"
                "Digite *0* para retornar."
            )
            return {"status": "success"}

        elif etapa == "AGUARDANDO_LOGIN_SENHA":
            senha_informada = texto_mensagem.strip()
            doc_usuario = estado_atual.get("doc", "")
            codcfo = estado_atual.get("codcfo", "")
            nome_cliente = estado_atual.get("nome", "")
            
            valido = False
            if service_bd and codcfo:
                valido = service_bd.verificar_senha_robo(codcfo, senha_informada)

            if valido:
                user_states[numero] = {
                    "etapa": "AGUARDANDO_PERIODO_RELATORIO",
                    "doc": doc_usuario,
                    "codcfo": codcfo,
                    "nome": nome_cliente,
                    "ultima_interacao": agora
                }
                enviar_mensagem_whatsapp(
                    numero,
                    "✅ *Login efetuado com sucesso!*\n\n" + montar_texto_submenu_periodo()
                )
            else:
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, "❌ Senha incorreta. Acesso negado.")
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
            
            return {"status": "success"}

        elif etapa == "AGUARDANDO_PERIODO_RELATORIO":
            user_states[numero]["ultima_interacao"] = agora
            opcao_periodo = texto_mensagem.strip().lstrip("0")
            mapa_periodos = {"1": 30, "2": 60, "3": 90}

            if opcao_periodo not in mapa_periodos:
                enviar_mensagem_whatsapp(
                    numero,
                    "❌ Opção inválida.\n\n" + montar_texto_submenu_periodo()
                )
                return {"status": "success"}

            dias_escolhidos = mapa_periodos[opcao_periodo]
            doc_usuario = estado_atual.get("doc", "")
            codcfo = estado_atual.get("codcfo", "")
            nome_cliente = estado_atual.get("nome", "")

            user_states[numero] = {
                "etapa": "LOGADO_MENU_CLIENTE",
                "doc": doc_usuario,
                "codcfo": codcfo,
                "nome": nome_cliente,
                "dias_periodo": dias_escolhidos,
                "ultima_interacao": agora
            }
            enviar_mensagem_whatsapp(
                numero,
                f"⏳ Buscando seus pedidos dos últimos *{dias_escolhidos} dias* no sistema ERP..."
            )
            
            pedidos = service_bd.consultar_relatorio_pedidos_90_dias(codcfo, dias=dias_escolhidos)
            
            if pedidos:
                # Gera e envia o PDF consolidado do período selecionado
                if service_pdf:
                    try:
                        validacao_doc = service_bd.validar_e_formatar_documento(doc_usuario)
                        doc_fmt = validacao_doc.get("documento", doc_usuario)
                        caminho_relatorio = service_pdf.gerar_pdf_relatorio_90_dias(nome_cliente, doc_fmt, pedidos)
                        if caminho_relatorio and os.path.exists(caminho_relatorio):
                            enviar_pdf_whatsapp(
                                numero=numero,
                                caminho_pdf=caminho_relatorio,
                                filename=f"Extrato_Financeiro_{dias_escolhidos}_Dias.pdf",
                                caption=f"📊 Segue o seu extrato consolidado dos últimos {dias_escolhidos} dias."
                            )
                    except Exception as e_pdf:
                        logging.error(f"Erro ao gerar/enviar relatório {dias_escolhidos} dias: {e_pdf}")

                # Monta a mensagem no chat dividida por PEDIDO (espelhando o PDF)
                user_states[numero]["pedidos_map"] = {}
                blocos_pedidos = []

                for idx, ped in enumerate(pedidos, start=1):
                    user_states[numero]["pedidos_map"][str(idx)] = ped
                    blocos_pedidos.append(formatar_bloco_pedido_chat(idx, ped))

                msg_pedidos = (
                    f"📋 *Pedidos e Títulos (últimos {dias_escolhidos} dias):*\n\n"
                    + "\n\n──────────────\n\n".join(blocos_pedidos)
                    + "\n\nDigite o *número do pedido* acima para receber os boletos e notas existentes.\n"
                    "Digite *P* para escolher outro período (30/60/90 dias) ou *0* para voltar ao menu inicial."
                )
                enviar_mensagem_whatsapp(numero, msg_pedidos)
            else:
                enviar_mensagem_whatsapp(
                    numero, 
                    f"ℹ️ Nenhum pedido ou título foi encontrado para este documento nos últimos *{dias_escolhidos} dias*.\n\n"
                    "Digite *P* para consultar outro período (30/60/90 dias) ou *0* para retornar ao menu principal."
                )
            
            return {"status": "success"}

        # =========================================================================
        # FLUXO 4: INTERAÇÃO APÓS LOGIN (ENVIO DE NOTAS XML/PDF + BOLETOS PDF)
        # =========================================================================
        elif etapa == "LOGADO_MENU_CLIENTE":
            user_states[numero]["ultima_interacao"] = agora
            pedidos_map = estado_atual.get("pedidos_map", {})
            opcao_escolhida = texto_mensagem.strip()

            if opcao_escolhida.upper() == "P":
                user_states[numero]["etapa"] = "AGUARDANDO_PERIODO_RELATORIO"
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_periodo())
                return {"status": "success"}

            if opcao_escolhida in pedidos_map:
                pedido_selecionado = pedidos_map[opcao_escolhida]
                ped_num = pedido_selecionado.get("PEDIDO") or pedido_selecionado.get("NUMERO_PEDIDO") or opcao_escolhida
                cfg_sistema = obter_config_sistema()

                enviar_mensagem_whatsapp(numero, f"⏳ Buscando boletos e notas do *Pedido {ped_num}*, aguarde um instante...")

                arquivos_enviados = 0
                arquivos_nao_localizados = []

                # 1. Busca e envia NF-e (XML + PDF) e NFS-e (PDF) via módulo notas.py
                if notas and hasattr(notas, "buscar_arquivos_notas"):
                    resultado_notas = notas.buscar_arquivos_notas(pedido_selecionado, cfg_sistema)
                    for item_nota in resultado_notas.get("encontrados", []):
                        caminho_arq = item_nota["caminho"]
                        nome_arq = item_nota["filename"]
                        tipo_arq = item_nota["tipo"]
                        resp_nota = enviar_documento_whatsapp(
                            numero=numero,
                            caminho_arquivo=caminho_arq,
                            filename=nome_arq,
                            caption=f"📄 {tipo_arq} - Pedido {ped_num}"
                        )
                        if resp_nota:
                            arquivos_enviados += 1
                    arquivos_nao_localizados.extend(resultado_notas.get("nao_encontrados", []))

                # 2. Gera e envia os Boletos PDF do pedido
                if pedido_selecionado.get("BOLETOS"):
                    pasta_boletos = pathlib.Path.home() / "Documents" / "RondochassisBot" / "boletos"
                    pasta_boletos.mkdir(parents=True, exist_ok=True)

                    caminhos_boletos = []
                    if boleto and hasattr(boleto, "gerar_pdf_boleto"):
                        caminhos_boletos = boleto.gerar_pdf_boleto(
                            pedido_selecionado,
                            str(pasta_boletos),
                            cfg_sistema
                        )

                    if caminhos_boletos:
                        for caminho_pdf in caminhos_boletos:
                            if caminho_pdf and os.path.exists(caminho_pdf):
                                nome_arquivo = os.path.basename(caminho_pdf)
                                enviar_pdf_whatsapp(
                                    numero=numero,
                                    caminho_pdf=caminho_pdf,
                                    filename=nome_arquivo,
                                    caption=f"🧾 Boleto - Pedido {ped_num}"
                                )
                                arquivos_enviados += 1
                    else:
                        for bol in pedido_selecionado.get("BOLETOS", []):
                            linha_dig = bol.get("LINHADIGITAVELBOLETO") or bol.get("CODBARRABOLETO")
                            if linha_dig:
                                enviar_mensagem_whatsapp(
                                    numero,
                                    f"⚠️ Linha digitável (Parcela {bol.get('PARCELA', 1)}):\n\n`{linha_dig}`"
                                )

                # 3. Aviso específico caso alguma nota exista no banco mas o arquivo não esteja na pasta
                if arquivos_nao_localizados:
                    lista_faltantes = "\n".join(f"• *{item}*" for item in arquivos_nao_localizados)
                    enviar_mensagem_whatsapp(
                        numero,
                        f"⚠️ Não foi possível enviar automaticamente o(s) seguinte(s) arquivo(s) do *Pedido {ped_num}*:\n\n"
                        f"{lista_faltantes}\n\n"
                        "Por favor, procure o setor financeiro (Opção *1* no menu inicial) para solicitá-lo(s)."
                    )
                elif arquivos_enviados == 0:
                    enviar_mensagem_whatsapp(
                        numero,
                        f"⚠️ Nenhum arquivo foi localizado para o *Pedido {ped_num}*. "
                        "Caso precise de segunda via, procure o setor financeiro."
                    )

                enviar_mensagem_whatsapp(
                    numero,
                    "Digite *outro número* da lista acima para baixar os arquivos, *P* para mudar o período ou *0* para voltar."
                )
            else:
                enviar_mensagem_whatsapp(
                    numero,
                    "❌ Opção inválida. Digite o *número do pedido* listado acima, *P* para mudar o período ou *0* para voltar."
                )

            return {"status": "success"}

        # =========================================================================
        # FLUXO 5: SOLICITAR SENHA PROVISÓRIA (OPÇÃO 2-2)
        # =========================================================================
        elif etapa == "AGUARDANDO_SOLICITAR_SENHA":
            user_states[numero]["ultima_interacao"] = agora
            doc_limpo = apenas_numeros(texto_mensagem)

            if not doc_limpo or len(doc_limpo) not in [11, 14]:
                enviar_mensagem_whatsapp(
                    numero,
                    "⚠️ Formato inválido. Digite um *CPF (11 dígitos)* ou *CNPJ (14 dígitos)* válido:\n\n"
                    "Digite *0* para retornar."
                )
                return {"status": "success"}

            if not service_bd or not service_email:
                logging.error("Módulos service_bd ou service_email ausentes ao solicitar senha.")
                enviar_mensagem_whatsapp(
                    numero,
                    "❌ Serviço de envio de senha temporariamente indisponível. Entre em contato com o financeiro."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            cliente = service_bd.buscar_cliente_por_documento(doc_limpo)
            status_cli = cliente.get("status")

            if status_cli == "inativo":
                enviar_mensagem_whatsapp(
                    numero,
                    "⚠️ O seu cadastro consta como *INATIVO* em nosso sistema.\n\n"
                    "Por favor, consulte o setor financeiro (Opção *1* no menu inicial) para regularizar."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            if status_cli != "encontrado":
                enviar_mensagem_whatsapp(
                    numero,
                    "❌ Não existe esse CPF/CNPJ cadastrado em nosso sistema.\n\n"
                    "Verifique o número digitado ou entre em contato com o financeiro."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            email_cliente = cliente.get("email", "").strip()
            if not email_cliente:
                enviar_mensagem_whatsapp(
                    numero,
                    "⚠️ Encontramos o seu cadastro, porém não há nenhum e-mail cadastrado no sistema.\n\n"
                    "Se deseja cadastrar ou alterar o e-mail, entrar em contato com o financeiro."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            nova_senha = gerar_senha_provisoria(6)
            codcfo = cliente.get("codcfo")
            nome = cliente.get("nome")

            salvou_bd = service_bd.salvar_ou_atualizar_senha_robo(codcfo, nome, email_cliente, nova_senha)
            if not salvou_bd:
                enviar_mensagem_whatsapp(
                    numero,
                    "❌ Erro ao registrar a senha provisória no banco de dados. Tente novamente ou fale com o financeiro."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            enviou_email = service_email.enviar_email_senha_provisoria(email_cliente, nome, nova_senha)
            if enviou_email:
                email_mascarado = mascarar_email(email_cliente)
                enviar_mensagem_whatsapp(
                    numero,
                    f"📧 Uma senha provisória foi gerada e enviada para o e-mail do seu cadastro ({email_mascarado}).\n\n"
                    "Se deseja alterar o e-mail, entrar em contato com o financeiro."
                )
            else:
                enviar_mensagem_whatsapp(
                    numero,
                    "❌ Houve uma falha ao enviar o e-mail com a senha provisória. Por favor, entre em contato com o financeiro."
                )

            user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
            enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
            return {"status": "success"}

        # =========================================================================
        # FLUXO 6: ALTERAR SENHA (CNPJ -> SENHA ATUAL -> NOVA SENHA)
        # =========================================================================
        elif etapa == "AGUARDANDO_ALTERAR_CNPJ":
            user_states[numero]["ultima_interacao"] = agora
            doc_limpo = apenas_numeros(texto_mensagem)

            if not doc_limpo or len(doc_limpo) not in [11, 14]:
                enviar_mensagem_whatsapp(
                    numero,
                    "⚠️ Formato inválido. Digite um *CPF (11 dígitos)* ou *CNPJ (14 dígitos)* válido:\n\n"
                    "Digite *0* para retornar."
                )
                return {"status": "success"}

            if not service_bd:
                enviar_mensagem_whatsapp(numero, "❌ Erro interno: módulo de banco de dados indisponível.")
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            cliente = service_bd.buscar_cliente_por_documento(doc_limpo)
            status_cli = cliente.get("status")

            if status_cli == "inativo":
                enviar_mensagem_whatsapp(
                    numero,
                    "⚠️ O seu cadastro consta como *INATIVO* em nosso sistema.\n\n"
                    "Por favor, consulte o setor financeiro (Opção *1* no menu inicial) para regularizar."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            if status_cli != "encontrado":
                enviar_mensagem_whatsapp(
                    numero,
                    "❌ Não existe esse CPF/CNPJ cadastrado em nosso sistema.\n\n"
                    "Caso precise de ajuda, entre em contato com o setor financeiro."
                )
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
                return {"status": "success"}

            user_states[numero] = {
                "etapa": "AGUARDANDO_SENHA_ATUAL",
                "doc": doc_limpo,
                "codcfo": cliente.get("codcfo"),
                "nome": cliente.get("nome"),
                "email": cliente.get("email", ""),
                "ultima_interacao": agora
            }
            enviar_mensagem_whatsapp(
                numero,
                "🔑 Digite a sua *senha atual*:\n\n"
                "Digite *0* para retornar."
            )
            return {"status": "success"}

        elif etapa == "AGUARDANDO_SENHA_ATUAL":
            user_states[numero]["ultima_interacao"] = agora
            codcfo = estado_atual.get("codcfo", "")
            senha_atual = texto_mensagem.strip()

            if service_bd and codcfo and service_bd.verificar_senha_robo(codcfo, senha_atual):
                user_states[numero]["etapa"] = "AGUARDANDO_NOVA_SENHA"
                enviar_mensagem_whatsapp(
                    numero,
                    "🔒 Digite a sua *nova senha*:\n\n"
                    "Digite *0* para retornar."
                )
            else:
                enviar_mensagem_whatsapp(numero, "❌ Senha atual incorreta. Não foi possível continuar a alteração.")
                user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
                enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
            return {"status": "success"}

        elif etapa == "AGUARDANDO_NOVA_SENHA":
            nova_senha = texto_mensagem.strip()
            codcfo = estado_atual.get("codcfo", "")
            nome = estado_atual.get("nome", "")
            email = estado_atual.get("email", "")

            sucesso_troca = False
            if service_bd and codcfo:
                sucesso_troca = service_bd.salvar_ou_atualizar_senha_robo(codcfo, nome, email, nova_senha)

            if sucesso_troca:
                enviar_mensagem_whatsapp(numero, "✅ *Senha alterada com sucesso!* Utilize a nova senha para fazer login.")
            else:
                enviar_mensagem_whatsapp(numero, "❌ Erro ao salvar a nova senha no banco de dados. Tente novamente mais tarde.")

            user_states[numero] = {"etapa": "GESTAO_FINANCEIRA_MENU", "ultima_interacao": agora}
            enviar_mensagem_whatsapp(numero, montar_texto_submenu_financeiro())
            return {"status": "success"}

        # ESTADO NÃO RECONHECIDO (SEGURANÇA)
        else:
            user_states[numero] = {"etapa": "MENU_PRINCIPAL", "ultima_interacao": agora}
            enviar_mensagem_whatsapp(numero, montar_texto_menu_principal())
            return {"status": "success"}

    except Exception as e:
        logging.error(f"Erro crítico na rota /webhook: {e}")
        return Response(content=f'{{"detail": "{str(e)}"}}', status_code=500, media_type="application/json")


@app.get("/")
def raiz():
    return {"status": "online", "message": "Chatbot Rondochassis rodando com sucesso!"}


if __name__ == "__main__":
    logging.info(f"Servidor FastAPI ativo e aguardando webhooks na porta {PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)