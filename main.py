from fastapi import FastAPI, Request
import requests
import os
import logging
import uvicorn
import random
import string
from dotenv import load_dotenv

# Importa os serviços que criamos
from service_bd import (
    buscar_cliente_por_documento, 
    salvar_ou_atualizar_senha_robo, 
    verificar_senha_robo
)
from service_email import enviar_email_senha_provisoria

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

def mascarar_email(email):
    """Mascara o e-mail para exibição segura no WhatsApp (ex: rondo****@gmail.com)"""
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

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        payload = await request.json()
        
        if payload.get("event") == "messages.upsert":
            data = payload.get("data", {})
            
            if data.get("key", {}).get("fromMe"):
                return {"status": "ignored"}
                
            remote_jid = data.get("key", {}).get("remoteJid")
            
            # Extrai apenas os números do JID
            numero_limpo = remote_jid.split("@")[0] if remote_jid else ""
            
            # =========================================================================
            # TRAVA TEMPORÁRIA PARA TESTES:
            # Ignora tudo e permite apenas o número de teste autorizado (6634211496)
            # =========================================================================
            NUMERO_AUTORIZADO_TESTE = "556634211496"
            if numero_limpo != NUMERO_AUTORIZADO_TESTE:
                return {"status": "ignored_test_mode"}
            # =========================================================================

            # (Mantida a lógica oficial para o futuro)
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
                        "Responda apenas com o número da opção desejada.\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
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
                        "2️⃣ - Falar com Atendente Humano\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif message_body == "2": # Contas a Pagar
                    session["state"] = "contas_a_pagar_atendente"
                    enviar_mensagem(
                        remote_jid,
                        "💳 Você selecionou *Contas a Pagar*.\n\n"
                        "Um atendente do setor financeiro já foi notificado e logo irá atendê-lo por aqui!\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                else:
                    enviar_mensagem(
                        remote_jid, 
                        "Opção inválida. Digite *1* para Contas a Receber ou *2* para Contas a Pagar.\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )

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
                        "3️⃣ - Alterar Senha\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif message_body == "2": # Falar com Atendente
                    enviar_mensagem(
                        remote_jid,
                        "👤 Um atendente do financeiro foi notificado para lhe auxiliar com Contas a Receber.\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                else:
                    enviar_mensagem(
                        remote_jid, 
                        "Opção inválida. Digite *1* para Gestão Financeira ou *2* para Falar com Atendente.\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )

            # ==========================================
            # ETAPA 4: MENU DE ACESSO
            # ==========================================
            elif current_state == "menu_acesso":
                if message_body == "1": # Fazer Login
                    session["state"] = "login_aguardando_cnpj"
                    enviar_mensagem(
                        remote_jid, 
                        "Por favor, digite o seu **CNPJ ou CPF** (apenas números ou formatado):\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif message_body == "2": # Solicitar Senha
                    session["state"] = "solicitar_senha_aguardando_cnpj"
                    enviar_mensagem(
                        remote_jid, 
                        "Para solicitar sua senha provisória, digite o seu **CNPJ ou CPF**:\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif message_body == "3": # Alterar Senha
                    session["state"] = "alterar_senha_aguardando_cnpj"
                    enviar_mensagem(
                        remote_jid, 
                        "Para alterar sua senha, digite o seu **CNPJ ou CPF**:\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                else:
                    enviar_mensagem(
                        remote_jid, 
                        "Opção inválida. Escolha entre *1*, *2* ou *3*.\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )

            # ==========================================
            # FLUXO DE SOLICITAR SENHA (INTEGRADO AO ERP)
            # ==========================================
            elif current_state == "solicitar_senha_aguardando_cnpj":
                resultado = buscar_cliente_por_documento(message_body)
                
                if resultado["status"] == "erro_formato":
                    enviar_mensagem(
                        remote_jid,
                        "❌ *Formato inválido!*\n"
                        "Um CPF deve conter exatamente 11 dígitos e um CNPJ 14 dígitos.\n"
                        "Por favor, digite novamente o seu **CNPJ ou CPF**:\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif resultado["status"] == "nao_encontrado":
                    enviar_mensagem(
                        remote_jid,
                        "❌ *CNPJ/CPF não encontrado* em nossa base de dados.\n"
                        "Verifique os números digitados ou entre em contato com o nosso suporte financeiro.\n\n"
                        "*(Envie 0 ou menu para retornar ao menu principal)*"
                    )
                    session["state"] = "menu_principal"
                elif resultado["status"] == "encontrado":
                    email_completo = resultado["email"]
                    
                    if not email_completo:
                        # CORREÇÃO: Evita o limbo oferecendo as opções 1 ou 0
                        session["state"] = "aguardando_opcao_email_vazio"
                        enviar_mensagem(
                            remote_jid,
                            f"Encontramos o cadastro: *{resultado['nome']}*\n\n"
                            "⚠️ Não encontramos um e-mail cadastrado para o seu CNPJ/CPF no sistema.\n\n"
                            "Como deseja prosseguir?\n"
                            "1️⃣ - Falar com o Setor Financeiro (Atualizar cadastro)\n"
                            "0️⃣ - Voltar ao Menu Principal\n\n"
                            "*(Responda com 1 ou 0)*"
                        )
                        return {"status": "success"}
                        
                    # Salva dados temporários na sessão
                    session["dados"]["codcfo"] = resultado["codcfo"]
                    session["dados"]["nome"] = resultado["nome"]
                    session["dados"]["email"] = email_completo
                    
                    email_mascarado = mascarar_email(email_completo)
                    session["state"] = "solicitar_senha_confirmar_email"
                    
                    enviar_mensagem(
                        remote_jid,
                        f"Encontramos o cadastro: *{resultado['nome']}*\n\n"
                        f"O e-mail cadastrado para envio da senha é: *{email_mascarado}*\n\n"
                        "O e-mail está correto?\n"
                        "1️⃣ - Sim, enviar senha provisória para este e-mail\n"
                        "2️⃣ - Não, o e-mail está incorreto\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )

            # CORREÇÃO: Tratamento para o cliente sem e-mail não ficar no limbo
            elif current_state == "aguardando_opcao_email_vazio":
                if message_body == "1":
                    session["state"] = "menu_principal"
                    texto_pre_fabricado = (
                        "Olá, preciso cadastrar/atualizar o meu e-mail no sistema da Rondochassis "
                        "para conseguir solicitar a senha do robô WhatsApp."
                    )
                    link_financeiro = f"https://wa.me/556634211496?text={requests.utils.quote(texto_pre_fabricado)}"
                    enviar_mensagem(
                        remote_jid,
                        "Para atualizar seu e-mail e liberar o acesso, fale diretamente com o financeiro clicando no link abaixo:\n\n"
                        f"{link_financeiro}\n\n"
                        "💡 Após a atualização, envie *0* ou *menu* para voltar aqui e solicitar sua senha."
                    )
                elif message_body == "0":
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
                else:
                    enviar_mensagem(
                        remote_jid,
                        "Opção inválida. Digite *1* para falar com o financeiro ou *0* para retornar ao menu principal."
                    )

            elif current_state == "solicitar_senha_confirmar_email":
                if message_body == "1": # E-mail correto -> Gera e envia
                    codcfo = session["dados"].get("codcfo")
                    nome = session["dados"].get("nome")
                    email = session["dados"].get("email")
                    
                    nova_senha = gerar_senha_aleatoria()
                    
                    # Salva na tabela ROBOWHATS
                    salvar_ou_atualizar_senha_robo(codcfo, nome, email, nova_senha)
                    
                    # Dispara o e-mail
                    enviado = enviar_email_senha_provisoria(email, nome, nova_senha)
                    
                    email_mascarado = mascarar_email(email)
                    
                    if enviado:
                        session["state"] = "submenu_financeiro"
                        enviar_mensagem(
                            remote_jid,
                            f"✅ Uma senha provisória foi enviada com sucesso para o e-mail: *{email_mascarado}*.\n\n"
                            "Utilize-a para fazer seu login na opção 1 do menu anterior.\n\n"
                            "Retornando ao submenu financeiro."
                        )
                    else:
                        enviar_mensagem(
                            remote_jid,
                            "❌ Houve uma falha técnica ao disparar o e-mail. Por favor, tente novamente mais tarde ou contate o financeiro."
                        )
                        session["state"] = "menu_principal"
                        
                elif message_body == "2": # E-mail incorreto -> Mensagem pré-fabricada
                    session["state"] = "menu_principal"
                    texto_pre_fabricado = (
                        "Olá, preciso atualizar o meu e-mail de cadastro no sistema da Rondochassis "
                        "para conseguir receber a senha do robô WhatsApp."
                    )
                    link_financeiro = f"https://wa.me/556634211496?text={requests.utils.quote(texto_pre_fabricado)}"
                    
                    enviar_mensagem(
                        remote_jid,
                        "Entendido! Como o seu e-mail precisa ser atualizado, por favor clique no link abaixo "
                        "para falar diretamente com o nosso setor financeiro e solicitar a correção:\n\n"
                        f"{link_financeiro}\n\n"
                        "💡 Após a alteração pelo financeiro, volte aqui e solicite sua senha novamente."
                    )
                else:
                    enviar_mensagem(
                        remote_jid,
                        "Opção inválida. Digite *1* se o e-mail estiver correto ou *2* se estiver incorreto.\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )

            # ==========================================
            # FLUXO DE FAZER LOGIN
            # ==========================================
            elif current_state == "login_aguardando_cnpj":
                resultado = buscar_cliente_por_documento(message_body)
                
                if resultado["status"] == "erro_formato":
                    enviar_mensagem(
                        remote_jid,
                        "❌ *Formato inválido!* Digite corretamente o seu **CNPJ ou CPF**:\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif resultado["status"] == "nao_encontrado":
                    enviar_mensagem(
                        remote_jid,
                        "❌ *CNPJ/CPF não encontrado* em nossa base de dados.\n\n"
                        "*(Envie 0 ou menu para voltar)*"
                    )
                    session["state"] = "menu_principal"
                elif resultado["status"] == "encontrado":
                    session["dados"]["codcfo"] = resultado["codcfo"]
                    session["state"] = "login_aguardando_senha"
                    enviar_mensagem(
                        remote_jid,
                        "Por favor, digite a sua **Senha** (ou a provisória recebida por e-mail):\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )

            elif current_state == "login_aguardando_senha":
                codcfo = session["dados"].get("codcfo")
                senha_digitada = message_body
                
                # Valida na tabela ROBOWHATS
                login_sucesso = verificar_senha_robo(codcfo, senha_digitada)
                
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
                    enviar_mensagem(
                        remote_jid,
                        "❌ *Senha incorreta!* Se você esqueceu sua senha, solicite uma nova senha provisória no menu de acesso.\n\n"
                        "Retornando ao menu de acesso."
                    )

            # ==========================================
            # FLUXO DE ALTERAR SENHA
            # ==========================================
            elif current_state == "alterar_senha_aguardando_cnpj":
                resultado = buscar_cliente_por_documento(message_body)
                
                if resultado["status"] == "erro_formato":
                    enviar_mensagem(
                        remote_jid,
                        "❌ *Formato inválido!* Digite corretamente o seu **CNPJ ou CPF**:\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif resultado["status"] == "nao_encontrado":
                    enviar_mensagem(
                        remote_jid,
                        "❌ *CNPJ/CPF não encontrado* em nossa base de dados.\n\n"
                        "*(Envie 0 ou menu para voltar)*"
                    )
                    session["state"] = "menu_principal"
                elif resultado["status"] == "encontrado":
                    session["dados"]["codcfo"] = resultado["codcfo"]
                    session["state"] = "alterar_senha_aguardando_senha_atual"
                    enviar_mensagem(
                        remote_jid,
                        "Digite a sua **Senha Atual** (ou a provisória que recebeu por e-mail):\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )

            elif current_state == "alterar_senha_aguardando_senha_atual":
                codcfo = session["dados"].get("codcfo")
                senha_atual = message_body
                
                # Verifica se a senha atual confere
                if verificar_senha_robo(codcfo, senha_atual):
                    session["state"] = "alterar_senha_aguardando_senha_nova"
                    enviar_mensagem(
                        remote_jid,
                        "Digite a **Nova Senha** desejada:\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                else:
                    session["state"] = "menu_acesso"
                    enviar_mensagem(
                        remote_jid,
                        "❌ *Senha atual incorreta!* Se você esqueceu sua senha, solicite uma nova pelo menu de acesso.\n\n"
                        "Retornando ao menu de acesso."
                    )

            elif current_state == "alterar_senha_aguardando_senha_nova":
                codcfo = session["dados"].get("codcfo")
                nova_senha = message_body
                
                from service_bd import _obter_conexao_bd
                conn = _obter_conexao_bd()
                cursor = conn.cursor()
                cursor.execute("SELECT NOME, EMAIL FROM ROBOWHATS WHERE CODCFO = ?", (codcfo,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    nome, email = row
                    salvar_ou_atualizar_senha_robo(codcfo, nome, email, nova_senha)
                    
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
                        "*(O documento PDF será enviado em instantes)*\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                elif message_body == "2": # Solicitar Notas e Boletos
                    enviar_mensagem(
                        remote_jid,
                        "📄 Buscando suas *Notas Fiscais e Boletos* disponíveis...\n\n"
                        "*(Os arquivos serão enviados por aqui)*\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                else:
                    enviar_mensagem(
                        remote_jid, 
                        "Opção inválida no menu logado. Digite *1* ou *2*.\n\n"
                        "*(Envie 0 ou menu a qualquer momento para voltar)*"
                    )
                    
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Erro crítico no webhook: {e}")
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)