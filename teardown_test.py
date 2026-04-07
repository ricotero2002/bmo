import requests
import time

# Configuración
API_BASE_URL = "http://localhost:8081/api" # Ajusta si usas otra URL en k8s
TEST_USER_ID = "locust_tester"

def clean_test_chats():
    print(f"--- Iniciando limpieza de Chats para el usuario: {TEST_USER_ID} ---")
    try:
        # 1. Obtener todos los chats del usuario
        response = requests.get(f"{API_BASE_URL}/chats", params={"user_id": TEST_USER_ID})
        
        if not response.ok:
            print(f"❌ Error al obtener chats: {response.text}")
            return

        chats = response.json().get("chats", [])
        if not chats:
            print("✅ No hay chats de prueba para borrar.")
            return

        print(f"🧹 Se encontraron {len(chats)} chats. Borrando...")
        
        # 2. Iterar y borrar cada chat
        for chat in chats:
            thread_id = chat.get("thread_id")
            del_resp = requests.delete(f"{API_BASE_URL}/chats/{thread_id}")
            
            if del_resp.ok:
                print(f"  [OK] Chat {thread_id} eliminado.")
            else:
                print(f"  [ERROR] No se pudo borrar el chat {thread_id}: {del_resp.text}")
            
            time.sleep(0.1) # Pequeña pausa para no bombardear la API
            
    except Exception as e:
        print(f"💥 Excepción durante la limpieza de chats: {e}")

def clean_test_documents():
    print(f"\n--- Iniciando limpieza de Documentos para el usuario: {TEST_USER_ID} ---")
    
    # Hemos verificado que el endpoint real es /api/debug/document
    list_docs_endpoint = f"{API_BASE_URL}/debug/document" 
    
    try:
        response = requests.get(list_docs_endpoint, params={"user_id": TEST_USER_ID})
        
        if response.status_code == 404:
            print(f"⚠️ Endpoint de listado de documentos no encontrado en {list_docs_endpoint}.")
            return
        elif not response.ok:
            print(f"❌ Error al obtener documentos: {response.text}")
            return

        docs = response.json().get("documents", [])
        if not docs:
            print("✅ No hay documentos de prueba para borrar.")
            return

        print(f"🧹 Se encontraron {len(docs)} documentos. Encolando borrado...")

        # 2. Iterar y borrar usando el endpoint POST /delete_file
        for doc in docs:
            doc_id = doc.get("doc_id")
            payload = {
                "doc_id": doc_id,
                "user_id": TEST_USER_ID
            }
            del_resp = requests.post(f"{API_BASE_URL}/delete_file", json=payload)
            
            if del_resp.ok:
                print(f"  [OK] Documento {doc_id} enviado a la cola de borrado.")
            else:
                print(f"  [ERROR] No se pudo borrar el doc {doc_id}: {del_resp.text}")
                
            time.sleep(0.2)
            
    except Exception as e:
        print(f"💥 Excepción durante la limpieza de documentos: {e}")

if __name__ == "__main__":
    print("🚀 INICIANDO TEARDOWN DE PRUEBAS DE ESTRÉS 🚀")
    clean_test_chats()
    clean_test_documents()
    print("\n✨ TEARDOWN COMPLETADO ✨")
