import fdb
import json
from pathlib import Path
import logging


def _obter_caminho_config_json():
    docs_path = Path.home() / "Documents" / "RondochassisBot"
    docs_path.mkdir(parents=True, exist_ok=True)
    return docs_path / "config_sistema.json"


def _obter_conexao_bd():
    caminho_bd = "Servidor:c:/tga/Dados/TGA.FDB"
    config_file = _obter_caminho_config_json()
    
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                dados = json.load(f)
                caminho_bd = dados.get("db_dsn", caminho_bd)
        except Exception:
            pass
            
    return fdb.connect(
        dsn=caminho_bd,
        user="SYSDBA",
        password="masterkey",
        charset="ISO8859_1",
    )


def _limpar_texto_bd(valor):
    """Converte strings, bytes ou campos BLOB do Firebird com segurança."""
    if not valor:
        return ""
    if hasattr(valor, "read"):
        valor = valor.read()
    if isinstance(valor, bytes):
        try:
            valor = valor.decode("iso-8859-1")
        except Exception:
            valor = valor.decode("utf-8", errors="ignore")
    texto = str(valor).strip()
    return "" if texto.upper() == "NONE" else texto


def validar_e_formatar_documento(doc_texto):
    digitos = "".join(filter(str.isdigit, doc_texto))
    if len(digitos) == 11:
        formatado = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
        return {"valido": True, "tipo": "CPF", "documento": formatado}
    elif len(digitos) == 14:
        formatado = f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
        return {"valido": True, "tipo": "CNPJ", "documento": formatado}
    else:
        return {"valido": False, "tipo": None, "documento": doc_texto}


def extrair_primeiro_email(email_bruto):
    if not email_bruto:
        return ""
    if isinstance(email_bruto, bytes):
        try:
            email_bruto = email_bruto.decode("iso-8859-1")
        except Exception:
            email_bruto = email_bruto.decode("utf-8", errors="ignore")
    return str(email_bruto).split(";")[0].strip()


def buscar_cliente_por_documento(doc_digitado):
    """
    Busca cliente na FCFO pelo CPF/CNPJ considerando apenas TIPO IN ('C', 'A') (Cliente ou Ambas):
      - Se não existir: status = 'nao_encontrado'
      - Se houver ativo (ATIVO = 'T') e inativo (ATIVO = 'F'): prioriza e retorna o ativo ('encontrado')
      - Se houver apenas inativo (ATIVO = 'F'): status = 'inativo'
    """
    validacao = validar_e_formatar_documento(doc_digitado)
    if not validacao["valido"]:
        return {"status": "erro_formato", "mensagem": "Formato inválido."}
        
    doc_formatado = validacao["documento"]
    digitos_puros = "".join(filter(str.isdigit, doc_digitado))
    
    conn = _obter_conexao_bd()
    cursor = conn.cursor()
    sql = """
        SELECT CODCFO, NOME, EMAIL, ATIVO
        FROM FCFO
        WHERE (TRIM(CGCCFO) = ? OR TRIM(CGCCFO) = ?)
          AND UPPER(TRIM(COALESCE(TIPO, ''))) IN ('C', 'A')
        ORDER BY
            CASE WHEN UPPER(TRIM(COALESCE(ATIVO, ''))) = 'T' THEN 0 ELSE 1 END,
            CODCFO DESC
    """
    
    try:
        cursor.execute(sql, (doc_formatado, digitos_puros))
        rows = cursor.fetchall()
        if not rows:
            return {"status": "nao_encontrado", "mensagem": "Não encontrado."}

        ativos = []
        inativos = []
        for r in rows:
            codcfo, nome, email_bruto, ativo_flag = r
            flag_limpa = str(ativo_flag).strip().upper() if ativo_flag else ""
            registro = {
                "codcfo": str(codcfo).strip(),
                "nome": str(nome).strip() if nome else "",
                "email": extrair_primeiro_email(email_bruto),
                "ativo": flag_limpa,
            }
            if flag_limpa == "T":
                ativos.append(registro)
            else:
                inativos.append(registro)

        if ativos:
            escolhido = ativos[0]
            return {
                "status": "encontrado",
                "codcfo": escolhido["codcfo"],
                "nome": escolhido["nome"],
                "email": escolhido["email"],
                "codcfos_ativos": [a["codcfo"] for a in ativos],
            }

        escolhido_inativo = inativos[0]
        return {
            "status": "inativo",
            "codcfo": escolhido_inativo["codcfo"],
            "nome": escolhido_inativo["nome"],
            "email": escolhido_inativo["email"],
            "mensagem": "Cadastro inativo. Consulte o setor financeiro.",
        }

    except Exception as e:
        logging.error(f"Erro ao buscar cliente: {e}")
        return {"status": "erro_bd", "mensagem": str(e)}
    finally:
        conn.close()

def _obter_codcfos_relacionados_ativos(cursor, codcfo_limpo: str) -> list[str]:
    """Retorna todos os CODCFO ativos (TIPO 'C' ou 'A') com o mesmo CGCCFO do cliente informado."""
    cursor.execute("SELECT TRIM(CGCCFO) FROM FCFO WHERE TRIM(CODCFO) = ?", (codcfo_limpo,))
    row_doc = cursor.fetchone()
    if not row_doc or not row_doc[0]:
        return [codcfo_limpo]

    doc_ref = str(row_doc[0]).strip()
    digitos_ref = "".join(filter(str.isdigit, doc_ref))
    cursor.execute(
        """
        SELECT TRIM(CODCFO)
        FROM FCFO
        WHERE (TRIM(CGCCFO) = ? OR TRIM(CGCCFO) = ?)
          AND UPPER(TRIM(COALESCE(TIPO, ''))) IN ('C', 'A')
          AND UPPER(TRIM(COALESCE(ATIVO, ''))) = 'T'
        ORDER BY CODCFO DESC
        """,
        (doc_ref, digitos_ref),
    )
    lista = [str(r[0]).strip() for r in cursor.fetchall() if r and r[0]]
    return lista if lista else [codcfo_limpo]

def salvar_ou_atualizar_senha_robo(codcfo, nome, email, senha_plana):
    conn = _obter_conexao_bd()
    cursor = conn.cursor()
    cursor.execute("SELECT CODCFO FROM ROBOWHATS WHERE CODCFO = ?", (codcfo,))
    existe = cursor.fetchone()
    try:
        if existe:
            cursor.execute("UPDATE ROBOWHATS SET NOME = ?, EMAIL = ?, SENHA = ? WHERE CODCFO = ?", (nome, email, senha_plana, codcfo))
        else:
            cursor.execute("INSERT INTO ROBOWHATS (CODCFO, NOME, EMAIL, SENHA) VALUES (?, ?, ?, ?)", (codcfo, nome, email, senha_plana))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Erro ao salvar senha: {e}")
        return False
    finally:
        conn.close()


def verificar_senha_robo(codcfo, senha_digitada):
    senha_master_configada = "260880"
    config_file = _obter_caminho_config_json()
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                dados = json.load(f)
                senha_master_configada = dados.get("senha_master", "260880")
        except Exception:
            pass

    if senha_digitada.strip() == str(senha_master_configada).strip():
        return True
        
    conn = _obter_conexao_bd()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT SENHA FROM ROBOWHATS WHERE CODCFO = ?", (codcfo,))
        row = cursor.fetchone()
        if row:
            return str(row[0]).strip() == senha_digitada.strip()
        return False
    except Exception as e:
        logging.error(f"Erro ao verificar senha: {e}")
        return False
    finally:
        conn.close()


def _carregar_dados_fcfo(cursor, codcfo_limpo, item):
    """Carrega dados cadastrais e de endereço da FCFO para o item"""
    query_fcfo = """
        SELECT NOME, EMAIL, FAX, CGCCFO, 
               RUA, NUMERO, BAIRRO, CIDADE, CODETD, CEP, 
               RUAPGTO, NUMEROPGTO, BAIRROPGTO, CIDADEPGTO, CODETDPGTO, CEPPGTO 
        FROM FCFO 
        WHERE CODCFO = ?
    """
    cursor.execute(query_fcfo, (codcfo_limpo,))
    cliente = cursor.fetchone()
    if cliente:
        item["CLIENTE_NOME"] = cliente[0].strip() if cliente[0] else "CLIENTE NÃO IDENTIFICADO"
        item["EMAIL"] = cliente[1].strip() if cliente[1] else ""
        item["WHATSAPP"] = cliente[2].strip() if cliente[2] else ""
        item["CLIENTE_DOC"] = cliente[3].strip() if cliente[3] else ""
        item["CLIENTE_RUA"] = cliente[4].strip() if cliente[4] else ""
        item["CLIENTE_NUMERO"] = cliente[5].strip() if cliente[5] else ""
        item["CLIENTE_BAIRRO"] = cliente[6].strip() if cliente[6] else ""
        item["CLIENTE_CIDADE"] = cliente[7].strip() if cliente[7] else ""
        item["CLIENTE_ESTADO"] = cliente[8].strip() if cliente[8] else ""
        item["CLIENTE_CEP"] = cliente[9].strip() if cliente[9] else ""
        item["CLIENTE_RUAPGTO"] = cliente[10].strip() if cliente[10] else ""
        item["CLIENTE_NUMEROPGTO"] = cliente[11].strip() if cliente[11] else ""
        item["CLIENTE_BAIRROPGTO"] = cliente[12].strip() if cliente[12] else ""
        item["CLIENTE_CIDADEPGTO"] = cliente[13].strip() if cliente[13] else ""
        item["CLIENTE_ESTADOPGTO"] = cliente[14].strip() if cliente[14] else ""
        item["CLIENTE_CEPPGTO"] = cliente[15].strip() if cliente[15] else ""


def _formatar_data_bd(valor_dt) -> str:
    if not valor_dt:
        return ""
    partes = str(valor_dt).split()[0].split("-")
    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return ""


# -------------------------------------------------------------------------
# 1. BLOCO DE PEDIDOS COMUNS
# -------------------------------------------------------------------------
def _consultar_pedidos_comuns(cursor, codcfo_limpo):
    sql_comum = """
        SELECT 
            f.IDMOV,
            f.NUMERODOCUMENTO,
            f.DATAEMISSAO,
            f.DATAVENCIMENTO,
            f.VALORORIGINAL,
            f.STATUSLAN,
            f.PARCELA,
            t.NUMEROMOV,
            t.DATAEMISSAO,
            t.VALORLIQUIDO,
            t.OB_NUMEROSERIE,
            t.IDMOVRELAC,
            t.SERIE,
            t.CHAVEACESSO,
            tnfe.CHAVEACESSO,
            nfs.NUMERONFSE,
            nfs.RECIBO,
            ev.NUMEROMOV,
            ev.OB_NUMEROSERIE,
            ev.IDMOVRELAC,
            ev.SERIE,
            ev.CHAVEACESSO,
            tnfe_ev.CHAVEACESSO,
            os.NUMEROMOV,
            f.CODBARRABOLETO,
            f.LINHADIGITAVELBOLETO,
            f.QRCODEPIX,
            f.BOL_NUMERO,
            f.HISTORICO,
            mov_nfs.NUMEROMOV,
            mov_nfs.SERIE,
            nfs_relac.NUMERONFSE,
            nfs_relac.RECIBO,
            mov_nfe.NUMEROMOV,
            tnfe_relac.CHAVEACESSO,
            mov_nfe.CHAVEACESSO
        FROM FLAN f
        LEFT JOIN TMOV t ON f.IDMOV = t.IDMOV
        LEFT JOIN TNFE tnfe ON tnfe.IDMOV = t.IDMOV
        LEFT JOIN TNFEMUNICIPAL nfs ON f.IDMOV = nfs.IDMOV
        LEFT JOIN TMOV ev ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) IN ('005', 'NFS', '1') THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOV
                ELSE t.IDMOV
            END = ev.IDMOV
        )
        LEFT JOIN TNFE tnfe_ev ON tnfe_ev.IDMOV = ev.IDMOV
        LEFT JOIN TMOV mov_nfs ON mov_nfs.IDMOVRELAC = t.IDMOV AND UPPER(TRIM(mov_nfs.SERIE)) IN ('005', 'NFS')
        LEFT JOIN TNFEMUNICIPAL nfs_relac ON nfs_relac.IDMOV = mov_nfs.IDMOV
        LEFT JOIN TMOV mov_nfe ON mov_nfe.IDMOVRELAC = t.IDMOV AND UPPER(TRIM(mov_nfe.SERIE)) = '1'
        LEFT JOIN TNFE tnfe_relac ON tnfe_relac.IDMOV = mov_nfe.IDMOV
        LEFT JOIN TMOV os ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) IN ('005', 'NFS', '1') THEN ev.IDMOVRELAC
                ELSE NULL
            END = os.IDMOV
        )
        WHERE f.CODCFO = ?
          AND f.PAGREC = 'R'
          AND f.STATUSLAN IN ('A', 'B')
          AND f.DATAEMISSAO >= CURRENT_DATE - 90
          AND f.CODTDO IN ('DP', 'BO', 'NF')
          AND f.IDMOV IS NOT NULL
        ORDER BY f.DATAEMISSAO ASC, f.PARCELA ASC
    """
    
    cursor.execute(sql_comum, (codcfo_limpo,))
    linhas = cursor.fetchall()
    lancamentos = {}
    
    for row in linhas:
        (
            id_mov, num_doc, dt_emissao_flan, dt_venc, val_orig, status_lan, parcela,
            num_mov, dt_emissao_tmov, valor_liq, placa_tmov, id_mov_relac, serie, chave_tmov, tnfe_chave,
            nfs_numfse, recibo_nfs,
            ev_num_mov, ev_placa, ev_relac, ev_serie, ev_chave, tnfe_ev_chave,
            os_num_mov, cod_barras, linha_dig, pix, bol_num, historico_flan,
            mov_nfs_num, mov_nfs_serie, nfs_relac_numfse, nfs_relac_recibo,
            mov_nfe_num, tnfe_relac_chave, mov_nfe_chave
        ) = row
        
        if not id_mov:
            continue
            
        if id_mov not in lancamentos:
            serie_limpa = str(serie).strip().upper() if serie else ""
            ev_serie_limpa = str(ev_serie).strip().upper() if ev_serie else ""
            mov_nfs_serie_limpa = str(mov_nfs_serie).strip().upper() if mov_nfs_serie else ""
            
            placa = "-"
            if placa_tmov and str(placa_tmov).strip() and str(placa_tmov).strip().upper() != "NONE":
                placa = str(placa_tmov).strip()
            elif ev_placa and str(ev_placa).strip() and str(ev_placa).strip().upper() != "NONE":
                placa = str(ev_placa).strip()

            serie_nfs = ""
            if serie_limpa in ("005", "NFS"):
                serie_nfs = serie_limpa
            elif mov_nfs_serie_limpa in ("005", "NFS"):
                serie_nfs = mov_nfs_serie_limpa

            nfs_bruto = nfs_numfse or nfs_relac_numfse
            num_nfs_municipal_val = ""
            if nfs_bruto and str(nfs_bruto).strip() and str(nfs_bruto).strip().upper() != "NONE":
                num_nfs_municipal_val = str(nfs_bruto).strip().lstrip("0")
            elif serie_limpa in ("005", "NFS") and num_mov:
                num_nfs_municipal_val = str(num_mov).strip().lstrip("0")
            elif mov_nfs_num:
                num_nfs_municipal_val = str(mov_nfs_num).strip().lstrip("0")

            recibo_bruto = recibo_nfs or nfs_relac_recibo
            recibo_val = str(recibo_bruto).strip() if recibo_bruto and str(recibo_bruto).strip().upper() != "NONE" else ""

            numero_nfe = ""
            if serie_limpa == "1":
                numero_nfe = str(num_mov).strip().lstrip("0") if num_mov else ""
            elif ev_serie_limpa == "1":
                numero_nfe = str(ev_num_mov).strip().lstrip("0") if ev_num_mov else ""
            elif mov_nfe_num:
                numero_nfe = str(mov_nfe_num).strip().lstrip("0")

            numero_nota_fiscal = ""
            if numero_nfe:
                numero_nota_fiscal = numero_nfe
            elif serie_limpa in ("005", "NFS") or num_nfs_municipal_val:
                numero_nota_fiscal = num_nfs_municipal_val
            elif not serie_limpa or serie_limpa == "EV":
                if num_mov and serie_limpa not in ("005", "NFS"):
                    numero_nota_fiscal = str(num_mov).strip().lstrip("0")

            chave_nfe_val = (
                str(tnfe_chave).strip() if tnfe_chave and str(tnfe_chave).strip() != "" else
                str(tnfe_relac_chave).strip() if tnfe_relac_chave and str(tnfe_relac_chave).strip() != "" else
                str(tnfe_ev_chave).strip() if tnfe_ev_chave and str(tnfe_ev_chave).strip() != "" else
                str(chave_tmov).strip() if chave_tmov and str(chave_tmov).strip() != "" else
                str(mov_nfe_chave).strip() if mov_nfe_chave and str(mov_nfe_chave).strip() != "" else
                str(ev_chave).strip() if ev_chave and str(ev_chave).strip() != "" else ""
            )

            num_pedido = ""
            if ev_num_mov and ev_serie_limpa not in ("1", "005", "NFS"):
                num_pedido = str(ev_num_mov).strip().lstrip("0")
            elif num_mov and serie_limpa not in ("1", "005", "NFS"):
                num_pedido = str(num_mov).strip().lstrip("0")
            
            if not num_pedido and num_doc:
                num_pedido = str(num_doc).strip().lstrip("0")

            num_os = ""
            if os_num_mov:
                num_os = str(os_num_mov).strip().lstrip("0")

            data_str = _formatar_data_bd(dt_emissao_tmov) or _formatar_data_bd(dt_emissao_flan)
            valor_total = float(valor_liq) if valor_liq else float(val_orig or 0)

            chaves_nfe_lista = []
            if chave_nfe_val:
                chaves_nfe_lista.append({
                    "chave": chave_nfe_val,
                    "numero": numero_nfe or numero_nota_fiscal,
                    "data": data_str,
                })

            recibos_nfse_lista = []
            if serie_nfs or recibo_val or num_nfs_municipal_val:
                num_ref_nfs = num_nfs_municipal_val or (numero_nota_fiscal if serie_nfs in ("005", "NFS") else "")
                if recibo_val or num_ref_nfs:
                    recibos_nfse_lista.append({
                        "recibo": recibo_val,
                        "numero": num_ref_nfs,
                        "serie": serie_nfs,
                    })

            lancamentos[id_mov] = {
                "DATA": data_str,
                "OS": num_os,
                "PEDIDO": num_pedido,
                "NUMERO_PEDIDO": num_pedido,
                "PLACA": placa,
                "NOTA": numero_nota_fiscal,
                "CHAVE_NFE": chave_nfe_val,
                "RECIBO_NFSE": recibo_val,
                "NUMERO_NFS_MUNICIPAL": num_nfs_municipal_val,
                "SERIE_NFSE": serie_nfs,
                "CHAVES_NFE": chaves_nfe_lista,
                "RECIBOS_NFSE": recibos_nfse_lista,
                "VALOR_TOTAL": valor_total,
                "PARCELAS": [],
                "BOLETOS": []
            }
            
            _carregar_dados_fcfo(cursor, codcfo_limpo, lancamentos[id_mov])
        
        venc_parc_str = _formatar_data_bd(dt_venc)
        val_parcela = float(val_orig) if val_orig else 0.0
        p_num = parcela if parcela else 1

        if not any(p["PARCELA"] == p_num for p in lancamentos[id_mov]["PARCELAS"]):
            lancamentos[id_mov]["PARCELAS"].append({
                "PARCELA": p_num,
                "VENCIMENTO": venc_parc_str,
                "VALOR": val_parcela,
                "STATUS": "BAIXADO" if str(status_lan).strip().upper() == "B" else "ABERTO"
            })

            lancamentos[id_mov]["BOLETOS"].append({
                "PARCELA": p_num,
                "NUMERO_DOCUMENTO": str(num_doc).strip() if num_doc else "DOC",
                "VENCIMENTO": venc_parc_str,
                "VALOR": val_parcela,
                "BOL_NUMERO": _limpar_texto_bd(bol_num),
                "CODBARRABOLETO": _limpar_texto_bd(cod_barras),
                "LINHADIGITAVELBOLETO": _limpar_texto_bd(linha_dig),
                "QRCODEPIX": _limpar_texto_bd(pix),
                "DATA_EMISSAO": lancamentos[id_mov]["DATA"],
                "HISTORICO": _limpar_texto_bd(historico_flan),
            })

    return list(lancamentos.values())


# -------------------------------------------------------------------------
# 2. BLOCO DE PEDIDOS AGRUPADOS
# -------------------------------------------------------------------------
def _consultar_pedidos_agrupados(cursor, codcfo_limpo):
    sql_agrupado = """
        SELECT 
            f.IDLAN,
            f.NUMERODOCUMENTO,
            f.DATAEMISSAO,
            f.DATAVENCIMENTO,
            f.VALORORIGINAL,
            f.STATUSLAN,
            f.PARCELA,
            f.IDFATLAN,
            COALESCE(orig.IDMOV, orig_via_ponte.IDMOV) AS IDMOV_ORIGEM,
            t.NUMEROMOV,
            t.DATAEMISSAO,
            t.VALORLIQUIDO,
            t.OB_NUMEROSERIE,
            t.SERIE,
            t.CHAVEACESSO,
            tnfe.CHAVEACESSO,
            nfs.NUMERONFSE,
            nfs.RECIBO,
            ev.NUMEROMOV,
            ev.OB_NUMEROSERIE,
            ev.SERIE,
            ev.CHAVEACESSO,
            tnfe_ev.CHAVEACESSO,
            nfs_ev.NUMERONFSE,
            nfs_ev.RECIBO,
            os.NUMEROMOV,
            f.CODBARRABOLETO,
            f.LINHADIGITAVELBOLETO,
            f.QRCODEPIX,
            f.BOL_NUMERO,
            f.HISTORICO,
            mov_nfe_ev.NUMEROMOV,
            mov_nfe_ev.DATAEMISSAO,
            tnfe_filho.CHAVEACESSO,
            mov_nfe_ev.CHAVEACESSO,
            mov_nfs_ev.NUMEROMOV,
            mov_nfs_ev.SERIE,
            nfs_filho.NUMERONFSE,
            nfs_filho.RECIBO
        FROM FLAN f
        LEFT JOIN FLAN orig ON orig.IDFAT = f.IDFATLAN AND orig.IDMOV IS NOT NULL
        LEFT JOIN FLAN ponte ON ponte.IDFAT = f.IDFATLAN AND ponte.IDMOV IS NULL
        LEFT JOIN FLAN orig_via_ponte ON orig_via_ponte.IDFAT = ponte.IDFATLAN AND orig_via_ponte.IDMOV IS NOT NULL
        
        LEFT JOIN TMOV t ON t.IDMOV = COALESCE(orig.IDMOV, orig_via_ponte.IDMOV)
        LEFT JOIN TNFE tnfe ON tnfe.IDMOV = t.IDMOV
        LEFT JOIN TNFEMUNICIPAL nfs ON nfs.IDMOV = t.IDMOV
        LEFT JOIN TMOV ev ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) IN ('005', 'NFS', '1') THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOV
                ELSE t.IDMOV
            END = ev.IDMOV
        )
        LEFT JOIN TNFE tnfe_ev ON tnfe_ev.IDMOV = ev.IDMOV
        LEFT JOIN TNFEMUNICIPAL nfs_ev ON nfs_ev.IDMOV = ev.IDMOV
        LEFT JOIN TMOV mov_nfe_ev ON mov_nfe_ev.IDMOVRELAC = ev.IDMOV AND UPPER(TRIM(mov_nfe_ev.SERIE)) = '1'
        LEFT JOIN TNFE tnfe_filho ON tnfe_filho.IDMOV = mov_nfe_ev.IDMOV
        LEFT JOIN TMOV mov_nfs_ev ON mov_nfs_ev.IDMOVRELAC = ev.IDMOV AND UPPER(TRIM(mov_nfs_ev.SERIE)) IN ('005', 'NFS')
        LEFT JOIN TNFEMUNICIPAL nfs_filho ON nfs_filho.IDMOV = mov_nfs_ev.IDMOV
        LEFT JOIN TMOV os ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) IN ('005', 'NFS', '1') THEN ev.IDMOVRELAC
                ELSE NULL
            END = os.IDMOV
        )
        WHERE f.CODCFO = ?
          AND f.PAGREC = 'R'
          AND f.STATUSLAN IN ('A', 'B')
          AND f.DATAEMISSAO >= CURRENT_DATE - 90
          AND f.CODTDO IN ('DP', 'BO', 'NF')
          AND f.IDMOV IS NULL
          AND (orig.IDMOV IS NOT NULL OR orig_via_ponte.IDMOV IS NOT NULL)
        ORDER BY f.DATAEMISSAO ASC, f.PARCELA ASC
    """
    
    cursor.execute(sql_agrupado, (codcfo_limpo,))
    linhas = cursor.fetchall()
    lancamentos = {}
    ids_lan_ja_processados = set()
    
    contexto_fatura = {}
    for row in linhas:
        idfatlan = row[7]
        os_val = row[25]
        t_num = row[9]
        t_serie = str(row[13]).strip().upper() if row[13] else ""
        if idfatlan:
            if os_val and not contexto_fatura.get(f"{idfatlan}_os"):
                contexto_fatura[f"{idfatlan}_os"] = str(os_val).strip().lstrip("0")
            if t_num and t_serie not in ("1", "005", "NFS") and not contexto_fatura.get(f"{idfatlan}_ped"):
                contexto_fatura[f"{idfatlan}_ped"] = str(t_num).strip().lstrip("0")

    for row in linhas:
        (
            id_lan, num_doc, dt_emissao_flan, dt_venc, val_orig, status_lan, parcela,
            idfatlan, id_mov_origem,
            num_mov, dt_emissao_tmov, valor_liq, placa_tmov, serie, chave_tmov, tnfe_chave,
            nfs_numfse, recibo_nfs,
            ev_num_mov, ev_placa, ev_serie, ev_chave, tnfe_ev_chave, ev_nfs_numfse, ev_recibo_nfs,
            os_num_mov, cod_barras, linha_dig, pix, bol_num, historico_flan,
            mov_nfe_ev_num, mov_nfe_ev_dt, tnfe_filho_chave, mov_nfe_ev_chave,
            mov_nfs_ev_num, mov_nfs_ev_serie, nfs_filho_numfse, nfs_filho_recibo
        ) = row
        
        if not idfatlan:
            continue
            
        chave_agrupamento = f"AGR_{idfatlan}"
        serie_limpa = str(serie).strip().upper() if serie else ""
        ev_serie_limpa = str(ev_serie).strip().upper() if ev_serie else ""
        mov_nfs_ev_serie_limpa = str(mov_nfs_ev_serie).strip().upper() if mov_nfs_ev_serie else ""
        
        if chave_agrupamento not in lancamentos:
            placa = "-"
            if ev_placa and str(ev_placa).strip() and str(ev_placa).strip().upper() != "NONE":
                placa = str(ev_placa).strip()
            elif placa_tmov and str(placa_tmov).strip() and str(placa_tmov).strip().upper() != "NONE":
                placa = str(placa_tmov).strip()

            num_pedido = ""
            if ev_num_mov and ev_serie_limpa not in ("1", "005", "NFS"):
                num_pedido = str(ev_num_mov).strip().lstrip("0")
            elif num_mov and serie_limpa not in ("1", "005", "NFS"):
                num_pedido = str(num_mov).strip().lstrip("0")
            
            if not num_pedido and num_doc:
                num_pedido = str(num_doc).split('/')[0].strip().lstrip("0")
            
            if not num_pedido and idfatlan:
                num_pedido = contexto_fatura.get(f"{idfatlan}_ped", "")

            num_os = ""
            if os_num_mov:
                num_os = str(os_num_mov).strip().lstrip("0")
            elif idfatlan:
                num_os = contexto_fatura.get(f"{idfatlan}_os", "")

            data_str = _formatar_data_bd(dt_emissao_tmov) or _formatar_data_bd(dt_emissao_flan)

            lancamentos[chave_agrupamento] = {
                "DATA": data_str,
                "OS": num_os,
                "PEDIDO": num_pedido,
                "NUMERO_PEDIDO": num_pedido,
                "PLACA": placa,
                "NFES_NUMS": [],
                "NFSS_NUMS": [],
                "CHAVE_NFE": "",
                "RECIBO_NFSE": "",
                "NUMERO_NFS_MUNICIPAL": "",
                "SERIE_NFSE": "",
                "CHAVES_NFE": [],
                "RECIBOS_NFSE": [],
                "NOTA": "",
                "VALOR_TOTAL": 0.0,
                "PARCELAS": [],
                "BOLETOS": []
            }
            
            _carregar_dados_fcfo(cursor, codcfo_limpo, lancamentos[chave_agrupamento])

        grupo = lancamentos[chave_agrupamento]

        if not grupo["OS"] and os_num_mov:
            grupo["OS"] = str(os_num_mov).strip().lstrip("0")
        elif not grupo["OS"] and idfatlan:
            grupo["OS"] = contexto_fatura.get(f"{idfatlan}_os", "")

        if not grupo["PEDIDO"] and num_pedido:
            grupo["PEDIDO"] = num_pedido
            grupo["NUMERO_PEDIDO"] = num_pedido
        elif not grupo["PEDIDO"] and idfatlan:
            p_fat = contexto_fatura.get(f"{idfatlan}_ped", "")
            grupo["PEDIDO"] = p_fat
            grupo["NUMERO_PEDIDO"] = p_fat

        serie_nfs_atual = ""
        if serie_limpa in ("005", "NFS"):
            serie_nfs_atual = serie_limpa
        elif ev_serie_limpa in ("005", "NFS"):
            serie_nfs_atual = ev_serie_limpa
        elif mov_nfs_ev_serie_limpa in ("005", "NFS"):
            serie_nfs_atual = mov_nfs_ev_serie_limpa

        if serie_nfs_atual and not grupo["SERIE_NFSE"]:
            grupo["SERIE_NFSE"] = serie_nfs_atual

        num_nfs_atual = ""
        val_nfs_real = nfs_numfse or ev_nfs_numfse or nfs_filho_numfse
        if val_nfs_real and str(val_nfs_real).strip().upper() != "NONE":
            num_nfs_atual = str(val_nfs_real).strip().lstrip("0")
        elif serie_limpa in ("005", "NFS") and num_mov:
            num_nfs_atual = str(num_mov).strip().lstrip("0")
        elif mov_nfs_ev_num:
            num_nfs_atual = str(mov_nfs_ev_num).strip().lstrip("0")

        if num_nfs_atual:
            if num_nfs_atual not in grupo["NFSS_NUMS"]:
                grupo["NFSS_NUMS"].append(num_nfs_atual)
            if not grupo["NUMERO_NFS_MUNICIPAL"]:
                grupo["NUMERO_NFS_MUNICIPAL"] = num_nfs_atual

        rec_limpo = ""
        for rec_cand in (recibo_nfs, ev_recibo_nfs, nfs_filho_recibo):
            cand_str = str(rec_cand).strip() if rec_cand and str(rec_cand).strip().upper() != "NONE" else ""
            if cand_str:
                rec_limpo = cand_str
                break

        if rec_limpo and not grupo["RECIBO_NFSE"]:
            grupo["RECIBO_NFSE"] = rec_limpo

        if serie_nfs_atual or rec_limpo or num_nfs_atual:
            ja_registrada = any(
                (r.get("serie") == serie_nfs_atual and r.get("numero") == num_nfs_atual and r.get("recibo") == rec_limpo)
                for r in grupo["RECIBOS_NFSE"]
            )
            if not ja_registrada and (rec_limpo or num_nfs_atual):
                grupo["RECIBOS_NFSE"].append({
                    "recibo": rec_limpo,
                    "numero": num_nfs_atual,
                    "serie": serie_nfs_atual,
                })

        num_nfe_atual = ""
        if serie_limpa == "1" and num_mov:
            num_nfe_atual = str(num_mov).strip().lstrip("0")
        elif ev_serie_limpa == "1" and ev_num_mov:
            num_nfe_atual = str(ev_num_mov).strip().lstrip("0")
        elif mov_nfe_ev_num:
            num_nfe_atual = str(mov_nfe_ev_num).strip().lstrip("0")
        elif num_mov and serie_limpa not in ("005", "NFS", "EV"):
            num_nfe_atual = str(num_mov).strip().lstrip("0")

        if num_nfe_atual and num_nfe_atual not in grupo["NFES_NUMS"]:
            grupo["NFES_NUMS"].append(num_nfe_atual)

        data_nfe_ref = _formatar_data_bd(mov_nfe_ev_dt) or _formatar_data_bd(dt_emissao_tmov) or grupo["DATA"]
        for chave_cand in (tnfe_chave, tnfe_ev_chave, tnfe_filho_chave, chave_tmov, ev_chave, mov_nfe_ev_chave):
            chave_limpa = str(chave_cand).strip() if chave_cand and str(chave_cand).strip().upper() != "NONE" else ""
            if chave_limpa:
                if not grupo["CHAVE_NFE"]:
                    grupo["CHAVE_NFE"] = chave_limpa
                if not any(c["chave"] == chave_limpa for c in grupo["CHAVES_NFE"]):
                    grupo["CHAVES_NFE"].append({
                        "chave": chave_limpa,
                        "numero": num_nfe_atual,
                        "data": data_nfe_ref,
                    })

        if not grupo["NFES_NUMS"] and not grupo["NFSS_NUMS"] and num_doc:
            doc_limpo = str(num_doc).strip()
            if "/" in doc_limpo:
                partes = doc_limpo.split('/')
                if len(partes) >= 2:
                    nfe_doc = partes[0].strip().lstrip("0")
                    if nfe_doc and nfe_doc not in grupo["NFES_NUMS"]:
                        grupo["NFES_NUMS"].append(nfe_doc)
                    nfs_candidata = partes[1].strip().lstrip("0")
                    if nfs_candidata and nfs_candidata != grupo["PEDIDO"]:
                        if nfs_candidata not in grupo["NFSS_NUMS"]:
                            grupo["NFSS_NUMS"].append(nfs_candidata)
                        if not grupo["NUMERO_NFS_MUNICIPAL"]:
                            grupo["NUMERO_NFS_MUNICIPAL"] = nfs_candidata
                        if not any(r.get("numero") == nfs_candidata for r in grupo["RECIBOS_NFSE"]):
                            grupo["RECIBOS_NFSE"].append({
                                "recibo": "",
                                "numero": nfs_candidata,
                                "serie": serie_limpa if serie_limpa in ("005", "NFS") else "",
                            })
            else:
                if serie_limpa in ("005", "NFS"):
                    val_doc = doc_limpo.lstrip("0")
                    if val_doc and val_doc not in grupo["NFSS_NUMS"]:
                        grupo["NFSS_NUMS"].append(val_doc)
                    if not grupo["NUMERO_NFS_MUNICIPAL"]:
                        grupo["NUMERO_NFS_MUNICIPAL"] = val_doc
                    if val_doc and not any(r.get("numero") == val_doc for r in grupo["RECIBOS_NFSE"]):
                        grupo["RECIBOS_NFSE"].append({
                            "recibo": "",
                            "numero": val_doc,
                            "serie": serie_limpa,
                        })
                else:
                    val_doc = doc_limpo.lstrip("0")
                    if val_doc and val_doc not in grupo["NFES_NUMS"]:
                        grupo["NFES_NUMS"].append(val_doc)

        if id_lan not in ids_lan_ja_processados:
            ids_lan_ja_processados.add(id_lan)
            
            venc_parc_str = _formatar_data_bd(dt_venc)
            valor_parcela = float(val_orig) if val_orig else 0.0
            p_num = parcela if parcela else 1

            grupo["PARCELAS"].append({
                "PARCELA": p_num,
                "VENCIMENTO": venc_parc_str,
                "VALOR": valor_parcela,
                "STATUS": "BAIXADO" if str(status_lan).strip().upper() == "B" else "ABERTO"
            })

            grupo["BOLETOS"].append({
                "PARCELA": p_num,
                "NUMERO_DOCUMENTO": str(num_doc).strip() if num_doc else "DOC",
                "VENCIMENTO": venc_parc_str,
                "VALOR": valor_parcela,
                "BOL_NUMERO": _limpar_texto_bd(bol_num),
                "CODBARRABOLETO": _limpar_texto_bd(cod_barras),
                "LINHADIGITAVELBOLETO": _limpar_texto_bd(linha_dig),
                "QRCODEPIX": _limpar_texto_bd(pix),
                "DATA_EMISSAO": grupo["DATA"],
                "HISTORICO": _limpar_texto_bd(historico_flan),
            })

    resultado_final = []
    for item in lancamentos.values():
        nfes = item.pop("NFES_NUMS")
        nfss = item.pop("NFSS_NUMS")
        
        partes_nota = nfes + nfss
        item["NOTA"] = "  ".join(partes_nota) if partes_nota else "-"
        item["VALOR_TOTAL"] = sum(p["VALOR"] for p in item["PARCELAS"])
        resultado_final.append(item)

    for i in range(len(resultado_final)):
        atual = resultado_final[i]
        if atual["OS"] in ("", "-"):
            for outro in resultado_final:
                if outro["DATA"] == atual["DATA"] and outro["PLACA"] == atual["PLACA"] and outro != atual:
                    if outro["OS"] not in ("", "-"):
                        atual["OS"] = outro["OS"]
                        atual["PEDIDO"] = outro["PEDIDO"]
                        atual["NUMERO_PEDIDO"] = outro["NUMERO_PEDIDO"]
                    break

    return resultado_final


# -------------------------------------------------------------------------
# 3. ORQUESTRADOR PRINCIPAL
# -------------------------------------------------------------------------
def consultar_relatorio_pedidos_90_dias(codcfo_cliente):
    conn = _obter_conexao_bd()
    if not conn:
        return []

    cursor = conn.cursor()
    codcfo_limpo = codcfo_cliente.strip()
    
    try:
        lista_comuns = _consultar_pedidos_comuns(cursor, codcfo_limpo)
        lista_agrupados = _consultar_pedidos_agrupados(cursor, codcfo_limpo)
        resultado_final = lista_comuns + lista_agrupados
        return resultado_final

    except Exception as e:
        logging.error(f"Erro na consulta unificada de 90 dias: {e}")
        return []
    finally:
        conn.close()