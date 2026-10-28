import fdb
import json
from pathlib import Path

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
    # Se vier como bytes do Firebird, decodifica com segurança
    if isinstance(email_bruto, bytes):
        try:
            email_bruto = email_bruto.decode("iso-8859-1")
        except:
            email_bruto = email_bruto.decode("utf-8", errors="ignore")
            
    primeiro = str(email_bruto).split(";")[0].strip()
    return primeiro

def buscar_cliente_por_documento(doc_digitado):
    validacao = validar_e_formatar_documento(doc_digitado)
    
    if not validacao["valido"]:
        return {
            "status": "erro_formato",
            "mensagem": "O documento digitado possui quantidade incorreta de dígitos. Um CPF deve ter 11 dígitos e um CNPJ 14 dígitos."
        }
        
    doc_formatado = validacao["documento"]
    digitos_puros = "".join(filter(str.isdigit, doc_digitado))
    
    conn = _obter_conexao_bd()
    cursor = conn.cursor()
    
    # O TRIM() remove os espaços invisíveis adicionados pelo Firebird em campos CHAR
    sql = """
        SELECT CODCFO, NOME, EMAIL 
        FROM FCFO 
        WHERE TRIM(CGCCFO) = ? OR TRIM(CGCCFO) = ?
    """
    
    try:
        cursor.execute(sql, (doc_formatado, digitos_puros))
        row = cursor.fetchone()
        
        if row:
            codcfo, nome, email_bruto = row
            email_valido = extrair_primeiro_email(email_bruto)
            
            return {
                "status": "encontrado",
                "codcfo": str(codcfo).strip(),
                "nome": str(nome).strip() if nome else "",
                "email": str(email_valido).strip() if email_valido else ""
            }
        else:
            return {
                "status": "nao_encontrado",
                "mensagem": "CNPJ/CPF não encontrado em nossa base de dados."
            }
    except Exception as e:
        print(f"Erro ao buscar cliente no BD: {e}")
        return {
            "status": "erro_bd",
            "mensagem": str(e)
        }
    finally:
        conn.close()

def salvar_ou_atualizar_senha_robo(codcfo, nome, email, senha_plana):
    conn = _obter_conexao_bd()
    cursor = conn.cursor()
    
    cursor.execute("SELECT CODCFO FROM ROBOWHATS WHERE CODCFO = ?", (codcfo,))
    existe = cursor.fetchone()
    
    try:
        if existe:
            sql = "UPDATE ROBOWHATS SET NOME = ?, EMAIL = ?, SENHA = ? WHERE CODCFO = ?"
            cursor.execute(sql, (nome, email, senha_plana, codcfo))
        else:
            sql = "INSERT INTO ROBOWHATS (CODCFO, NOME, EMAIL, SENHA) VALUES (?, ?, ?, ?)"
            cursor.execute(sql, (codcfo, nome, email, senha_plana))
            
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao salvar na ROBOWHATS: {e}")
        return False
    finally:
        conn.close()

def verificar_senha_robo(codcfo, senha_digitada):
    conn = _obter_conexao_bd()
    cursor = conn.cursor()
    sql = "SELECT SENHA FROM ROBOWHATS WHERE CODCFO = ?"
    
    try:
        cursor.execute(sql, (codcfo,))
        row = cursor.fetchone()
        if row:
            senha_cadastrada = str(row[0]).strip()
            return senha_cadastrada == senha_digitada.strip()
        return False
    except Exception as e:
        print(f"Erro ao verificar senha na ROBOWHATS: {e}")
        return False
    finally:
        conn.close()