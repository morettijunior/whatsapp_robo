import time
import shutil
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURAÇÕES DE CAMINHO ---
# Raiz local no terminal de faturamento
RAIZ_LOCAL_PDF = r"C:\TGA\Nfe\PDF"
RAIZ_LOCAL_XML = r"C:\TGA\Nfe\XML"

# Raiz correspondente no Servidor (substitua "SERVIDOR" pelo IP ou Nome do seu Servidor)
RAIZ_SERVIDOR_PDF = r"\\SERVIDOR\TGA\Nfe\PDF"
RAIZ_SERVIDOR_XML = r"\\SERVIDOR\TGA\Nfe\XML"

class SincronizarTgaHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        arquivo_origem = event.src_path
        extensao = os.path.splitext(arquivo_origem)[1].lower()
        
        destino = None
        
        # Identifica se pertence à árvore de PDF ou XML e calcula o caminho relativo
        if extensao == ".pdf" and RAIZ_LOCAL_PDF.lower() in arquivo_origem.lower():
            # Pega o caminho relativo a partir da raiz local e aplica na raiz do servidor
            caminho_relativo = os.path.relpath(arquivo_origem, RAIZ_LOCAL_PDF)
            destino = os.path.join(RAIZ_SERVIDOR_PDF, caminho_relativo)
            
        elif extensao == ".xml" and RAIZ_LOCAL_XML.lower() in arquivo_origem.lower():
            caminho_relativo = os.path.relpath(arquivo_origem, RAIZ_LOCAL_XML)
            destino = os.path.join(RAIZ_SERVIDOR_XML, caminho_relativo)
            
        if destino:
            # Aguarda 1 segundo para garantir que o ERP terminou de gravar o arquivo no disco
            time.sleep(1)
            try:
                # Garante que a subpasta exata (ex: 202610 ou 202610\NFe) exista no servidor
                pasta_destino_dir = os.path.dirname(destino)
                os.makedirs(pasta_destino_dir, exist_ok=True)
                
                # Copia o arquivo para o servidor mantendo o nome exato
                shutil.copy2(arquivo_origem, destino)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sincronizado: {destino}")
            except Exception as e:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Erro ao copiar '{arquivo_origem}': {e}")

if __name__ == "__main__":
    # Garante que as pastas raiz locais existam
    for pasta in [RAIZ_LOCAL_PDF, RAIZ_LOCAL_XML]:
        if not os.path.exists(pasta):
            os.makedirs(pasta, exist_ok=True)

    event_handler = SincronizarTgaHandler()
    observer = Observer()
    
    # recursive=True permite monitorar todas as subpastas (AnoMes, NFe, etc.) geradas automaticamente
    observer.schedule(event_handler, path=RAIZ_LOCAL_PDF, recursive=True)
    observer.schedule(event_handler, path=RAIZ_LOCAL_XML, recursive=True)
    
    observer.start()
    print("Monitor de NF-e (PDF/XML com subpastas) iniciado no terminal.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()