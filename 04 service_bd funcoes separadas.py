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


# -------------------------------------------------------------------------
# 1. BLOCO DE PEDIDOS COMUNS (Mantido 100% idêntico à base estável)
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
            nfs.NUMERONFSE,
            ev.NUMEROMOV,
            ev.OB_NUMEROSERIE,
            ev.IDMOVRELAC,
            os.NUMEROMOV
        FROM FLAN f
        LEFT JOIN TMOV t ON f.IDMOV = t.IDMOV
        LEFT JOIN TNFEMUNICIPAL nfs ON f.IDMOV = nfs.IDMOV
        LEFT JOIN TMOV ev ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) IN ('NFS', '1') THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOV
                ELSE t.IDMOV
            END = ev.IDMOV
        )
        LEFT JOIN TMOV os ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) IN ('NFS', '1') THEN ev.IDMOVRELAC
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
            num_mov, dt_emissao_tmov, valor_liq, placa_tmov, id_mov_relac, serie,
            nfs_numfse,
            ev_num_mov, ev_placa, ev_relac,
            os_num_mov
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
            
            placa = "-"
            if placa_tmov and str(placa_tmov).strip() and str(placa_tmov).strip().upper() != "NONE":
                placa = str(placa_tmov).strip()
            elif ev_placa and str(ev_placa).strip() and str(ev_placa).strip().upper() != "NONE":
                placa = str(ev_placa).strip()
            
            numero_nota_fiscal = ""
            if serie_limpa == "NFS":
                if nfs_numfse:
                    numero_nota_fiscal = str(nfs_numfse).strip()
                else:
                    numero_nota_fiscal = str(num_mov).strip().lstrip("0") if num_mov else ""
            elif serie_limpa == "1":
                numero_nota_fiscal = str(num_mov).strip().lstrip("0") if num_mov else ""

            num_pedido = ""
            if ev_num_mov:
                num_pedido = str(ev_num_mov).strip().lstrip("0")
            elif num_mov:
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
                "PLACA": placa,
                "NOTA": numero_nota_fiscal,
                "VALOR_TOTAL": valor_total,
                "PARCELAS": []
            }
        
        lancamentos[id_mov]["PARCELAS"].append({
            "PARCELA": parcela if parcela else 1,
            "VENCIMENTO": venc_str if 'venc_str' in locals() else "",
            "VALOR": float(val_orig) if val_orig else 0.0,
            "STATUS": "BAIXADO" if str(status_lan).strip().upper() == "B" else "ABERTO"
        })

    return list(lancamentos.values())


# -------------------------------------------------------------------------
# 2. BLOCO DE PEDIDOS AGRUPADOS (Isolado e seguro para investigações futuras)
# -------------------------------------------------------------------------
def _consultar_pedidos_agrupados(cursor, codcfo_limpo):
    sql_agrupado = """
        SELECT 
            (
                SELECT FIRST 1 orig.IDMOV 
                FROM FLAN orig 
                WHERE orig.CODCFO = f.CODCFO 
                  AND orig.VALORORIGINAL = f.VALORORIGINAL 
                  AND orig.IDMOV IS NOT NULL 
                  AND orig.STATUSLAN = 'F'
            ) AS IDMOV_EFETIVO,
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
            nfs.NUMERONFSE,
            ev.NUMEROMOV,
            ev.OB_NUMEROSERIE,
            ev.IDMOVRELAC,
            ev.SERIE,
            nfs_ev.NUMERONFSE,
            os.NUMEROMOV
        FROM FLAN f
        LEFT JOIN TMOV t ON t.IDMOV = (
            SELECT FIRST 1 orig.IDMOV 
            FROM FLAN orig 
            WHERE orig.CODCFO = f.CODCFO 
              AND orig.VALORORIGINAL = f.VALORORIGINAL 
              AND orig.IDMOV IS NOT NULL 
              AND orig.STATUSLAN = 'F'
        )
        LEFT JOIN TNFEMUNICIPAL nfs ON nfs.IDMOV = t.IDMOV
        LEFT JOIN TMOV ev ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) IN ('NFS', '1') THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOV
                ELSE t.IDMOV
            END = ev.IDMOV
        )
        LEFT JOIN TNFEMUNICIPAL nfs_ev ON nfs_ev.IDMOV = ev.IDMOV
        LEFT JOIN TMOV os ON (
            CASE 
                WHEN UPPER(TRIM(t.SERIE)) = 'EV' THEN t.IDMOVRELAC
                WHEN UPPER(TRIM(t.SERIE)) IN ('NFS', '1') THEN ev.IDMOVRELAC
                ELSE NULL
            END = os.IDMOV
        )
        WHERE f.CODCFO = ?
          AND f.PAGREC = 'R'
          AND f.STATUSLAN IN ('A', 'B')
          AND f.DATAEMISSAO >= CURRENT_DATE - 90
          AND f.CODTDO IN ('DP', 'BO', 'NF')
          AND f.IDMOV IS NULL
        ORDER BY f.DATAEMISSAO ASC, f.PARCELA ASC
    """
    
    cursor.execute(sql_agrupado, (codcfo_limpo,))
    linhas = cursor.fetchall()
    lancamentos = {}
    
    for row in linhas:
        (
            id_mov_efetivo, num_doc, dt_emissao_flan, dt_venc, val_orig, status_lan, parcela,
            num_mov, dt_emissao_tmov, valor_liq, placa_tmov, id_mov_relac, serie,
            nfs_numfse,
            ev_num_mov, ev_placa, ev_relac, ev_serie, ev_nfs_numfse,
            os_num_mov
        ) = row
        
        if not id_mov_efetivo:
            continue
            
        if id_mov_efetivo not in lancamentos:
            venc_str = ""
            if dt_venc:
                v_partes = str(dt_venc).split()[0].split("-")
                if len(v_partes) == 3:
                    venc_str = f"{v_partes[2]}/{v_partes[1]}/{v_partes[0]}"
            
            serie_limpa = str(serie).strip().upper() if serie else ""
            ev_serie_limpa = str(ev_serie).strip().upper() if ev_serie else ""
            
            placa = "-"
            if ev_placa and str(ev_placa).strip() and str(ev_placa).strip().upper() != "NONE":
                placa = str(ev_placa).strip()
            elif placa_tmov and str(placa_tmov).strip() and str(placa_tmov).strip().upper() != "NONE":
                placa = str(placa_tmov).strip()
            
            numero_nota_fiscal = ""
            if nfs_numfse:
                numero_nota_fiscal = str(nfs_numfse).strip()
            elif ev_nfs_numfse:
                numero_nota_fiscal = str(ev_nfs_numfse).strip()
            elif serie_limpa in ("NFS", "1") and num_mov:
                numero_nota_fiscal = str(num_mov).strip().lstrip("0")
            elif ev_serie_limpa in ("NFS", "1") and ev_num_mov:
                numero_nota_fiscal = str(ev_num_mov).strip().lstrip("0")
            
            if not numero_nota_fiscal and num_doc and str(num_doc).strip():
                numero_nota_fiscal = str(num_doc).strip()

            num_pedido = ""
            if ev_num_mov:
                num_pedido = str(ev_num_mov).strip().lstrip("0")
            elif num_mov:
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

            lancamentos[id_mov_efetivo] = {
                "DATA": data_str,
                "OS": num_os,
                "PEDIDO": num_pedido,
                "PLACA": placa,
                "NOTA": numero_nota_fiscal,
                "VALOR_TOTAL": valor_total,
                "PARCELAS": []
            }
        
        lancamentos[id_mov_efetivo]["PARCELAS"].append({
            "PARCELA": parcela if parcela else 1,
            "VENCIMENTO": venc_str if 'venc_str' in locals() else "",
            "VALOR": float(val_orig) if val_orig else 0.0,
            "STATUS": "BAIXADO" if str(status_lan).strip().upper() == "B" else "ABERTO"
        })

    return list(lancamentos.values())


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
        # Executa as duas consultas de forma totalmente isolada e segura
        lista_comuns = _consultar_pedidos_comuns(cursor, codcfo_limpo)
        lista_agrupados = _consultar_pedidos_agrupados(cursor, codcfo_limpo)
        
        # Junta os resultados unificados para o PDF
        resultado_final = lista_comuns + lista_agrupados
        
        return resultado_final

    except Exception as e:
        logging.error(f"Erro na consulta unificada de 90 dias: {e}")
        return []
    finally:
        conn.close()