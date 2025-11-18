import socket
import threading
import json
import os
import base64
import uuid
import time
import random 
from queue import Queue
import tkinter as tk
from tkinter import scrolledtext

#BD
import sqlite3
from datetime import datetime

#INICIALIZACIÓN DE BASE DE DATOS
def init_db():
    #crea el archivo historial db
    conn = sqlite3.connect("historial.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial_conexiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias TEXT NOT NULL,
            codigo TEXT NOT NULL,
            ip TEXT NOT NULL,
            fecha_conexion TEXT NOT NULL,
            fecha_desconexion TEXT
        );
    """)
    conn.commit()
    conn.close()

def registrar_conexion(alias, codigo, ip):
    
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("historial.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO historial_conexiones(alias, codigo, ip, fecha_conexion)
        VALUES (?, ?, ?, ?)
    """, (alias, codigo, ip, fecha))
    conn.commit()
    conn.close()

def registrar_desconexion(alias):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("historial.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE historial_conexiones
        SET fecha_desconexion = ?
        WHERE alias = ? AND fecha_desconexion IS NULL
    """, (fecha, alias))
    conn.commit()
    conn.close()

# Inicializa BD al iniciar servidor
init_db()

clientes = {}                  # Diccionario global: alias → {codigo}
lock = threading.Lock()        # Evita conflictos entre threads
cola_mensajes = Queue()        # Cola segura para manejo de mensajes

#GUARDAR MENSAJES EN JSON
def guardar_mensaje_json(alias, mensaje, destinatario="Todos"):
    
    archivo = f"{alias}_chat.json"
    chat = []

    if os.path.exists(archivo):
        with open(archivo, "r", encoding="utf-8") as f:
            chat = json.load(f)

    chat.append({"remitente": alias, "destinatario": destinatario, "mensaje": mensaje})

    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(chat, f, indent=4, ensure_ascii=False)

#FUNCIONES PARA ENVÍO DE MENSAJES
def broadcast(texto, remitente):
    #Envía mensajes a TODOS los usuarios excepto al remitente.
    with lock:
        for alias, info in clientes.items():
            if alias != remitente:
                try:
                    info["conn"].send(f"{remitente} (Todos): {texto}".encode("utf-8"))
                except:
                    pass

def enviar_privado(destinatario, texto, remitente):
    #Envía mensajes privados entre dos usuarios.
    with lock:
        if destinatario in clientes:
            try:
                clientes[destinatario]["conn"].send(
                    f"{remitente} (Privado): {texto}".encode("utf-8")
                )
            except:
                pass

def enviar_archivo(remitente, destinatario, nombre_archivo, contenido_b64):   
    # Envía archivos codificados en base64. Se mandan como texto siguiendo el formato FILE:.
    mensaje = f"FILE:{remitente}:{nombre_archivo}:{contenido_b64}"

    with lock: #Utiliza un objeto lock (cerrojo) para asegurar que el acceso al diccionario compartido clientes sea seguro
        if destinatario.lower() == "todos":
            for alias, info in clientes.items(): #itera sobre clientes conectados
                if alias != remitente:
                    try:
                        info["conn"].send(mensaje.encode("utf-8"))
                    except:
                        pass
        elif destinatario in clientes: #enviar el archivo directamente
            try:
                clientes[destinatario]["conn"].send(mensaje.encode("utf-8"))
            except:
                pass

def enviar_lista_usuarios():
    #Notifica a todos los clientes la lista actualizada de usuarios conectados.
    with lock:
        lista = [f"{info['codigo']}|{alias}" for alias, info in clientes.items()]
        mensaje = ",".join(lista)

        for info in clientes.values():
            try:
                info["conn"].send(mensaje.encode("utf-8"))
            except:
                pass

#MANEJO PRINCIPAL DE CLIENTES (THREAD POR CLIENTE)
def manejar_cliente(conn, addr):
    #Atiende un cliente desde que se conecta hasta que se desconecta. Se ejecuta en un hilo independiente por cada usuario.
   
    alias = ""

    try:
        # Solicitar alias único
        while True:
            conn.send("Escribe tu alias: ".encode("utf-8"))
            alias = conn.recv(1024).decode("utf-8").strip()

            with lock:
                # Evita duplicados
                if alias in clientes:
                    conn.send("ALIAS_TAKEN".encode("utf-8"))
                    continue
                else:
                    # Asigna un código de usuario (100–999)
                    codigo = str(random.randint(100, 999))
                    clientes[alias] = {"conn": conn, "codigo": codigo}
                    conn.send(f"Bienvenido, {alias}.\n".encode("utf-8"))

                    # REGISTRO BD
                    registrar_conexion(alias, codigo, addr[0])
                    break

        print(f"{alias} se ha conectado desde {addr}")
        enviar_lista_usuarios()

        # Ciclo principal de recepción de mensajes
        while True:
            mensaje = conn.recv(10_000_000).decode("utf-8")
            if not mensaje or mensaje.lower() == "salir":
                break
            cola_mensajes.put((alias, mensaje))

    except Exception as e:
        print(f"Error con cliente {addr}: {e}")

    finally:
        # Eliminar usuario de lista global
        with lock:
            if alias in clientes:
                del clientes[alias]

        registrar_desconexion(alias)
        conn.close()
        print(f"{alias} se ha desconectado")
        enviar_lista_usuarios()

#PROCESADOR DE MENSAJES
def procesar_mensajes():  
    #Hilo que procesa todos los mensajes encolados, garantiza orden y evita condiciones de carrera.
  
    while True:
        alias, mensaje = cola_mensajes.get()

        if mensaje.startswith("MSG_ALL:"):
            texto = mensaje[len("MSG_ALL:"):]
            broadcast(texto, alias)
            guardar_mensaje_json(alias, texto, "Todos")
            print(f"{alias} mandó un mensaje público")

        elif mensaje.startswith("MSG_PRIVATE:"):
            partes = mensaje.split(":", 2)
            if len(partes) == 3:
                destinatario = partes[1]
                texto = partes[2]
                enviar_privado(destinatario, texto, alias)
                guardar_mensaje_json(alias, texto, destinatario)
                print(f"{alias} mandó un mensaje privado a {destinatario}")

        elif mensaje.startswith("FILE:"):
            partes = mensaje.split(":", 3)
            if len(partes) == 4:
                destinatario = partes[1]
                nombre_archivo = partes[2]
                contenido_b64 = partes[3]
                enviar_archivo(alias, destinatario, nombre_archivo, contenido_b64)
                guardar_mensaje_json(alias, f"Archivo enviado: {nombre_archivo}", destinatario)
                print(f"{alias} envió un archivo a {destinatario}")

        cola_mensajes.task_done()

#INTERFAZ GRÁFICA (TKINTER)
class InterfazServidor:
    #Interfaz gráfica que muestra actividad del servidor en tiempo real, Personalizada con colores suaves y botones útiles.
    def __init__(self, root):
        self.root = root
        self.root.title("Servidor de Chat")
        self.root.geometry("600x400")

        fondo_general = "#DBFAEB"
        fondo_interno = "#E8FFF4"
        texto_color  = "#2E463A"

        self.root.configure(bg=fondo_general)

        # Área de logs
        self.area_texto = scrolledtext.ScrolledText(
            root,
            state='disabled',
            wrap=tk.WORD,
            bg=fondo_interno,
            fg=texto_color,
            font=("Segoe UI", 10),
            borderwidth=2,
            relief="flat"
        )
        self.area_texto.pack(expand=True, fill='both', padx=10, pady=10)

        # Botonera
        self.frame_botones = tk.Frame(root, bg=fondo_general)
        self.frame_botones.pack(fill="x", pady=5)

        self.boton_limpiar = tk.Button(
            self.frame_botones,
            text="Limpiar",
            bg="#CFFFEA",
            fg="#1F3A31",
            relief="ridge",
            font=("Segoe UI", 10, "bold"),
            command=self.limpiar_texto
        )
        self.boton_limpiar.pack(side=tk.LEFT, padx=10)

        self.boton_salir = tk.Button(
            self.frame_botones,
            text="Cerrar servidor",
            bg="#CFFFEA",
            fg="#1F3A31",
            relief="ridge",
            font=("Segoe UI", 10, "bold"),
            command=self.cerrar_servidor
        )
        self.boton_salir.pack(side=tk.RIGHT, padx=10)

        # Redirección de print() hacia la interfaz
        self._stdout = print
        self.redirigir_print()

    def redirigir_print(self):
        #Redirige todo lo que se imprime en consola hacia la interfaz gráfica.
    
        def nuevo_print(*args, **kwargs):
            texto = " ".join(str(arg) for arg in args)
            self.area_texto.config(state='normal')
            self.area_texto.insert(tk.END, texto + "\n")
            self.area_texto.config(state='disabled')
            self.area_texto.yview(tk.END)
            self._stdout(*args, **kwargs)
        globals()['print'] = nuevo_print

    def limpiar_texto(self):
        #Limpia la ventana de logs.
        self.area_texto.config(state='normal')
        self.area_texto.delete(1.0, tk.END)
        self.area_texto.config(state='disabled')

    def cerrar_servidor(self):
        #Cierra servidor y finaliza la aplicación.
        print("Servidor cerrado manualmente.")
        self.root.quit()
        os._exit(0)

#MAIN DEL SERVIDOR
if __name__ == "__main__":
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind(("10.18.90.109", 5010))
    servidor.listen(5)
    print("Servidor en espera de conexiones...")

    # Thread que procesa mensajes
    threading.Thread(target=procesar_mensajes, daemon=True).start()

    def aceptar_conexiones():
        #Acepta nuevos clientes y lanza un hilo por cada uno.
    
        while True:
            conn, addr = servidor.accept()
            hilo = threading.Thread(target=manejar_cliente, args=(conn, addr))
            hilo.start()

    # Thread que acepta conexiones
    threading.Thread(target=aceptar_conexiones, daemon=True).start()

    # Inicia interfaz gráfica
    root = tk.Tk()
    app = InterfazServidor(root)
    root.mainloop()


