import os
import re
import json
import logging
from datetime import date, timedelta
from pathlib import Path


def _obter_config() -> dict:
    config_file = Path.home() / "Documents" / "RondochassisBot" / "config_sistema.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erro ao ler config_sistema.json no notas.py: {e}")
    return {}


def extrair_ano_mes(chave_acesso: str, data_emissao: str = "") -> str:
    """
    Extrai 'AAAAMM' (ex: '202611') a partir das posições 3..6 (AAMM) da chave de acesso de 44 dígitos,
    com fallback para a data de emissão do movimento.
    """
    digitos = re.sub(r"\D", "", str(chave_acesso or ""))
    if len(digitos) == 44:
        aamm = digitos[2:6]
        return f"20{aamm}"

    data_str = str(data_emissao or "").strip()
    if "/" in data_str:
        partes = data_str.split("/")
        if len(partes) == 3 and len(partes[2]) == 4:
            return f"{partes[2]}{partes[1].zfill(2)}"
    elif "-" in data_str:
        partes = data_str.split()[0].split("-")
        if len(partes) == 3 and len(partes[0]) == 4:
            return f"{partes[0]}{partes[1].zfill(2)}"

    return ""


def obter_pastas_ano_mes_90_dias(chave_acesso: str = "", data_emissao: str = "") -> list[str]:
    """
    Monta a lista ordenada (sem duplicatas) das pastas 'AAAAMM' dos últimos 90 dias
    (ex: 202611, 202610, 202609...), priorizando o mês da chave/emissão quando disponível.
    """
    candidatos = []

    ano_mes_chave = extrair_ano_mes(chave_acesso, data_emissao)
    if ano_mes_chave:
        candidatos.append(ano_mes_chave)

    hoje = date.today()
    for dias_atras in range(0, 96, 15):
        dt_ref = hoje - timedelta(days=dias_atras)
        pasta = f"{dt_ref.year}{dt_ref.month:02d}"
        if pasta not in candidatos:
            candidatos.append(pasta)

    dt_90 = hoje - timedelta(days=90)
    pasta_90 = f"{dt_90.year}{dt_90.month:02d}"
    if pasta_90 not in candidatos:
        candidatos.append(pasta_90)

    return candidatos


def _localizar_arquivo_direto(diretorio: Path, nome_arquivo: str, cache_dirs: dict) -> str | None:
    """
    Verifica diretamente se o arquivo existe via os.path.isfile (case-insensitive no Windows),
    sem listar o conteúdo da pasta na rede.
    """
    dir_str = str(diretorio)
    if dir_str not in cache_dirs:
        try:
            cache_dirs[dir_str] = os.path.isdir(dir_str)
        except OSError:
            cache_dirs[dir_str] = False

    if not cache_dirs[dir_str]:
        return None

    caminho_completo = os.path.join(dir_str, nome_arquivo)
    try:
        if os.path.isfile(caminho_completo):
            return caminho_completo
    except OSError as e:
        logging.error(f"Erro ao acessar {caminho_completo}: {e}")

    return None


def _buscar_nfe_nos_meses(
    base_dir: Path,
    nome_arquivo: str,
    pastas_ano_mes: list[str],
    cache_dirs: dict,
    subpasta_interna: str = ""
) -> str | None:
    """
    Procura o arquivo da NF-e em cada pasta 'AAAAMM' dos últimos 90 dias.
    """
    for ano_mes in pastas_ano_mes:
        dir_alvo = base_dir / ano_mes / subpasta_interna if subpasta_interna else base_dir / ano_mes
        encontrado = _localizar_arquivo_direto(dir_alvo, nome_arquivo, cache_dirs)
        if encontrado:
            return encontrado

    # Fallback na raiz caso o arquivo esteja fora das subpastas de mês
    dir_raiz = base_dir / subpasta_interna if subpasta_interna else base_dir
    return _localizar_arquivo_direto(dir_raiz, nome_arquivo, cache_dirs)


def buscar_arquivos_notas(dados_pedido: dict, caminhos_config: dict = None) -> dict:
    """
    Busca todos os arquivos de NF-e (XML e PDF nos meses dos últimos 90 dias)
    e NFS-e (PDF) vinculados ao pedido:
      - Série 'NFS' (até 31/10): {base_nfs_pdf}\{numeronota}-nfse.pdf
      - Série '005' (após 01/11): {base_nfs_pdf}\{recibo}-nfse.pdf
    """
    cfg = caminhos_config if caminhos_config else _obter_config()

    base_nfe_pdf = str(cfg.get("pasta_nfe_pdf") or r"\\Servidor\tga\Nfe\PDF").strip().rstrip("\\/")
    base_nfe_xml = str(cfg.get("pasta_nfe_xml") or r"\\Servidor\tga\Nfe\XML").strip().rstrip("\\/")
    base_nfs_pdf = str(cfg.get("pasta_nfs_pdf") or r"\\Servidor\tga\NFS-e\XML").strip().rstrip("\\/")

    encontrados = []
    nao_encontrados = []
    cache_dirs = {}

    # 1. NF-e (XML e PDF) buscando em todas as pastas AAAAMM dos últimos 90 dias
    lista_nfes = list(dados_pedido.get("CHAVES_NFE") or [])
    if not lista_nfes:
        chave_unica = str(dados_pedido.get("CHAVE_NFE") or "").strip()
        if chave_unica:
            lista_nfes.append({
                "chave": chave_unica,
                "numero": str(dados_pedido.get("NOTA") or "").strip(),
                "data": str(dados_pedido.get("DATA") or "").strip(),
            })

    chaves_processadas = set()
    for item_nfe in lista_nfes:
        chave = str(item_nfe.get("chave") or "").strip()
        if not chave or chave in chaves_processadas:
            continue
        chaves_processadas.add(chave)

        num_nota = str(item_nfe.get("numero") or "").strip()
        rotulo_nfe = f"NF-e nº {num_nota}" if num_nota and num_nota != "-" else f"NF-e ({chave[:10]}...)"
        data_ref = str(item_nfe.get("data") or dados_pedido.get("DATA") or "").strip()
        pastas_candidatas = obter_pastas_ano_mes_90_dias(chave, data_ref)

        # NF-e XML: {base_nfe_xml}\{AAAAMM}\NFe\{chave}-nfe.xml
        nome_xml = f"{chave}-nfe.xml"
        arq_xml = _buscar_nfe_nos_meses(
            Path(base_nfe_xml),
            nome_xml,
            pastas_candidatas,
            cache_dirs,
            subpasta_interna="NFe"
        )
        if arq_xml:
            encontrados.append({
                "tipo": "NF-e XML",
                "caminho": arq_xml,
                "filename": os.path.basename(arq_xml),
            })
        else:
            logging.warning(f"NF-e XML ({nome_xml}) não encontrada nas pastas: {pastas_candidatas}")
            nao_encontrados.append(f"{rotulo_nfe} (XML)")

        # NF-e PDF: {base_nfe_pdf}\{AAAAMM}\{chave}-nfe.pdf
        nome_pdf = f"{chave}-nfe.pdf"
        arq_pdf = _buscar_nfe_nos_meses(
            Path(base_nfe_pdf),
            nome_pdf,
            pastas_candidatas,
            cache_dirs,
            subpasta_interna=""
        )
        if arq_pdf:
            encontrados.append({
                "tipo": "NF-e PDF",
                "caminho": arq_pdf,
                "filename": os.path.basename(arq_pdf),
            })
        else:
            logging.warning(f"NF-e PDF ({nome_pdf}) não encontrada nas pastas: {pastas_candidatas}")
            nao_encontrados.append(f"{rotulo_nfe} (PDF)")

    # 2. NFS-e PDF (diferencia série 'NFS' municipal até 31/10 vs série '005' nacional após 01/11)
    lista_nfss = list(dados_pedido.get("RECIBOS_NFSE") or [])
    if not lista_nfss:
        recibo_unico = str(dados_pedido.get("RECIBO_NFSE") or "").strip()
        num_nfs_unico = str(dados_pedido.get("NUMERO_NFS_MUNICIPAL") or "").strip()
        serie_nfs_unica = str(dados_pedido.get("SERIE_NFSE") or "").strip().upper()
        if recibo_unico or (num_nfs_unico and num_nfs_unico != "-"):
            lista_nfss.append({
                "recibo": recibo_unico,
                "numero": num_nfs_unico,
                "serie": serie_nfs_unica,
            })

    nfss_processadas = set()
    dir_nfs = Path(base_nfs_pdf)

    for item_nfs in lista_nfss:
        recibo = str(item_nfs.get("recibo") or "").strip()
        num_nfs = str(item_nfs.get("numero") or "").strip()
        serie_nfs = str(item_nfs.get("serie") or "").strip().upper()

        chave_dedup = (serie_nfs, recibo, num_nfs)
        if chave_dedup in nfss_processadas:
            continue
        nfss_processadas.add(chave_dedup)

        rotulo_nfs = (
            f"NFS-e nº {num_nfs}"
            if num_nfs and num_nfs != "-"
            else f"NFS-e ({recibo[:10]}...)"
        )

        # Caso 1: Emissão Municipal antiga (Série 'NFS', até 31/10) -> {numeronota}-nfse.pdf
        if serie_nfs == "NFS":
            if not num_nfs or num_nfs == "-":
                nao_encontrados.append("NFS-e (PDF - número da nota não localizado no cadastro)")
                continue

            nome_nfs_pdf = f"{num_nfs}-nfse.pdf"
            arq_nfs = _localizar_arquivo_direto(dir_nfs, nome_nfs_pdf, cache_dirs)
            if arq_nfs:
                encontrados.append({
                    "tipo": "NFS-e PDF",
                    "caminho": arq_nfs,
                    "filename": os.path.basename(arq_nfs),
                })
            else:
                logging.warning(f"NFS-e Municipal PDF não encontrada: {dir_nfs / nome_nfs_pdf}")
                nao_encontrados.append(f"{rotulo_nfs} (PDF)")

        # Caso 2: Emissor Nacional (Série '005', a partir de 01/11) -> {recibo}-nfse.pdf
        elif serie_nfs == "005":
            if not recibo:
                nao_encontrados.append(f"{rotulo_nfs} (PDF - recibo/chave não localizado no cadastro)")
                continue

            nome_nfs_pdf = f"{recibo}-nfse.pdf"
            arq_nfs = _localizar_arquivo_direto(dir_nfs, nome_nfs_pdf, cache_dirs)
            if arq_nfs:
                encontrados.append({
                    "tipo": "NFS-e PDF",
                    "caminho": arq_nfs,
                    "filename": os.path.basename(arq_nfs),
                })
            else:
                logging.warning(f"NFS-e Nacional PDF não encontrada: {dir_nfs / nome_nfs_pdf}")
                nao_encontrados.append(f"{rotulo_nfs} (PDF)")

        # Caso 3: Fallback quando a série não veio identificada
        else:
            arq_nfs = None
            if recibo:
                arq_nfs = _localizar_arquivo_direto(dir_nfs, f"{recibo}-nfse.pdf", cache_dirs)
            if not arq_nfs and num_nfs and num_nfs != "-":
                arq_nfs = _localizar_arquivo_direto(dir_nfs, f"{num_nfs}-nfse.pdf", cache_dirs)

            if arq_nfs:
                encontrados.append({
                    "tipo": "NFS-e PDF",
                    "caminho": arq_nfs,
                    "filename": os.path.basename(arq_nfs),
                })
            else:
                nao_encontrados.append(f"{rotulo_nfs} (PDF)")

    return {
        "encontrados": encontrados,
        "nao_encontrados": nao_encontrados,
    }