import socket
import threading # para recibir mensajes sin congelar la interfaz
import base64 # # para convertir archivos binarios en texto seguro para enviar
import os # para manejar rutas y archivos
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, simpledialog 
# filedialog: para elegir archivos
# scrolledtext: cuadro de texto con scroll
# messagebox: mostrar avisos o errores
# simpledialog: pedir datos con una ventanita

COLORES = {
    "fondo": "#F1FAF5",              
    "texto": "#1E3832",              
    "entrada": "#FFFFFF",            
    "panel_derecho": "#E3F2ED",      
    "boton_principal": "#4DB6AC",    
    "boton_secundario": "#A5D6A7",   
    "boton_verde": "#66BB6A",        
    "boton_rojo": "#E57373",         
    "texto_resaltado": "#739B8E",    
    "mensaje_bienvenida": "#26A69A", 
    "usuario_conectado": "#1ABC9C"   
}

# Envío / recepción de archivos
def enviar_archivo(cliente, destinatario, ruta_archivo, callback):
    if not os.path.exists(ruta_archivo):
        messagebox.showerror("Error", "Archivo no encontrado.")
        return

    nombre_archivo = os.path.basename(ruta_archivo)
    with open(ruta_archivo, "rb") as f:
        contenido_b64 = base64.b64encode(f.read()).decode("utf-8")

    mensaje = f"FILE:{destinatario}:{nombre_archivo}:{contenido_b64}"
    cliente.send(mensaje.encode("utf-8"))
    callback(f"📤 Archivo '{nombre_archivo}' enviado a {destinatario}.")

# objetivo: escuchar todo lo que viene del servidor y procesarlo
def recibir_mensajes(cliente, callback_mensaje, callback_usuarios):
    while True:
        try:
            mensaje = cliente.recv(10_000_000).decode("utf-8")
            if not mensaje:
                break
            texto = mensaje.strip()

            # Recibe la lista de usuarios conectados, la limpia y la envía a la interfaz
            if "|" in texto and ("," in texto or ";" in texto):
                lista_raw = texto.replace(";", ",")
                usuarios = [u for u in (item.strip() for item in lista_raw.split(",")) if u]
                callback_usuarios(usuarios)
                continue

            # Detecta archivos, los reconstruye desde base64 y los guarda en /recibidos
            if texto.startswith("FILE:"):
                partes = texto.split(":", 3)
                if len(partes) == 4:
                    remitente, nombre_archivo, contenido_b64 = partes[1], partes[2], partes[3]
                    os.makedirs("recibidos", exist_ok=True) # Crea la carpeta donde se guardarán los archivos recibidos
                    ruta = os.path.join("recibidos", nombre_archivo) #Une la carpeta recibidos con el nombre del archivo para generar la ruta  donde se va a guarda
                    with open(ruta, "wb") as f:
                        f.write(base64.b64decode(contenido_b64))# Convierte de Base64 a binario y lo guarda
                    callback_mensaje(f"📁 Archivo recibido de {remitente}: {nombre_archivo}\nGuardado en: {ruta}")
                else:
                    callback_mensaje("⚠ Mensaje de archivo mal formado.")
                continue

            # Si el mensaje es de bienvenida, lo muestro aparte

            if texto.startswith("Bienvenido"):
                callback_mensaje(texto)
                continue

            # Si no, lo trato como mensaje normal y lo muestro igual
            callback_mensaje(texto)

        except Exception as e:
            callback_mensaje(f"⚠ Error al recibir mensaje: {e}")
            break

# GUI Cliente

class ClienteGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("💬 Chat Cliente")
        self.master.geometry("900x550")#TAMAÑo ventana 
        self.master.configure(bg=COLORES["fondo"])

        #Conexión al servidor 
        #penas crea el socket, no se conecta todavía.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect(("127.0.0.1", 5010))#Intentar conectar al servidor
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo conectar con el servidor: {e}")
            master.destroy()
            return      
        try:
            # Llama al handshake para registrarse y obtener un alias autorizado por el servidor
            self.alias = self._realizar_handshake() 
            if not self.alias:
                self.sock.close()
                master.destroy()
                return
        except Exception as e:
            messagebox.showerror("Error", f"Error durante handshake: {e}")
            self.sock.close()
            master.destroy()
            return
        # Interfaz principal 
        main_frame = tk.Frame(master, bg=COLORES["fondo"])
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Panel izquierdo (mensajes)
        left_frame = tk.Frame(main_frame, bg=COLORES["fondo"])
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.text_area = scrolledtext.ScrolledText(
            left_frame, wrap=tk.WORD, state=tk.DISABLED,
            bg=COLORES["panel_derecho"], fg=COLORES["texto"], insertbackground="white"
           
        )
    
        self.text_area.pack(fill=tk.BOTH, expand=True)

        frame_input = tk.Frame(left_frame, bg=COLORES["fondo"])
        frame_input.pack(fill=tk.X, pady=5)

        self.entry_msg = tk.Entry(frame_input, bg=COLORES["entrada"], fg=COLORES["texto"], insertbackground="white")
        self.entry_msg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Botones de envío ----
        tk.Button(frame_input, text="Enviar a Todos", bg=COLORES["boton_principal"], fg="white",
                  command=self.enviar_a_todos).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_input, text="Enviar Privado", bg=COLORES["boton_secundario"], fg="white",
                  command=self.enviar_privado).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_input, text="📎 Adjuntar", bg=COLORES["boton_verde"], fg="white",
                  command=self.adjuntar_archivo).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_input, text="Desconectar", bg=COLORES["boton_rojo"], fg="white",
                  command=self.desconectar).pack(side=tk.LEFT, padx=5)

        self.mostrar_mensaje(f"👋 ¡Bienvenido/a {self.alias}! Ya puedes comenzar a chatear.")

        # Panel derecho (usuarios)  donde se muestra la lista de usuarios conectados
        right_frame = tk.Frame(main_frame, width=220, bg=COLORES["panel_derecho"])
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(right_frame, text="Usuarios conectados", bg=COLORES["panel_derecho"],
                 fg=COLORES["texto_resaltado"], font=("Arial", 10, "bold")).pack(pady=5)

        self.listbox_usuarios = tk.Listbox(right_frame, bg=COLORES["fondo"], fg=COLORES["texto"])
        self.listbox_usuarios.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Hilo para recibir mensajes 
        threading.Thread(target=recibir_mensajes, args=(self.sock, self.mostrar_mensaje, self.actualizar_usuarios), daemon=True).start()
    # Registro y validación del alias con el servidor.
    def _realizar_handshake(self):
        while True:
             #  Recibir mensaje inicial del servidor (el servidor habla primero)
            prompt = self.sock.recv(4096).decode("utf-8").strip()
            if not prompt:
                return None
            #  Si el servidor ya nos da la bienvenida, ya tenemos alias
            if prompt.startswith("Bienvenido"):
                try:
                    alias = prompt.split(",")[1].strip().strip(".")
                except:
                    alias = "Anónimo"
                return alias
            
            #  Si no hay bienvenida → pedir alias al usuario
            alias = simpledialog.askstring("Alias", prompt if prompt else "Ingrese su alias:")
            if alias is None:
                return None
            alias = alias.strip() or "Anónimo"
             #  Enviar alias al servidor para validación
            self.sock.send(alias.encode("utf-8"))
            # Recibir respuesta del servidor (aceptado, ocupado o mensaje extra)
            respuesta = self.sock.recv(4096).decode("utf-8").strip()
            if not respuesta:
                raise RuntimeError("El servidor cerró la conexión durante el registro de alias.")

             # Si el alias fue aceptado → terminar handshake
            if respuesta.startswith("Bienvenido") or respuesta.startswith("ALIAS_OK"):
                return alias
            #  Si el alias está ocupado → pedir otro (repite el ciclo)
            elif "alias_taken" in respuesta.lower() or "ya existe" in respuesta.lower():
                messagebox.showwarning("Alias ocupado", "El alias ya está en uso. Intente con otro.")
                continue
            
            else:
                if "bienvenido" in respuesta.lower():
                    return alias
                messagebox.showinfo("Servidor", respuesta)
                continue

    # envio de mensajes publicos 
    def enviar_a_todos(self):
        # toma el mensaje que el suario escribió en la entrada de texto
        mensaje = self.entry_msg.get().strip()
        if not mensaje:
            return
        try:
            #Envía el mensaje al servidor con el formato publico
            self.sock.send(f"MSG_ALL:{mensaje}".encode("utf-8"))
            self.mostrar_mensaje(f"(Tú a Todos): {mensaje}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar el mensaje: {e}")
        self.entry_msg.delete(0, tk.END)
        # envio de mensajes privados
    def enviar_privado(self):
         # toma el mensaje que el suario escribió en la entrada de texto
        mensaje = self.entry_msg.get().strip()
        if not mensaje:
            return
         # Verifica si el usuario seleccionó un destinatario en la lista
        seleccion = self.listbox_usuarios.curselection()
        if not seleccion:
            messagebox.showwarning("Privado", "Selecciona un usuario de la lista.")
            return
         # Obtiene el nombre del usuario seleccionado
        usuario = self.listbox_usuarios.get(seleccion[0])
        alias = usuario.split(" (")[0]
        try:
            self.sock.send(f"MSG_PRIVATE:{alias}:{mensaje}".encode("utf-8"))
            self.mostrar_mensaje(f"(Tú a {alias}): {mensaje}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar el mensaje privado: {e}")
        self.entry_msg.delete(0, tk.END)

    def adjuntar_archivo(self):
          # Abre una ventana para que el usuario elija un archivo
        ruta = filedialog.askopenfilename(title="Seleccionar archivo", filetypes=[("Todos los archivos", "*.*")])
        if not ruta:
            return
        destinatario = simpledialog.askstring("Enviar a", "Ingrese el nombre del destinatario (o 'Todos'):")
        # Si el usuario no escribe nada, se envía a todos por defecto
        destinatario = destinatario or "Todos"
        enviar_archivo(self.sock, destinatario, ruta, self.mostrar_mensaje)

    # Visualización 
    def mostrar_mensaje(self, mensaje):
        # Habilita el cuadro de texto para poder escribir en él
        self.text_area.config(state=tk.NORMAL)
        self.text_area.insert(tk.END, mensaje + "\n")
        # Lo vuelve a poner en solo lectura para evitar que el usuario lo edite
        self.text_area.config(state=tk.DISABLED)
        self.text_area.yview(tk.END)

    def actualizar_usuarios(self, lista):
        self.listbox_usuarios.delete(0, tk.END)
        
        # Recorre cada usuario recibido del servidor
        for usuario in lista:
            # Si viene con “codigo|alias”, separa ambas partes para mostrarlas bonito
            if "|" in usuario:
                codigo, alias = usuario.split("|", 1)
                self.listbox_usuarios.insert(tk.END, f"{alias} ({codigo})")
                 # Si solo viene el alias, se muestra tal cual
            else:
                self.listbox_usuarios.insert(tk.END, usuario)

    #  Desconexión
    def desconectar(self):
        # Intenta avisar al servidor que el usuario se está desconectando
        try:
            self.sock.send("salir".encode("utf-8"))
        except:
            pass  
        try:
            self.sock.close()
        except:
            pass        
    # Cierra la ventana principal del cliente
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ClienteGUI(root)
    root.mainloop()
