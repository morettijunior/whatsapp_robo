import os
import json
from pathlib import Path
from datetime import datetime
from boleto import gerar_pdf_boleto  # Importa o script de boletos
import logging

# =====================================================================
# CONFIGURAÇÕES DE AMBIENTE
# =====================================================================
DIRETORIO_BASE_NFE_PDF = r"\\SERVIDOR\tga\Nfe\PDF"
DIRETORIO_BASE_NFE_XML = r"\\SERVIDOR\tga\Nfe\XML"
DIRETORIO_BASE_NFSE = r"\\SERVIDOR\tga\NFS-e\XML"

def _obter_caminho_config_json():
    docs_path = Path.home() / "Documents" / "RondochassisBot"
    docs_path.mkdir(parents=True, exist_ok=True)
    return docs_path / "config_sistema.json"

def buscar_arquivos_pedido(pedido_selecionado, pasta_destino_temp="temp_docs"):
    """
    Busca e/ou gera todos os arquivos referentes ao pedido selecionado:
    - NFE: PDF e XML baseados na Chave de Acesso da tabela TNFE
    - NFS-e: PDF baseado no RPS (<RPS>-nfse.pdf) se anterior a 01/11/2026, 
             ou Recibo (<RECIBO>-nfse.pdf) se a partir de 01/11/2026.
    - BOLETO: PDFs gerados dinamicamente
    """
    arquivos_para_enviar = []
    
    # Cria uma pasta temporária local para agrupar os arquivos
    Path(pasta_destino_temp).mkdir(parents=True, exist_ok=True)
    
    # Carrega as configurações do sistema (incluindo o caminho personalizado da logo_banco)
    config_file = _obter_caminho_config_json()
    caminhos_config = {}
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                caminhos_config = json.load(f)
        except:
            pass
    
    # -----------------------------------------------------------------
    # 1. LOCALIZAR NF-E (PDF e XML baseados na CHAVE DE ACESSO)
    # -----------------------------------------------------------------
    chave_nfe = pedido_selecionado.get("CHAVE_NFE", "").strip()
    data_emissao = pedido_selecionado.get("DATA", "").strip() # Formato DD/MM/AAAA
    
    if chave_nfe and chave_nfe != "-":
        chaves_lista = [c.strip() for c in chave_nfe.replace(",", " ").split() if c.strip()]
        
        for chave in chaves_lista:
            anomes = _extrair_anomes(data_emissao, chave)
            
            # --- Busca PDF da NF-e ---
            pdf_encontrado = None
            if anomes:
                pdf_path = os.path.join(DIRETORIO_BASE_NFE_PDF, anomes, f"{chave}-nfe.pdf")
                if os.path.exists(pdf_path):
                    pdf_encontrado = pdf_path
            if not pdf_encontrado:
                pdf_encontrado = _encontrar_arquivo_por_nome(DIRETORIO_BASE_NFE_PDF, f"{chave}-nfe.pdf")
                
            if pdf_encontrado and pdf_encontrado not in arquivos_para_enviar:
                arquivos_para_enviar.append(pdf_encontrado)

            # --- Busca XML da NF-e ---
            xml_encontrado = None
            if anomes:
                xml_path_1 = os.path.join(DIRETORIO_BASE_NFE_XML, anomes, "NFe", f"{chave}-nfe.xml")
                xml_path_2 = os.path.join(DIRETORIO_BASE_NFE_XML, anomes, "NFE", f"{chave}-nfe.xml")
                if os.path.exists(xml_path_1):
                    xml_encontrado = xml_path_1
                elif os.path.exists(xml_path_2):
                    xml_encontrado = xml_path_2
            if not xml_encontrado:
                xml_encontrado = _encontrar_arquivo_por_nome(DIRETORIO_BASE_NFE_XML, f"{chave}-nfe.xml")
                
            if xml_encontrado and xml_encontrado not in arquivos_para_enviar:
                arquivos_para_enviar.append(xml_encontrado)

    # -----------------------------------------------------------------
    # 2. LOCALIZAR NFS-E (Tratamento para antes e depois de 01/11/2026)
    # -----------------------------------------------------------------
    recibo_nfse = pedido_selecionado.get("RECIBO_NFSE", "").strip()
    is_antigo = _verificar_data_anterior_nacional(data_emissao)

    if is_antigo:
        num_nfs_antiga = pedido_selecionado.get("NUMERO_NFS_MUNICIPAL", "").strip()
        
        if num_nfs_antiga and num_nfs_antiga != "-":
            nfse_path = os.path.join(DIRETORIO_BASE_NFSE, f"{num_nfs_antiga}-nfse.pdf")
            if os.path.exists(nfse_path) and nfse_path not in arquivos_para_enviar:
                arquivos_para_enviar.append(nfse_path)
            else:
                nfse_fallback = _encontrar_arquivo_por_nome(DIRETORIO_BASE_NFSE, f"{num_nfs_antiga}-nfse.pdf")
                if nfse_fallback and nfse_fallback not in arquivos_para_enviar:
                    arquivos_para_enviar.append(nfse_fallback)
    else:
        if recibo_nfse and recibo_nfse != "-":
            recibos_lista = [r.strip() for r in recibo_nfse.replace(",", " ").split() if r.strip()]
            for recibo in recibos_lista:
                nfse_path = os.path.join(DIRETORIO_BASE_NFSE, f"{recibo}-nfse.pdf")
                if os.path.exists(nfse_path) and nfse_path not in arquivos_para_enviar:
                    arquivos_para_enviar.append(nfse_path)
                else:
                    nfse_fallback = _encontrar_arquivo_por_nome(DIRETORIO_BASE_NFSE, f"{recibo}-nfse.pdf")
                    if nfse_fallback and nfse_fallback not in arquivos_para_enviar:
                        arquivos_para_enviar.append(nfse_fallback)

    # -----------------------------------------------------------------
    # 3. GERAR BOLETOS DO PEDIDO (Com suporte a logo configurada)
    # -----------------------------------------------------------------
    boletos_dados = pedido_selecionado.get("BOLETOS", [])
    if boletos_dados:
        caminhos_boletos = gerar_pdf_boleto(pedido_selecionado, pasta_destino_temp, caminhos_config=caminhos_config)
        if caminhos_boletos:
            for b in caminhos_boletos:
                if b not in arquivos_para_enviar:
                    arquivos_para_enviar.append(b)

    return arquivos_para_enviar

def _verificar_data_anterior_nacional(data_str):
    """Retorna True se a data do documento for anterior a 01/11/2026"""
    try:
        if data_str and "/" in data_str:
            dt = datetime.strptime(data_str.split()[0], "%d/%m/%Y")
            data_corte = datetime(2026, 11, 1)
            return dt < data_corte
    except:
        pass
    return False

def _extrair_anomes(data_str, chave):
    """Extrai o AnoMês (AAAAMM) a partir da data DD/MM/AAAA ou dos dígitos da chave de acesso"""
    try:
        if data_str and "/" in data_str:
            partes = data_str.split("/")
            if len(partes) == 3:
                _, mes, ano = partes
                return f"{ano}{mes}"
    except:
        pass
        
    try:
        if len(chave) >= 6:
            ano_2_digitos = chave[2:4]
            mes_2_digitos = chave[4:6]
            return f"20{ano_2_digitos}{mes_2_digitos}"
    except:
        pass
        
    return ""

def _encontrar_arquivo_por_nome(diretorio_base, nome_arquivo_alvo):
    """Função de segurança para localizar o arquivo exato caso a estrutura de pastas varie"""
    if not os.path.exists(diretorio_base):
        return None
        
    for pasta_atual, _, arquivos in os.walk(diretorio_base):
        for arquivo in arquivos:
            if arquivo.lower() == nome_arquivo_alvo.lower():
                return os.path.join(pasta_atual, arquivo)
    return None