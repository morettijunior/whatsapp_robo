import os
from pathlib import Path
from boleto import gerar_pdf_boleto  # Importa o script de boletos que você enviou

# =====================================================================
# CONFIGURAÇÕES DE AMBIENTE (Mude para o servidor quando for implantar)
# =====================================================================
# Para testes na máquina local, apontamos para pastas locais.
# Quando for para o servidor, basta alterar para o caminho de rede: r"\\SERVIDOR\TGA\Nfe"
DIRETORIO_BASE_NFE = r"\\SERVIDOR\TGA\Nfe"
DIRETORIO_BASE_NFSE = r"\\SERVIDOR\tga\NFS-e\XML"  # Ajuste conforme o caminho real da NFS-e

def buscar_arquivos_pedido(pedido_selecionado, pasta_destino_temp="temp_docs"):
    """
    Busca e/ou gera todos os arquivos referentes ao pedido selecionado:
    - NFE: PDF + XML (se houver)
    - NFS: PDF (série 005, através do recibo)
    - BOLETO: PDFs gerados pelo script de boleto
    Retorna uma lista com os caminhos absolutos dos arquivos prontos para envio.
    """
    arquivos_para_enviar = []
    
    # Cria uma pasta temporária local para agrupar os arquivos antes de enviar
    Path(pasta_destino_temp).mkdir(parents=True, exist_ok=True)
    
    # -----------------------------------------------------------------
    # 1. LOCALIZAR NF-E (PDF e XML)
    # -----------------------------------------------------------------
    # O pedido selecionado deve trazer a chave de acesso ou número da nota
    nota = pedido_selecionado.get("NOTA", "")
    if nota and nota != "-":
        # Nota pode vir separada por vírgula se houver mais de uma
        notas_lista = [n.strip() for n in nota.replace(",", " ").split() if n.strip()]
        
        for n_fiscal in notas_lista:
            # Varre as subpastas (AnoMes) dentro de C:\TGA\Nfe\PDF e XML
            pdf_encontrado = _encontrar_arquivo_por_padrao(os.path.join(DIRETORIO_BASE_NFE, "PDF"), f"*{n_fiscal}*.pdf")
            xml_encontrado = _encontrar_arquivo_por_padrao(os.path.join(DIRETORIO_BASE_NFE, "XML"), f"*{n_fiscal}*.xml")
            
            if pdf_encontrado:
                arquivos_para_enviar.append(pdf_encontrado)
            if xml_encontrado:
                arquivos_para_enviar.append(xml_encontrado)

    # -----------------------------------------------------------------
    # 2. LOCALIZAR NFS-E (Série 005 - Baseado no RECIBO)
    # -----------------------------------------------------------------
    recibo = pedido_selecionado.get("RECIBO", "")
    if recibo and recibo != "-":
        # Conforme alinhado, o PDF da NFS-e utiliza o formato <RECIBO>-nfse.pdf
        nome_arquivo_nfse = f"{recibo}-nfse.pdf"
        
        # Procura na pasta de NFS-e do servidor/local
        caminho_nfse = _encontrar_arquivo_por_padrao(DIRETORIO_BASE_NFSE, nome_arquivo_nfse)
        if caminho_nfse:
            arquivos_para_enviar.append(caminho_nfse)

    # -----------------------------------------------------------------
    # 3. GERAR BOLETOS DO PEDIDO
    # -----------------------------------------------------------------
    boletos_dados = pedido_selecionado.get("BOLETOS", [])
    if boletos_dados:
        # Utiliza a função do script boleto.py para gerar os PDFs dinamicamente
        caminhos_boletos = gerar_pdf_boleto(pedido_selecionado, pasta_destino_temp)
        if caminhos_boletos:
            arquivos_para_enviar.extend(caminhos_boletos)

    return arquivos_para_enviar

def _encontrar_arquivo_por_padrao(diretorio_base, padrao):
    """Função auxiliar para buscar arquivos recursivamente em subpastas (ex: AnoMes)"""
    if not os.path.exists(diretorio_base):
        return None
    
    for pasta_atual, _, arquivos in os.walk(diretorio_base):
        for arquivo in arquivos:
            if Path(arquivo).match(padrao):
                return os.path.join(pasta_atual, arquivo)
    return None