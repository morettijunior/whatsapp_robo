import time
import shutil
import os
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURAÇÕES DE CAMINHO ---
RAIZ_LOCAL_PDF = r"C:\TGA\Nfe\PDF"
RAIZ_LOCAL_XML = r"C:\TGA\Nfe\XML"

RAIZ_SERVIDOR_PDF = r"\\SERVIDOR\TGA\Nfe\PDF"
RAIZ_SERVIDOR_XML = r"\\SERVIDOR\TGA\Nfe\XML"

# Janela de retenção (100 dias)
DIAS_LIMITE = 100

def limpar_pdfs_antigos(diretorio):
    """Apaga apenas arquivos .pdf com mais de 100 dias, preservando os XMLs"""
    if not os.path.exists(diretorio):
        return
    
    data_corte = datetime.now() - timedelta(days=DIAS_LIMITE)
    for pasta_atual, subpastas, arquivos in os.walk(diretorio):
        for arquivo in arquivos:
            if arquivo.lower().endswith(".pdf"):
                caminho_arquivo = os.path.join(pasta_atual, arquivo)
                try:
                    timestamp_arquivo = os.path.getmtime(caminho_arquivo)
                    data_arquivo = datetime.fromtimestamp(timestamp_arquivo)
                    
                    if data_arquivo < data_corte:
                        os.remove(caminho_arquivo)
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] PDF antigo removido da retenção: {arquivo}")
                except Exception as e:
                    print(f"Erro ao limpar PDF antigo '{arquivo}': {e}")

class SincronizarEValucarHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        arquivo_origem = event.src_path
        extensao = os.path.splitext(arquivo_origem)[1].lower()
        
        destino = None
        if extensao == ".pdf" and RAIZ_LOCAL_PDF.lower() in arquivo_origem.lower():
            caminho_relativo = os.path.relpath(arquivo_origem, RAIZ_LOCAL_PDF)
            destino = os.path.join(RAIZ_SERVIDOR_PDF, caminho_relativo)
        elif extensao == ".xml" and RAIZ_LOCAL_XML.lower() in arquivo_origem.lower():
            caminho_relativo = os.path.relpath(arquivo_origem, RAIZ_LOCAL_XML)
            destino = os.path.join(RAIZ_SERVIDOR_XML, caminho_relativo)
            
        if destino:
            time.sleep(1) # Aguarda gravação completa do ERP
            try:
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.copy2(arquivo_origem, destino)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sincronizado em tempo real: {destino}")
            except Exception as e:
                print(f"Erro ao sincronizar arquivo em tempo real: {e}")

if __name__ == "__main__":
    # Garante que as pastas locais existam
    for pasta in [RAIZ_LOCAL_PDF, RAIZ_LOCAL_XML]:
        if not os.path.exists(pasta):
            os.makedirs(pasta, exist_ok=True)

    print("Iniciando rotina de limpeza de PDFs com mais de 100 dias...")
    # Limpa no Terminal (Local)
    limpar_pdfs_antigos(RAIZ_LOCAL_PDF)
    # Limpa no Servidor
    limpar_pdfs_antigos(RAIZ_SERVIDOR_PDF)
    print("Limpeza concluída. Ativando monitoramento em tempo real...")

    # Ativa o watchdog para sincronizar o que vier daqui para frente
    event_handler = SincronizarEValucarHandler()
    observer = Observer()
    
    observer.schedule(event_handler, path=RAIZ_LOCAL_PDF, recursive=True)
    observer.schedule(event_handler, path=RAIZ_LOCAL_XML, recursive=True)
    
    observer.start()
    print("Monitor de NF-e rodando ativamente em segundo plano.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()