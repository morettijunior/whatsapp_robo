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
        except:
            pass
            
    return fdb.connect(
        dsn=caminho_bd,
        user="SYSDBA",
        password="masterkey",
        charset="ISO8859_1",
    )

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
        except:
            email_bruto = email_bruto.decode("utf-8", errors="ignore")
    return str(email_bruto).split(";")[0].strip()

def buscar_cliente_por_documento(doc_digitado):
    validacao = validar_e_formatar_documento(doc_digitado)
    if not validacao["valido"]:
        return {"status": "erro_formato", "mensagem": "Formato inválido."}
        
    doc_formatado = validacao["documento"]
    digitos_puros = "".join(filter(str.isdigit, doc_digitado))
    
    conn = _obter_conexao_bd()
    cursor = conn.cursor()
    sql = "SELECT CODCFO, NOME, EMAIL FROM FCFO WHERE TRIM(CGCCFO) = ? OR TRIM(CGCCFO) = ?"
    
    try:
        cursor.execute(sql, (doc_formatado, digitos_puros))
        row = cursor.fetchone()
        if row:
            codcfo, nome, email_bruto = row
            return {
                "status": "encontrado",
                "codcfo": str(codcfo).strip(),
                "nome": str(nome).strip() if nome else "",
                "email": extrair_primeiro_email(email_bruto)
            }
        else:
            return {"status": "nao_encontrado", "mensagem": "Não encontrado."}
    except Exception as e:
        logging.error(f"Erro ao buscar cliente: {e}")
        return {"status": "erro_bd", "mensagem": str(e)}
    finally:
        conn.close()

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
        except:
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
            f.BOL_NUMERO
        FROM FLAN f
        LEFT JOIN TMOV t ON f.IDMOV = t.IDMOV
        LEFT JOIN TNFE tnfe ON tnfe.IDMOV = t.IDMOV
        LEFT JOIN TNFEMUNICIPAL nfs ON f.IDMOV = nfs.IDMOV
        LEFT JOIN TMOV ev ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) IN ('005', '1') THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOV
                ELSE t.IDMOV
            END = ev.IDMOV
        )
        LEFT JOIN TNFE tnfe_ev ON tnfe_ev.IDMOV = ev.IDMOV
        LEFT JOIN TMOV os ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) IN ('005', '1') THEN ev.IDMOVRELAC
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
            os_num_mov, cod_barras, linha_dig, pix, bol_num
        ) = row
        
        if not id_mov:
            continue
            
        if id_mov not in lancamentos:
            venc_str = ""
            if dt_venc:
                v_partes = str(dt_venc).split()[0].split("-")
                if len(v_partes) == 3:
                    venc_str = f"{v_partes[2]}/{v_partes[1]}/{v_partes[0]}"
            
            serie_limpa = str(serie).strip().upper() if serie else ""
            ev_serie_limpa = str(ev_serie).strip().upper() if ev_serie else ""
            
            placa = "-"
            if placa_tmov and str(placa_tmov).strip() and str(placa_tmov).strip().upper() != "NONE":
                placa = str(placa_tmov).strip()
            elif ev_placa and str(ev_placa).strip() and str(ev_placa).strip().upper() != "NONE":
                placa = str(ev_placa).strip()
            
            numero_nota_fiscal = ""
            if serie_limpa == "1":
                numero_nota_fiscal = str(num_mov).strip().lstrip("0") if num_mov else ""
            elif ev_serie_limpa == "1":
                numero_nota_fiscal = str(ev_num_mov).strip().lstrip("0") if ev_num_mov else ""
            elif serie_limpa == "NFS":
                numero_nota_fiscal = str(nfs_numfse).strip() if nfs_numfse else (str(num_mov).strip().lstrip("0") if num_mov else "")
            elif not serie_limpa or serie_limpa == "EV":
                if num_mov and serie_limpa != "005":
                    numero_nota_fiscal = str(num_mov).strip().lstrip("0")

            chave_nfe_val = (
                str(tnfe_chave).strip() if tnfe_chave and str(tnfe_chave).strip() != "" else
                str(tnfe_ev_chave).strip() if tnfe_ev_chave and str(tnfe_ev_chave).strip() != "" else
                str(chave_tmov).strip() if chave_tmov and str(chave_tmov).strip() != "" else
                str(ev_chave).strip() if ev_chave and str(ev_chave).strip() != "" else ""
            )
            recibo_val = str(recibo_nfs).strip() if recibo_nfs else ""
            num_nfs_municipal_val = str(nfs_numfse).strip().lstrip("0") if nfs_numfse else ""

            num_pedido = ""
            if ev_num_mov and ev_serie_limpa != "1":
                num_pedido = str(ev_num_mov).strip().lstrip("0")
            elif num_mov and serie_limpa != "1":
                num_pedido = str(num_mov).strip().lstrip("0")
            
            if not num_pedido and num_doc:
                num_pedido = str(num_doc).strip().lstrip("0")

            num_os = ""
            if os_num_mov:
                num_os = str(os_num_mov).strip().lstrip("0")

            data_str = ""
            if dt_emissao_tmov:
                dt_partes = str(dt_emissao_tmov).split()[0].split("-")
                if len(dt_partes) == 3:
                    data_str = f"{dt_partes[2]}/{dt_partes[1]}/{dt_partes[0]}"
            elif dt_emissao_flan:
                dt_partes = str(dt_emissao_flan).split()[0].split("-")
                if len(dt_partes) == 3:
                    data_str = f"{dt_partes[2]}/{dt_partes[1]}/{dt_partes[0]}"

            valor_total = float(valor_liq) if valor_liq else float(val_orig or 0)

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
                "VALOR_TOTAL": valor_total,
                "PARCELAS": [],
                "BOLETOS": []
            }
            
            # Carrega dados do cliente na FCFO
            _carregar_dados_fcfo(cursor, codcfo_limpo, lancamentos[id_mov])
        
        venc_parc_str = ""
        if dt_venc:
            v_partes = str(dt_venc).split()[0].split("-")
            if len(v_partes) == 3:
                venc_parc_str = f"{v_partes[2]}/{v_partes[1]}/{v_partes[0]}"

        val_parcela = float(val_orig) if val_orig else 0.0
        p_num = parcela if parcela else 1

        if not any(p["PARCELA"] == p_num for p in lancamentos[id_mov]["PARCELAS"]):
            lancamentos[id_mov]["PARCELAS"].append({
                "PARCELA": p_num,
                "VENCIMENTO": venc_parc_str,
                "VALOR": val_parcela,
                "STATUS": "BAIXADO" if str(status_lan).strip().upper() == "B" else "ABERTO"
            })

            # Popula o boleto correspondente diretamente com os dados da FLAN da query
            lancamentos[id_mov]["BOLETOS"].append({
                "PARCELA": p_num,
                "NUMERO_DOCUMENTO": str(num_doc).strip() if num_doc else "DOC",
                "VENCIMENTO": venc_parc_str,
                "VALOR": val_parcela,
                "BOL_NUMERO": bol_num.strip() if (bol_num and str(bol_num).strip() != "None") else "",
                "CODBARRABOLETO": cod_barras.strip() if (cod_barras and str(cod_barras).strip() != "None") else "",
                "LINHADIGITAVELBOLETO": linha_dig.strip() if (linha_dig and str(linha_dig).strip() != "None") else "",
                "QRCODEPIX": pix.strip() if (pix and str(pix).strip() != "None") else "",
                "DATA_EMISSAO": data_str,
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
            f.BOL_NUMERO
        FROM FLAN f
        LEFT JOIN FLAN orig ON orig.IDFAT = f.IDFATLAN AND orig.IDMOV IS NOT NULL
        LEFT JOIN FLAN ponte ON ponte.IDFAT = f.IDFATLAN AND ponte.IDMOV IS NULL
        LEFT JOIN FLAN orig_via_ponte ON orig_via_ponte.IDFAT = ponte.IDFATLAN AND orig_via_ponte.IDMOV IS NOT NULL
        
        LEFT JOIN TMOV t ON t.IDMOV = COALESCE(orig.IDMOV, orig_via_ponte.IDMOV)
        LEFT JOIN TNFE tnfe ON tnfe.IDMOV = t.IDMOV
        LEFT JOIN TNFEMUNICIPAL nfs ON nfs.IDMOV = t.IDMOV
        LEFT JOIN TMOV ev ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) IN ('005', '1') THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOV
                ELSE t.IDMOV
            END = ev.IDMOV
        )
        LEFT JOIN TNFE tnfe_ev ON tnfe_ev.IDMOV = ev.IDMOV
        LEFT JOIN TNFEMUNICIPAL nfs_ev ON nfs_ev.IDMOV = ev.IDMOV
        LEFT JOIN TMOV os ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) IN ('005', '1') THEN ev.IDMOVRELAC
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
            if t_num and t_serie not in ("1", "NFS") and not contexto_fatura.get(f"{idfatlan}_ped"):
                contexto_fatura[f"{idfatlan}_ped"] = str(t_num).strip().lstrip("0")

    for row in linhas:
        (
            id_lan, num_doc, dt_emissao_flan, dt_venc, val_orig, status_lan, parcela,
            idfatlan, id_mov_origem,
            num_mov, dt_emissao_tmov, valor_liq, placa_tmov, serie, chave_tmov, tnfe_chave,
            nfs_numfse, recibo_nfs,
            ev_num_mov, ev_placa, ev_serie, ev_chave, tnfe_ev_chave, ev_nfs_numfse, ev_recibo_nfs,
            os_num_mov, cod_barras, linha_dig, pix, bol_num
        ) = row
        
        if not idfatlan:
            continue
            
        chave_agrupamento = f"AGR_{idfatlan}"
        
        if chave_agrupamento not in lancamentos:
            venc_str = ""
            if dt_venc:
                v_partes = str(dt_venc).split()[0].split("-")
                if len(v_partes) == 3:
                    venc_str = f"{v_partes[2]}/{v_partes[1]}/{v_partes[0]}"
            
            placa = "-"
            if ev_placa and str(ev_placa).strip() and str(ev_placa).strip().upper() != "NONE":
                placa = str(ev_placa).strip()
            elif placa_tmov and str(placa_tmov).strip() and str(placa_tmov).strip().upper() != "NONE":
                placa = str(placa_tmov).strip()

            num_pedido = ""
            if ev_num_mov:
                num_pedido = str(ev_num_mov).strip().lstrip("0")
            elif num_mov:
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

            data_str = ""
            if dt_emissao_tmov:
                dt_partes = str(dt_emissao_tmov).split()[0].split("-")
                if len(dt_partes) == 3:
                    data_str = f"{dt_partes[2]}/{dt_partes[1]}/{dt_partes[0]}"
            elif dt_emissao_flan:
                dt_partes = str(dt_emissao_flan).split()[0].split("-")
                if len(dt_partes) == 3:
                    data_str = f"{dt_partes[2]}/{dt_partes[1]}/{dt_partes[0]}"

            lancamentos[chave_agrupamento] = {
                "DATA": data_str,
                "OS": num_os,
                "PEDIDO": num_pedido,
                "NUMERO_PEDIDO": num_pedido,
                "PLACA": placa,
                "NFE_VAL": "",
                "NFS_VAL": "",
                "CHAVE_NFE": "",
                "RECIBO_NFSE": "",
                "NUMERO_NFS_MUNICIPAL": "",
                "NOTA": "",
                "VALOR_TOTAL": 0.0,
                "PARCELAS": [],
                "BOLETOS": []
            }
            
            # Carrega dados do cliente na FCFO
            _carregar_dados_fcfo(cursor, codcfo_limpo, lancamentos[chave_agrupamento])
        
        if not lancamentos[chave_agrupamento]["OS"] and os_num_mov:
            lancamentos[chave_agrupamento]["OS"] = str(os_num_mov).strip().lstrip("0")
        elif not lancamentos[chave_agrupamento]["OS"] and idfatlan:
            lancamentos[chave_agrupamento]["OS"] = contexto_fatura.get(f"{idfatlan}_os", "")

        if not lancamentos[chave_agrupamento]["PEDIDO"] and num_pedido:
            lancamentos[chave_agrupamento]["PEDIDO"] = num_pedido
            lancamentos[chave_agrupamento]["NUMERO_PEDIDO"] = num_pedido
        elif not lancamentos[chave_agrupamento]["PEDIDO"] and idfatlan:
            p_fat = contexto_fatura.get(f"{idfatlan}_ped", "")
            lancamentos[chave_agrupamento]["PEDIDO"] = p_fat
            lancamentos[chave_agrupamento]["NUMERO_PEDIDO"] = p_fat

        serie_limpa = str(serie).strip().upper() if serie else ""
        ev_serie_limpa = str(ev_serie).strip().upper() if ev_serie else ""
        
        val_nfs_real = nfs_numfse or ev_nfs_numfse
        if val_nfs_real:
            lancamentos[chave_agrupamento]["NFS_VAL"] = str(val_nfs_real).strip().lstrip("0")
            lancamentos[chave_agrupamento]["NUMERO_NFS_MUNICIPAL"] = str(val_nfs_real).strip().lstrip("0")
        elif serie_limpa == "NFS" and num_mov:
            lancamentos[chave_agrupamento]["NFS_VAL"] = str(num_mov).strip().lstrip("0")
            lancamentos[chave_agrupamento]["NUMERO_NFS_MUNICIPAL"] = str(num_mov).strip().lstrip("0")

        rec_val = recibo_nfs or ev_recibo_nfs
        if rec_val:
            lancamentos[chave_agrupamento]["RECIBO_NFSE"] = str(rec_val).strip()
                
        if serie_limpa == "1" and num_mov:
            lancamentos[chave_agrupamento]["NFE_VAL"] = str(num_mov).strip().lstrip("0")
        elif ev_serie_limpa == "1" and ev_num_mov:
            lancamentos[chave_agrupamento]["NFE_VAL"] = str(ev_num_mov).strip().lstrip("0")
        elif not lancamentos[chave_agrupamento]["NFE_VAL"] and num_mov and serie_limpa not in ("005", "NFS"):
            lancamentos[chave_agrupamento]["NFE_VAL"] = str(num_mov).strip().lstrip("0")

        current_chave = (
            str(tnfe_chave).strip() if tnfe_chave and str(tnfe_chave).strip() != "" else
            str(tnfe_ev_chave).strip() if tnfe_ev_chave and str(tnfe_ev_chave).strip() != "" else
            str(chave_tmov).strip() if chave_tmov and str(chave_tmov).strip() != "" else
            str(ev_chave).strip() if ev_chave and str(ev_chave).strip() != "" else ""
        )
        if current_chave and not lancamentos[chave_agrupamento]["CHAVE_NFE"]:
            lancamentos[chave_agrupamento]["CHAVE_NFE"] = current_chave

        if not lancamentos[chave_agrupamento]["NFE_VAL"] and not lancamentos[chave_agrupamento]["NFS_VAL"] and num_doc:
            doc_limpo = str(num_doc).strip()
            if "/" in doc_limpo:
                partes = doc_limpo.split('/')
                if len(partes) >= 2:
                    lancamentos[chave_agrupamento]["NFE_VAL"] = partes[0].strip().lstrip("0")
                    nfs_candidata = partes[1].strip().lstrip("0")
                    if nfs_candidata != lancamentos[chave_agrupamento]["PEDIDO"]:
                        lancamentos[chave_agrupamento]["NFS_VAL"] = nfs_candidata
                        lancamentos[chave_agrupamento]["NUMERO_NFS_MUNICIPAL"] = nfs_candidata
            else:
                if serie_limpa == "NFS":
                    lancamentos[chave_agrupamento]["NFS_VAL"] = doc_limpo.lstrip("0")
                else:
                    lancamentos[chave_agrupamento]["NFE_VAL"] = doc_limpo.lstrip("0")

        if id_lan not in ids_lan_ja_processados:
            ids_lan_ja_processados.add(id_lan)
            
            venc_parc_str = ""
            if dt_venc:
                v_partes = str(dt_venc).split()[0].split("-")
                if len(v_partes) == 3:
                    venc_parc_str = f"{v_partes[2]}/{v_partes[1]}/{v_partes[0]}"

            valor_parcela = float(val_orig) if val_orig else 0.0
            p_num = parcela if parcela else 1

            lancamentos[chave_agrupamento]["PARCELAS"].append({
                "PARCELA": p_num,
                "VENCIMENTO": venc_parc_str,
                "VALOR": valor_parcela,
                "STATUS": "BAIXADO" if str(status_lan).strip().upper() == "B" else "ABERTO"
            })

            lancamentos[chave_agrupamento]["BOLETOS"].append({
                "PARCELA": p_num,
                "NUMERO_DOCUMENTO": str(num_doc).strip() if num_doc else "DOC",
                "VENCIMENTO": venc_parc_str,
                "VALOR": valor_parcela,
                "BOL_NUMERO": bol_num.strip() if (bol_num and str(bol_num).strip() != "None") else "",
                "CODBARRABOLETO": cod_barras.strip() if (cod_barras and str(cod_barras).strip() != "None") else "",
                "LINHADIGITAVELBOLETO": linha_dig.strip() if (linha_dig and str(linha_dig).strip() != "None") else "",
                "QRCODEPIX": pix.strip() if (pix and str(pix).strip() != "None") else "",
                "DATA_EMISSAO": data_str,
            })

    resultado_final = []
    for item in lancamentos.values():
        nfe = item.pop("NFE_VAL")
        nfs = item.pop("NFS_VAL")
        
        partes_nota = []
        if nfe:
            partes_nota.append(nfe)
        if nfs:
            partes_nota.append(nfs)
            
        item["NOTA"] = "  ".join(partes_nota) if partes_nota else "-"
        item["VALOR_TOTAL"] = sum(p["VALOR"] for p in item["PARCELAS"])
        resultado_final.append(item)

    # --- PÓS-PROCESSAMENTO: Herança segura (apenas se a O.S. da linha estiver vazia) ---
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