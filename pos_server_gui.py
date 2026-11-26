"""Panel de control LAN para POS_Server. Sin servicios adicionales."""
from __future__ import annotations

import sqlite3
import queue
import socket
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from tkinter import ttk, messagebox, simpledialog

from core.settings import settings
from server_manager import server_manager, ip_lan
from services.lan_https import host_backend, url_visible


class ServerConsole:
    REFRESH_MS = 15000
    ONLINE_SECONDS = 90

    def __init__(self, host="0.0.0.0", port=None):
        self.host = host_backend(host)
        self.port = port or settings.api_port
        self.root = tk.Tk()
        self.root.title("IntraShop | Panel del servidor")
        self.root.geometry("1020x710")
        self.root.minsize(830, 560)
        self.root.configure(bg="#f3f5f9")
        self._closing = False
        self._loading = False
        self._refresh_requested = False
        self._timer = None
        self._tray = None
        self._tray_available = False
        self._exit_requested = False
        self._single_socket = None
        self._single_port = 49000 + (int(self.port) % 1000)
        self._init_single_instance()
        self.status = tk.StringVar(value="Iniciando servidor…")
        self.url = tk.StringVar(value=url_visible(ip_lan(), self.port))
        self.summary = tk.StringVar(value="Cargando dispositivos…")
        self.notice = tk.StringVar(value="")
        self.mostrar_eliminados = tk.BooleanVar(value=False)
        self._style()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._init_tray()
        self.refresh()
        self.start()

    def _init_single_instance(self):
        """Una consola por puerto; una segunda apertura enfoca la existente."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", self._single_port))
            sock.listen(4)
            sock.settimeout(0.5)
        except OSError:
            sock.close()
            try:
                with socket.create_connection(("127.0.0.1", self._single_port), timeout=1) as peer:
                    peer.sendall(b"SHOW")
            except OSError:
                pass
            self.root.destroy()
            raise SystemExit(0)
        self._single_socket = sock

        def listen():
            while not self._closing:
                try:
                    peer, _ = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with peer:
                    try:
                        if peer.recv(16).strip() == b"SHOW":
                            self.root.after(0, self.restore)
                    except OSError:
                        pass

        threading.Thread(target=listen, name="intrashop-singleton", daemon=True).start()

    def _init_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (64, 64), "#192b48")
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle((9, 9, 55, 55), radius=12, fill="#2d9f81")
            draw.text((23, 18), "I", fill="white")
            menu = pystray.Menu(
                pystray.MenuItem("Abrir administrador", lambda icon, item: self.root.after(0, self.restore), default=True),
                pystray.MenuItem("Iniciar servidor", lambda icon, item: self.root.after(0, self.start)),
                pystray.MenuItem("Detener servidor", lambda icon, item: self.root.after(0, self.stop)),
                pystray.MenuItem("Salir (detener servidor)", lambda icon, item: self.root.after(0, self.exit_app)),
            )
            self._tray = pystray.Icon("intrashop-server", img, "IntraShop Server", menu)
            threading.Thread(target=self._tray.run, name="intrashop-tray", daemon=True).start()
            self._tray_available = True
        except Exception:
            # Sin bandeja disponible (Linux sin AppIndicator, dependencias faltantes),
            # la ventana conserva su cierre normal para evitar quedar invisible.
            self._tray = None
            self._tray_available = False

    def restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit_app(self):
        if not messagebox.askyesno(
            "Salir de IntraShop Server",
            "¿Cerrar el administrador y detener el servidor que controla?"
        ):
            return
        self._exit_requested = True
        self.close()

    def _style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("Page.TFrame", background="#f3f5f9")
        style.configure("Panel.TLabel", background="#ffffff", foreground="#273449", font=("Arial", 10))
        style.configure("Title.TLabel", background="#f3f5f9", foreground="#16243b", font=("Arial", 20, "bold"))
        style.configure("Sub.TLabel", background="#f3f5f9", foreground="#53627a", font=("Arial", 10))
        style.configure("Treeview", rowheight=30, font=("Arial", 10))
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#152a49")])

    def _build(self):
        page = ttk.Frame(self.root, style="Page.TFrame", padding=20)
        page.pack(fill="both", expand=True)
        ttk.Label(page, text="IntraShop Server", style="Title.TLabel").pack(anchor="w")
        ttk.Label(page, text="Administración local · dispositivos y Mercado Pago", style="Sub.TLabel").pack(anchor="w", pady=(2, 12))
        head = ttk.Frame(page, style="Page.TFrame")
        head.pack(fill="x", pady=(0, 12))
        ttk.Label(head, textvariable=self.status, style="Sub.TLabel").pack(side="left")
        ttk.Label(head, textvariable=self.url, style="Sub.TLabel").pack(side="right")
        controls = ttk.Frame(page, style="Page.TFrame")
        controls.pack(fill="x", pady=(0, 12))
        for label, action in (("Iniciar servidor", self.start), ("Detener servidor", self.stop),
                              ("Abrir tienda", self.open_intrashop), ("Abrir administración", self.open_admin),
                              ("Copiar clave LAN", self.copy_lan_key),
                              ("Clave ADMIN", self.configure_admin_password),
                              ("HTTPS local", self.configure_https_ip),
                              ("Instalar / conectar equipos", self.distribution_wizard),
                              ("Actualizar", self.refresh)):
            ttk.Button(controls, text=label, command=action).pack(side="left", padx=(0, 8))
        ttk.Label(page, textvariable=self.summary, style="Sub.TLabel").pack(anchor="w", pady=(0, 10))

        notebook = ttk.Notebook(page)
        notebook.pack(fill="both", expand=True)
        devices = ttk.Frame(notebook, padding=12)
        assignments = ttk.Frame(notebook, padding=12)
        sessions = ttk.Frame(notebook, padding=12)
        pending_tab = ttk.Frame(notebook, padding=12)
        notebook.add(devices, text="Tótems")
        notebook.add(assignments, text="Asignaciones QR")
        notebook.add(sessions, text="Operadores POS")
        notebook.add(pending_tab, text="Conciliación")

        ttk.Label(
            devices,
            text="El tótem y su QR viven en POS Server. Desvincular equipo quita sólo la IP; "
                 "Eliminar tótem libera IP y asociación QR local, sin borrar ventas.",
            wraplength=900,
        ).pack(anchor="w", pady=(0, 8))
        self.totems = self._table(devices, [
            ("estado", "Estado", 105), ("nombre", "Nombre", 155), ("id", "Identificador", 145),
            ("ip", "IP vinculada", 120), ("observada", "IP observada", 115),
            ("contacto", "Último contacto", 155), ("qr", "QR", 105)])
        actions_totems = ttk.Frame(devices)
        actions_totems.pack(fill="x", pady=(8, 0))
        ttk.Button(actions_totems, text="Buscar equipos LAN", command=self.scan_lan).pack(side="left", padx=(0, 8))
        ttk.Button(actions_totems, text="Crear tótem", command=self.provision_totem).pack(side="left", padx=(0, 8))
        ttk.Button(actions_totems, text="Vincular / cambiar IP", command=self.bind_totem_ip).pack(side="left", padx=(0, 8))
        ttk.Button(actions_totems, text="Desvincular equipo (solo IP)", command=self.unbind_totem_ip).pack(side="left", padx=(0, 8))
        ttk.Button(actions_totems, text="Configurar QR", command=self.configure_totem_qr).pack(side="left")
        actions_baja = ttk.Frame(devices)
        actions_baja.pack(fill="x", pady=(6, 0))
        ttk.Button(actions_baja, text="Generar código de acceso", command=self.generate_pair_code).pack(side="left", padx=(0, 8))
        ttk.Button(actions_baja, text="Eliminar tótem…", command=self.delete_totem).pack(side="left", padx=(0, 8))
        ttk.Button(actions_baja, text="Restaurar eliminado", command=self.restore_totem).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(actions_baja, text="Mostrar eliminados", variable=self.mostrar_eliminados,
                        command=self.refresh).pack(side="left")
        self.totems.tag_configure("online", foreground="#12834a")
        self.totems.tag_configure("offline", foreground="#7a8799")
        self.totems.tag_configure("retired", foreground="#b07050")

        ttk.Label(assignments, text="Desvincular no elimina el POS ni el QR en Mercado Pago.", wraplength=800).pack(anchor="w", pady=(0, 8))
        self.qr_tree = self._table(assignments, [
            ("terminal", "Identificador", 260), ("tipo", "Tipo", 90),
            ("nombre", "Nombre", 200), ("pos", "POS Mercado Pago", 250)])
        actions = ttk.Frame(assignments)
        actions.pack(fill="x", pady=10)
        ttk.Button(actions, text="Desvincular QR seleccionado", command=self.unbind_qr).pack(side="left")
        ttk.Button(actions, text="Actualizar asignaciones", command=self.refresh).pack(side="left", padx=8)

        ttk.Label(sessions, text="Sesiones de operadores con acceso vigente").pack(anchor="w", pady=(0, 8))
        self.clients = self._table(sessions, [("operador", "Operador", 240), ("expira", "Válida hasta", 200)])
        ttk.Label(pending_tab, text="Operaciones que bloquean el QR; verificar en Mercado Pago antes de liberar.").pack(anchor="w", pady=(0, 8))
        self.pending_tree = self._table(pending_tab, [("id", "Checkout", 260), ("estado", "Estado", 110), ("pos", "POS Mercado Pago", 220), ("total", "Total", 110)])
        ttk.Button(pending_tab, text="Verificar pago y conciliar", command=self.reconcile_selected).pack(anchor="w", pady=4)
        ttk.Button(pending_tab, text="Liberar tras verificar en Mercado Pago", command=self.release_selected).pack(anchor="w", pady=4)
        ttk.Button(pending_tab, text="Copiar ID", command=self.copy_checkout_id).pack(anchor="w", pady=4)
        # Acciones por fila: nunca eliminar cobros, reservas o sesiones
        # directamente desde el menú contextual.
        for table, kind in ((self.totems, "totem"), (self.qr_tree, "qr"),
                            (self.clients, "session"), (self.pending_tree, "checkout")):
            table.bind("<Button-3>", lambda event, k=kind: self._context_menu(event, k))
            table.bind("<Button-2>", lambda event, k=kind: self._context_menu(event, k))
        ttk.Label(page, textvariable=self.notice, style="Sub.TLabel").pack(anchor="w", pady=(10, 0))

    def _context_menu(self, event, kind):
        table = {"totem": self.totems, "qr": self.qr_tree,
                 "session": self.clients, "checkout": self.pending_tree}[kind]
        item = table.identify_row(event.y)
        if not item:
            return
        table.selection_set(item)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Actualizar listado", command=self.refresh)
        if kind == "totem":
            menu.add_command(label="Vincular / cambiar IP…", command=self.bind_totem_ip)
            menu.add_command(label="Desvincular equipo (solo IP)", command=self.unbind_totem_ip)
            menu.add_command(label="Configurar QR…", command=self.configure_totem_qr)
            menu.add_command(label="Generar código de acceso al tótem", command=self.generate_pair_code)
            menu.add_command(label="Editar nombre del tótem", command=self.rename_totem)
            menu.add_command(label="Eliminar tótem…", command=self.delete_totem)
            menu.add_command(label="Restaurar tótem eliminado", command=self.restore_totem)
        elif kind == "qr":
            menu.add_command(label="Desvincular asignación QR", command=self.unbind_qr)
        elif kind == "checkout":
            menu.add_command(label="Verificar y conciliar", command=self.reconcile_selected)
            menu.add_command(label="Liberar tras verificación", command=self.release_selected)
            menu.add_command(label="Copiar ID de operación", command=self.copy_checkout_id)
        else:
            menu.add_command(label="Las sesiones expiran automáticamente", state="disabled")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            menu.destroy()

    def configure_https_ip(self):
        """Asistente Ubuntu: instala HTTPS en IP LAN sin DNS ni editar .env."""
        import shutil
        import subprocess
        import sys
        from pathlib import Path

        script = Path(__file__).resolve().parent / "deploy" / "configurar_https_ip.py"
        if not script.is_file():
            messagebox.showerror(
                "HTTPS local",
                "El instalador HTTPS no está incluido en esta distribución. "
                "Actualizá POS Server antes de continuar.",
                parent=self.root,
            )
            return
        detected = ip_lan()
        ip = simpledialog.askstring(
            "HTTPS local sin DNS",
            "IP fija de esta PC en la red LAN:\n"
            "No necesitás dominio ni configurar DNS.",
            initialvalue=detected, parent=self.root,
        )
        if ip is None:
            return
        try:
            from ipaddress import IPv4Address
            ip = str(IPv4Address(ip.strip()))
            from services.lan_https import url_visible
            from services.lan_discovery import _subnet_servidor
            _subnet_servidor(ip)
        except ValueError as exc:
            messagebox.showerror("IP LAN inválida", str(exc), parent=self.root)
            return
        if not messagebox.askyesno(
            "Configurar HTTPS gratuito",
            f"Se preparará HTTPS para https://{ip}/intrashop/.\n\n"
            "Un asistente instalará/configurará Caddy y creará el .env "
            "automáticamente. El sistema solicitará permisos de administrador "
            "una vez. No modifica la base ni los QR.\n\n"
            "Después tendrás que reiniciar POS Server y autorizar el "
            "certificado raíz una sola vez en cada tótem o POS cliente.\n\n"
            "¿Abrir asistente?",
            parent=self.root,
        ):
            return
        terminals = (
            (["konsole", "-e"] if shutil.which("konsole") else None),
            (["gnome-terminal", "--"] if shutil.which("gnome-terminal") else None),
            (["x-terminal-emulator", "-e"] if shutil.which("x-terminal-emulator") else None),
        )
        terminal = next((x for x in terminals if x is not None), None)
        if not terminal:
            messagebox.showinfo(
                "Instalar HTTPS",
                "No encontré un emulador de terminal. Ejecutá desde "
                "la carpeta del proyecto:\n\n"
                f"python3 deploy/configurar_https_ip.py --ip {ip}",
                parent=self.root,
            )
            return
        # Ejecutar la herramienta como usuario normal: ella invoca sudo
        # sólo al configurar Caddy. No lanzar Python del proyecto como root.
        try:
            command = terminal + [sys.executable, str(script), "--ip", ip]
            subprocess.Popen(command, cwd=str(script.parent.parent),
                             close_fds=True, start_new_session=True)
        except OSError as exc:
            messagebox.showerror("Asistente HTTPS", str(exc), parent=self.root)

    def _autorizar_kit_instalacion(self) -> bool:
        """Exige administrador existente; no se crea una clave maestra global."""
        from database_manager import DatabaseManager

        usuario = simpledialog.askstring(
            "Autorizar kit de instalación",
            "Usuario ADMIN de este comercio:", parent=self.root,
        )
        if not usuario:
            return False
        clave = simpledialog.askstring(
            "Autorizar kit de instalación",
            "Contraseña de administración:", show="*", parent=self.root,
        )
        if clave is None:
            return False
        try:
            actor = DatabaseManager(settings.db_path).autenticar_usuario(usuario, clave)
        except Exception:
            actor = None
        # No almacenar credenciales en memoria, logs, URL ni manifest.
        clave = None
        if not actor or not actor.get("es_admin") or not actor.get("activo"):
            messagebox.showerror(
                "Administración no autorizada",
                "Las credenciales no son de un administrador activo. "
                "Si todavía no configuraste uno, utilizá «Clave ADMIN» "
                "desde la consola local de POS Server.",
                parent=self.root,
            )
            return False
        return True

    def distribution_wizard(self):
        """Asistente de primera conexión POS/Server/Tótem con artefactos reales.

        Sin claves ni cookies embebidas en enlaces o ZIP. Nunca declara
        instalado un Tauri si no hay una compilación Windows disponible.
        """
        from pathlib import Path
        from tkinter import filedialog
        from services import installation_kits as kits

        window = tk.Toplevel(self.root)
        window.title("IntraShop · Instalar o conectar un equipo")
        window.geometry("670x525")
        window.minsize(575, 455)
        window.transient(self.root)
        pane = ttk.Frame(window, padding=18)
        pane.pack(fill="both", expand=True)
        ttk.Label(pane, text="Asistente de instalación",
                  font=("Arial", 18, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(
            pane,
            text="Un único sistema · Elegí qué función cumplirá este equipo.",
            wraplength=610,
        ).pack(anchor="w", pady=(0, 10))
        role = tk.StringVar(value="totem")
        options = ttk.Frame(pane)
        options.pack(fill="x", pady=(0, 10))
        for identifier, title in (
            ("servidor", "POS Server · Servidor"),
            ("pos", "POS · Caja"),
            ("totem", "IntraShop · Tótem"),
        ):
            ttk.Radiobutton(
                options, text=title, variable=role, value=identifier,
            ).pack(side="left", padx=(0, 12))
        url = url_visible(ip_lan(), self.port)
        current = tk.StringVar(value="")
        builds = tk.StringVar(value="")
        steps = tk.Text(
            pane, height=11, wrap="word", background="#f4f7fc",
            foreground="#223048", relief="flat", padx=14, pady=12,
            font=("Arial", 10),
        )
        steps.pack(fill="both", expand=True)
        ttk.Label(pane, textvariable=current, wraplength=615).pack(
            anchor="w", pady=(11, 3),
        )
        ttk.Label(pane, textvariable=builds, wraplength=615).pack(
            anchor="w", pady=(0, 6),
        )
        actions = ttk.Frame(pane)
        actions.pack(fill="x", pady=(6, 0))
        copy_button = ttk.Button(actions, text="Copiar enlace")
        copy_button.pack(side="left", padx=(0, 7))
        web_button = ttk.Button(actions, text="Abrir tienda")
        web_button.pack(side="left", padx=(0, 7))
        export_button = ttk.Button(actions, text="Exportar kit de conexión…")
        export_button.pack(side="left", padx=(0, 7))
        build_button = ttk.Button(actions, text="Ver ejecutables")
        build_button.pack(side="left", padx=(0, 7))
        setup_button = ttk.Button(pane, text="Configurar HTTPS local", command=self.configure_https_ip)
        setup_button.pack(anchor="w", pady=(12, 0))

        def refresh(*_):
            selected = role.get()
            available = kits.listar_instaladores()
            role_builds = available[selected]
            if selected == "servidor":
                detail = (
                    "1. Este equipo ejecuta POS Server y conserva la base SQLite.\n"
                    "2. Configurá HTTPS local desde el botón inferior.\n"
                    "3. Abrí la consola y creá las cajas y tótems.\n"
                    "4. Desde este asistente podés preparar kits para otras PCs.\n\n"
                    "La app POS Server se empaquetará junto a POS y Tauri "
                    "en el instalador unificado de distribución."
                )
            elif selected == "pos":
                detail = (
                    "1. Instalá el POS de escritorio en la caja.\n"
                    "2. Importá la CA pública del comercio, aprobando su huella.\n"
                    "3. Configurá la conexión con el servidor HTTPS y "
                    "la clave LAN copiada directamente por el administrador.\n"
                    "4. Iniciá sesión con un operador y sus permisos de caja.\n\n"
                    "El kit no contiene contraseñas ni clave LAN."
                )
            else:
                detail = (
                    "1. La tienda web puede abrirse desde cualquier PC/táctil.\n"
                    "2. Para el instalador Tauri Windows, debe existir un "
                    "ejecutable compilado y probado en «Ver ejecutables».\n"
                    "3. Importá el certificado del comercio con su huella verificada.\n"
                    "4. POS Server identifica el tótem y autoriza el navegador "
                    "con un código de uso único.\n\n"
                    "Cambiar de navegador no cambia su ID ni su asociación QR."
                )
            steps.configure(state="normal")
            steps.delete("1.0", "end")
            steps.insert("1.0", detail)
            steps.configure(state="disabled")
            if not url.startswith("https://"):
                current.set(
                    "Estado: HTTPS todavía no activo. Usá «Configurar HTTPS local» "
                    "antes de distribuir kits de producción."
                )
            else:
                current.set("Servidor: " + url + " · Acceso con certificado LAN privado")
            builds.set(
                "Instaladores encontrados: " +
                (", ".join(entry["nombre"] for entry in role_builds) if role_builds
                 else "ninguno compilado para este perfil.")
            )
            export_button.configure(state="normal" if url.startswith("https://")
                                    and selected in ("pos", "totem") else "disabled")
            copy_button.configure(state="normal" if selected == "totem" else "disabled")
            web_button.configure(state="normal" if selected == "totem" else "disabled")
            build_button.configure(state="normal" if role_builds else "disabled")

        def copy_link():
            # Sólo URL, nunca token, contraseña o código temporal en query.
            link = url + "/intrashop/"
            window.clipboard_clear()
            window.clipboard_append(link)
            messagebox.showinfo("Enlace copiado", link, parent=window)

        def export_kit():
            if not self._autorizar_kit_instalacion():
                return
            target = filedialog.asksaveasfilename(
                parent=window, title="Exportar kit público de conexión",
                initialfile=f"intrashop-conexion-{role.get()}.zip",
                defaultextension=".zip",
                filetypes=[("Kit de conexión ZIP", "*.zip")],
            )
            if not target:
                return
            try:
                result = kits.crear_kit_conexion(Path(target), url, role.get())
            except (ValueError, OSError) as exc:
                messagebox.showerror("Kit no generado", str(exc), parent=window)
                return
            messagebox.showinfo(
                "Kit de conexión creado",
                "Se generó el kit sin contraseñas ni tokens:\n"
                + result["archivo"] + "\n\n"
                "Huella de CA: " + result["sha256_ca"] +
                "\n\nVerificala en la PC cliente antes de aprobar el certificado.",
                parent=window,
            )

        def view_builds():
            found = kits.listar_instaladores().get(role.get(), [])
            if not found:
                messagebox.showinfo(
                    "Sin ejecutables publicados",
                    "Aún no hay compilaciones disponibles. El sistema "
                    "no genera ni anuncia enlaces de descarga falsos.",
                    parent=window,
                )
                return
            # Se abre la carpeta local de builds que maneja el administrador,
            # no se publica por una API anónima de la LAN.
            import subprocess
            import os
            directory = str(kits.BUILD_DIR)
            try:
                if os.name == "nt":
                    os.startfile(directory)
                elif shutil.which("xdg-open"):
                    subprocess.Popen(["xdg-open", directory])
                else:
                    raise OSError("No hay explorador de archivos instalado.")
            except OSError as exc:
                messagebox.showerror("Ejecutables", str(exc), parent=window)

        copy_button.configure(command=copy_link)
        web_button.configure(command=lambda: webbrowser.open(url + "/intrashop/"))
        export_button.configure(command=export_kit)
        build_button.configure(command=view_builds)
        role.trace_add("write", refresh)
        refresh()

    def configure_admin_password(self):
        """Inicialización/rotación local física del administrador del POS."""
        from services.passwords import hash_password, validar_nueva_clave
        from database_manager import DatabaseManager

        first = simpledialog.askstring(
            "Contraseña ADMIN segura",
            "Nueva contraseña del administrador (mínimo 12 caracteres):",
            show="*", parent=self.root,
        )
        if first is None:
            return
        second = simpledialog.askstring(
            "Confirmar contraseña ADMIN",
            "Repetí la contraseña para confirmar:",
            show="*", parent=self.root,
        )
        if second is None:
            return
        try:
            validar_nueva_clave(first)
            if first != second:
                raise ValueError("Las contraseñas no coinciden.")
        except ValueError as exc:
            messagebox.showerror("Contraseña ADMIN", str(exc), parent=self.root)
            return
        if not messagebox.askyesno(
            "Confirmar cambio ADMIN",
            "Esta operación reemplaza la clave del primer usuario ADMIN "
            "del servidor y lo activa. Revocará las sesiones abiertas y "
            "deshabilitará el acceso por clave legacy.\n\n"
            "¿Aplicar la contraseña nueva?",
            parent=self.root,
        ):
            return
        try:
            DatabaseManager(settings.db_path)
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """SELECT u.id,u.usuario FROM usuarios u
                       JOIN roles r ON r.id=u.rol_id
                       WHERE r.es_admin=1 ORDER BY u.id LIMIT 1"""
                ).fetchone()
                if row is None:
                    raise ValueError("No existe el usuario ADMIN.")
                conn.execute(
                    "UPDATE usuarios SET clave=?,activo=1,"
                    "fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?",
                    (hash_password(first), row["id"]),
                )
                # El acceso legacy ya no se usa; no retener la antigua clave
                # en texto plano dentro de config.
                conn.execute("DELETE FROM config WHERE clave='LOGIN_CLAVE'")
                conn.commit()
            from pos_auth import _sessions, _lock
            with _lock:
                _sessions.clear()
            self.notice.set(
                "Contraseña ADMIN actualizada y sesiones anteriores revocadas."
            )
            messagebox.showinfo(
                "ADMIN configurado",
                f"Se activó el usuario «{row['usuario']}» con la contraseña nueva.",
                parent=self.root,
            )
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("No se pudo configurar ADMIN", str(exc),
                                 parent=self.root)

    def copy_lan_key(self):
        """La clave se entrega sólo a un operador con acceso físico a esta PC."""
        if not messagebox.askyesno(
            "Clave de conexión de POS Server",
            "Esta clave permite acceder a las operaciones LAN del servidor.\n"
            "Compartila únicamente con terminales POS autorizadas y pegala "
            "en Configurar conexión LAN.\n\n"
            "¿Copiar al portapapeles de esta PC?",
            parent=self.root,
        ):
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(settings.api_key)
        self.notice.set(
            "Clave copiada. Pegala en Configurar conexión LAN del POS "
            "y borrá el portapapeles después."
        )

    def scan_lan(self):
        """Búsqueda solicitada desde la GUI, nunca automática.

        Solo muestra IPs detectadas. Al seleccionar una ofrece la IP como
        propuesta en el mismo diálogo de confirmación de vínculo.
        """
        from services.lan_discovery import detectar_lan

        try:
            own_ip = ip_lan()
            if not messagebox.askyesno(
                "Buscar equipos en la LAN",
                f"Se enviará un único ping a las IP de la red /24 de {own_ip}.\n"
                "No se escanean puertos, no se asignan QR y no se modifica ningún equipo.\n\n"
                "¿Continuar?",
                parent=self.root,
            ):
                return
        except (ValueError, OSError) as exc:
            messagebox.showerror("LAN", str(exc))
            return
        window = tk.Toplevel(self.root)
        window.title("Equipos detectados en la red local")
        window.geometry("570x455")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=15)
        frame.pack(fill="both", expand=True)
        status = tk.StringVar(value="Consultando IPs del segmento LAN…")
        ttk.Label(frame, textvariable=status, wraplength=530).pack(
            anchor="w", pady=(0, 10),
        )
        ttk.Label(
            frame,
            text="Una IP detectada no prueba que sea una PC ni que sea confiable. "
                 "La vinculación de un tótem siempre requiere confirmación.",
            wraplength=530,
        ).pack(anchor="w", pady=(0, 10))
        table = ttk.Treeview(
            frame, columns=("ip", "estado"), show="headings", selectmode="browse",
            height=12,
        )
        table.heading("ip", text="Dirección IP")
        table.heading("estado", text="Detección")
        table.column("ip", width=175, minwidth=130)
        table.column("estado", width=320, minwidth=200)
        table.pack(fill="both", expand=True)
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(12, 0))
        link = ttk.Button(bar, text="Usar IP para tótem seleccionado", state="disabled")
        link.pack(side="left")
        ttk.Button(bar, text="Cerrar", command=window.destroy).pack(side="right")
        results = queue.Queue()

        def worker():
            try:
                data = detectar_lan(own_ip)
                results.put(("ok", data))
            except Exception as exc:
                results.put(("error", str(exc)))

        def completed():
            if not window.winfo_exists():
                return
            try:
                state, result = results.get_nowait()
            except queue.Empty:
                window.after(150, completed)
                return
            if state == "error":
                status.set("No se pudo explorar la LAN: " + result)
                return
            status.set(
                f"Subred {result['subred']} · "
                f"{len(result['equipos'])} IP(s) detectadas. "
                "Elegí una y confirmá su vinculación."
            )
            for item in result["equipos"]:
                table.insert("", "end", values=(item["ip"], item["detalle"]))
            link.configure(state="normal" if result["equipos"] else "disabled")

        def use_ip():
            selected = table.selection()
            if not selected:
                messagebox.showinfo("Equipo", "Seleccioná una IP detectada.", parent=window)
                return
            if not self.totems.selection():
                messagebox.showinfo(
                    "Tótem", "Seleccioná primero un tótem en POS Server.", parent=window,
                )
                return
            chosen = table.item(selected[0], "values")[0]
            window.destroy()
            self.bind_totem_ip(suggested_ip=chosen)

        link.configure(command=use_ip)
        threading.Thread(target=worker, name="intrashop-lan-scan", daemon=True).start()
        window.after(150, completed)

    def generate_pair_code(self):
        """Código de un solo uso para habilitar checkout en este navegador."""
        from intrashop_entregas import ensure_schema
        from services.intrashop_totem_auth import generar_codigo

        selection = self.totems.selection()
        if not selection:
            messagebox.showinfo("Código de acceso", "Seleccioná primero un tótem.")
            return
        values = self.totems.item(selection[0], "values")
        totem_id, nombre = str(values[2]), str(values[1])
        try:
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN IMMEDIATE")
                ensure_schema(conn)
                code = generar_codigo(conn, totem_id)
                conn.commit()
            messagebox.showinfo(
                "Código temporal · " + nombre,
                f"Código válido por 10 minutos:\n\n{code}\n\n"
                "Ingresalo en la tienda desde el equipo cuya IP ya vinculaste.\n"
                "No envíes el código por enlaces o chats públicos.\n"
                "No se guarda en el navegador como localStorage.",
                parent=self.root,
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("Código de acceso", str(exc), parent=self.root)

    def provision_totem(self):
        from intrashop_entregas import ensure_schema
        from services.intrashop_totem_registry import provisionar

        try:
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN IMMEDIATE")
                ensure_schema(conn)
                created = provisionar(conn, 1)
                conn.commit()
            messagebox.showinfo("Tótem creado",
                created[0]["nombre"] + " (" + created[0]["id"] +
                ") disponible. Asignale IP y, luego, el QR desde POS Server.")
            self.refresh()
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("No se pudo crear el tótem", str(exc))

    def bind_totem_ip(self, suggested_ip=None):
        from intrashop_entregas import ensure_schema
        from services.intrashop_totem_registry import vincular_ip

        selected = self.totems.selection()
        if not selected:
            messagebox.showinfo("Vinculación IP", "Seleccioná un tótem.")
            return
        values = self.totems.item(selected[0], "values")
        totem_id, nombre = values[2], values[1]
        if str(values[0]).startswith("× Eliminado"):
            messagebox.showinfo(
                "Tótem eliminado", "Restaurá el tótem antes de vincular una IP.",
                parent=self.root,
            )
            return
        # La IP observada ayuda a elegir, pero no concede asociación automática.
        default = str(values[3]) if values[3] not in ("—", "", None) else ""
        if not default:
            default = str(values[4]) if values[4] not in ("—", "", None) else ""
        ip = simpledialog.askstring(
            "Vincular IP a " + str(nombre),
            "IP fija/reservada del equipo que abre la tienda:",
            initialvalue=str(suggested_ip or default), parent=self.root,
        )
        if ip is None:
            return
        ip = ip.strip()
        if not messagebox.askyesno(
            "Confirmar identidad del tótem",
            f"¿Vincular la IP {ip} a {nombre} ({totem_id})?\n\n"
            "Se conservará su asociación Mercado Pago, caja y pedidos.\n"
            "Una IP reutilizada por otro equipo podría suplantar este tótem. "
            "Reservala desde el router.",
            parent=self.root,
        ):
            return
        try:
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN IMMEDIATE")
                ensure_schema(conn)
                vincular_ip(conn, str(totem_id), ip)
                conn.commit()
            self.notice.set(f"{nombre} vinculado a {ip}. Identidad persistente en POS Server.")
            self.refresh()
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("No se pudo vincular la IP", str(exc))

    def unbind_totem_ip(self):
        from intrashop_entregas import ensure_schema
        from services.intrashop_totem_registry import desvincular_ip

        selected = self.totems.selection()
        if not selected:
            return
        values = self.totems.item(selected[0], "values")
        totem_id, nombre = values[2], values[1]
        if str(values[3]) in ("—", "", "None"):
            messagebox.showinfo(
                "Equipo ya desvinculado",
                f"{nombre} no tiene ninguna IP asignada.\n"
                "Para eliminar este registro de pruebas, usá «Eliminar tótem».",
                parent=self.root,
            )
            return
        if not messagebox.askyesno(
            "Desvincular equipo — conservar tótem y QR",
            f"¿Desconectar la IP {values[3]} del tótem {nombre}?\n\n"
            "El navegador dejará de identificarse como este tótem.\n"
            "Se conservan nombre, QR, caja y todo el historial.\n\n"
            "Para quitar también el tótem de la lista y liberar el QR, "
            "usá «Eliminar tótem».",
            parent=self.root,
        ):
            return
        try:
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN IMMEDIATE")
                ensure_schema(conn)
                if not desvincular_ip(conn, str(totem_id)):
                    raise ValueError("El tótem ya no existe.")
                conn.commit()
            self.notice.set(f"{nombre}: IP desvinculada. Tótem y QR conservados.")
            self.refresh()
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("No se pudo desvincular la IP", str(exc))

    def configure_totem_qr(self):
        """Asistente local: consulta POS autorizados y exige confirmación explícita."""
        selected = self.totems.selection()
        if not selected:
            messagebox.showinfo("Asignación QR", "Seleccioná primero un tótem.")
            return
        values = self.totems.item(selected[0], "values")
        totem_id, totem_name = values[2], values[1]
        try:
            with sqlite3.connect(settings.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                active = conn.execute(
                    "SELECT retirado FROM intrashop_totems WHERE id=?", (totem_id,),
                ).fetchone()
                if not active or active["retirado"]:
                    messagebox.showerror(
                        "QR no disponible",
                        "El tótem fue eliminado. Restauralo antes de vincular un QR.",
                        parent=self.root,
                    )
                    return
                existing = conn.execute(
                    "SELECT pos_external_id, store_external_id FROM intrashop_mp_bindings "
                    "WHERE terminal_id=? AND terminal_type='totem'", (totem_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            messagebox.showerror("Asignación QR", str(exc))
            return
        if existing:
            messagebox.showinfo("QR vinculado",
                "Tótem: " + str(totem_name) + "\\nPOS: " +
                str(existing["pos_external_id"]) + "\\nComercio: " +
                str(existing["store_external_id"]))
            return

        wizard = tk.Toplevel(self.root)
        wizard.title("Vincular QR · " + str(totem_name))
        wizard.geometry("620x390")
        wizard.transient(self.root)
        wizard.grab_set()
        frame = ttk.Frame(wizard, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Asignar punto de venta Mercado Pago",
                  font=("Arial", 14, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Tótem: " + str(totem_name) + "  |  IP: " + str(values[3])).pack(anchor="w", pady=(8, 12))
        status = tk.StringVar(value="Consultando los POS de la cuenta autorizada…")
        ttk.Label(frame, textvariable=status, wraplength=550).pack(anchor="w", pady=(0, 8))
        choice = tk.StringVar()
        combo = ttk.Combobox(frame, textvariable=choice, state="disabled", width=74)
        combo.pack(fill="x", pady=5)
        detail = tk.StringVar(value="No se enviarán credenciales ni claves en la URL.")
        ttk.Label(frame, textvariable=detail, wraplength=550).pack(anchor="w", pady=12)
        buttons = ttk.Frame(frame)
        buttons.pack(side="bottom", fill="x", pady=12)
        ttk.Button(buttons, text="Cancelar", command=wizard.destroy).pack(side="right", padx=5)
        confirm = ttk.Button(buttons, text="Confirmar vinculación", state="disabled")
        confirm.pack(side="right", padx=5)
        candidates = []
        messages = queue.Queue()

        def load():
            try:
                from services.mercadopago_service import mp_service
                results = mp_service.listar_pos()
                messages.put(("results", results))
            except Exception as exc:
                messages.put(("error", str(exc)))

        def poll_results():
            if not wizard.winfo_exists():
                return
            try:
                kind, payload = messages.get_nowait()
            except queue.Empty:
                wizard.after(120, poll_results)
                return
            if kind == "error":
                status.set("No se pudo consultar Mercado Pago: " + payload)
                return
            try:
                with sqlite3.connect(settings.db_path, timeout=5) as conn:
                    used = {row[0] for row in conn.execute(
                        "SELECT pos_external_id FROM intrashop_mp_bindings")}
                for item in payload:
                    external = str(item.get("external_id") or "").strip()
                    store = str(item.get("external_store_id") or "").strip()
                    if external and store and external not in used:
                        qr_data = item.get("qr_response") or item.get("qr") or {}
                        qr_url = str(qr_data.get("image") or item.get("qr_url") or "").strip() if isinstance(qr_data, dict) else ""
                        if qr_url.startswith("https://"):
                            candidates.append((external, store, str(item.get("name") or "POS"), qr_url))
                if not candidates:
                    status.set("No hay POS libres con comercio y QR HTTPS válido. Revisá la configuración de QR en Ajustes.")
                    return
                combo["values"] = [name + " | " + pos + " | Store " + store
                                   for pos, store, name, qr_url in candidates]
                combo.configure(state="readonly")
                status.set(str(len(candidates)) + " POS disponibles. Elegí uno para este tótem.")
            except (sqlite3.Error, ValueError) as exc:
                status.set("No se pudo preparar la selección: " + str(exc))

        def choose(_event=None):
            idx = combo.current()
            if idx >= 0:
                pos, store, _name, qr_url = candidates[idx]
                detail.set("Se asociará el POS " + pos + " del comercio " + store +
                           " con el tótem " + str(totem_name) + ". No se crea ningún POS nuevo.")
                confirm.configure(state="normal")
        combo.bind("<<ComboboxSelected>>", choose)

        def save():
            idx = combo.current()
            if idx < 0:
                return
            pos, store, _name, qr_url = candidates[idx]
            if not messagebox.askyesno("Confirmar QR",
                    "¿Vincular el tótem " + str(totem_name) + " con el POS " + pos +
                    " del comercio " + store + "?\\n\\nNo se creará ni eliminará ningún QR.",
                    parent=wizard):
                return
            confirm.configure(state="disabled")
            try:
                with sqlite3.connect(settings.db_path, timeout=5) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    import intrashop_checkout_store as checkout_store
                    checkout_store.ensure_schema(conn)
                    found = conn.execute("SELECT 1 FROM intrashop_totems WHERE id=?", (totem_id,)).fetchone()
                    if not found:
                        raise ValueError("El tótem ya no está registrado.")
                    if conn.execute("SELECT 1 FROM intrashop_mp_bindings WHERE terminal_id=? OR pos_external_id=?",
                                    (totem_id, pos)).fetchone():
                        raise ValueError("El tótem o POS ya fue vinculado desde otra ventana.")
                    active = conn.execute(
                        "SELECT 1 FROM intrashop_checkouts WHERE pos_external_id=? "
                        "AND estado IN ('reserved','creating','waiting','verifying','uncertain','paid') LIMIT 1",
                        (pos,)).fetchone()
                    if active:
                        raise ValueError("Este POS tiene un cobro activo o pendiente de conciliación.")
                    conn.execute("""INSERT INTO intrashop_mp_bindings
                        (terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,nombre)
                        VALUES (?,'totem',?,?,?,?)""", (totem_id, pos, store, qr_url, totem_name))
                    conn.commit()
                wizard.destroy()
                self.refresh()
                messagebox.showinfo("QR vinculado", "Asignación guardada y verificada en POS Server.")
            except (sqlite3.Error, ValueError) as exc:
                status.set("No se pudo vincular: " + str(exc))
                confirm.configure(state="normal")
        confirm.configure(command=save)
        threading.Thread(target=load, daemon=True).start()
        wizard.after(120, poll_results)

    def rename_totem(self):
        selection = self.totems.selection()
        if not selection:
            return
        values = self.totems.item(selection[0], "values")
        totem_id, current_name = values[2], values[1]
        name = simpledialog.askstring("Editar tótem", "Nombre del tótem:",
                                      initialvalue=current_name, parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name or len(name) > 80:
            messagebox.showerror("Tótem", "Ingresá un nombre de 1 a 80 caracteres.")
            return
        try:
            with sqlite3.connect(settings.db_path, timeout=5) as conn:
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.execute("UPDATE intrashop_totems SET nombre=? WHERE id=?",
                                      (name, totem_id))
                if cursor.rowcount != 1:
                    raise ValueError("El tótem ya no existe.")
                conn.commit()
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("Tótem", str(exc))
            return
        self.refresh()

    def delete_totem(self):
        """Retira un tótem de pruebas sin borrar pagos ni comandas históricas."""
        from intrashop_entregas import ensure_schema
        import intrashop_checkout_store as checkout_store
        from services.intrashop_totem_registry import resumen_retiro, retirar_totem

        selection = self.totems.selection()
        if not selection:
            messagebox.showinfo("Eliminar tótem", "Seleccioná el tótem que querés eliminar.")
            return
        values = self.totems.item(selection[0], "values")
        totem_id = str(values[2])
        try:
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                ensure_schema(conn)
                checkout_store.ensure_schema(conn)
                conn.commit()
                estado = resumen_retiro(conn, totem_id)
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("No se pudo consultar el tótem", str(exc))
            return
        if estado["retirado"]:
            messagebox.showinfo(
                "Tótem eliminado", "Este tótem ya está retirado. Usá «Restaurar eliminado».")
            return
        if estado["cobros_pendientes"] or estado["entregas_pendientes"]:
            messagebox.showerror(
                "No se puede eliminar todavía",
                f"El tótem {estado['nombre']} tiene "
                f"{estado['cobros_pendientes']} cobro(s) sin resolver y "
                f"{estado['entregas_pendientes']} entrega(s) pendiente(s).\n\n"
                "Regularizá las operaciones antes de eliminarlo.\n"
                "No se borrarán cobros ni se liberará stock por la fuerza.",
                parent=self.root,
            )
            return
        if not messagebox.askyesno(
            "Confirmar eliminación de tótem",
            f"Eliminar «{estado['nombre']}» ({totem_id}) de la lista operativa?\n\n"
            f"IP: {estado['ip_vinculada'] or 'Sin IP'}\n"
            f"POS Mercado Pago: {estado['pos_external_id'] or 'Sin QR'}\n"
            f"Checkouts históricos: {estado['checkouts_historicos']}\n"
            f"Comandas históricas: {estado['entregas_historicas']}\n\n"
            "Se quitarán la IP y el vínculo QR LOCAL del servidor.\n"
            "NO se eliminará el POS/QR de Mercado Pago ni los pagos, "
            "ventas, tickets o comandas históricos.\n"
            "El ID se reservará para evitar reutilizaciones accidentales.\n"
            "Podrás restaurar el tótem desde «Mostrar eliminados».",
            parent=self.root,
        ):
            return
        try:
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN IMMEDIATE")
                ensure_schema(conn)
                checkout_store.ensure_schema(conn)
                retirar_totem(conn, totem_id)
                conn.commit()
            self.notice.set(
                f"{estado['nombre']} eliminado de la operación. "
                "IP y QR local liberados; historial conservado."
            )
            self.refresh()
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("No se pudo eliminar el tótem", str(exc), parent=self.root)

    def restore_totem(self):
        from intrashop_entregas import ensure_schema
        from services.intrashop_totem_registry import restaurar_totem

        selection = self.totems.selection()
        if not selection:
            messagebox.showinfo(
                "Restaurar tótem",
                "Activá «Mostrar eliminados» y seleccioná el tótem a restaurar.")
            return
        values = self.totems.item(selection[0], "values")
        totem_id, nombre = str(values[2]), str(values[1])
        if not str(values[0]).startswith("× Eliminado"):
            messagebox.showinfo(
                "El tótem ya está activo",
                "Para restaurar, marcá «Mostrar eliminados» y seleccioná "
                "una fila con estado «Eliminado».",
                parent=self.root,
            )
            return
        if not messagebox.askyesno(
            "Restaurar tótem",
            f"¿Volver a habilitar {nombre} ({totem_id})?\n\n"
            "Deberás confirmar nuevamente su IP y configurar el QR local.",
            parent=self.root,
        ):
            return
        try:
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN IMMEDIATE")
                ensure_schema(conn)
                restaurar_totem(conn, totem_id)
                conn.commit()
            self.notice.set(f"{nombre} restaurado. Vinculá nuevamente la IP y el QR.")
            self.refresh()
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("No se pudo restaurar", str(exc), parent=self.root)

    def _table(self, parent, columns):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, label, width in columns:
            table.heading(key, text=label)
            table.column(key, width=width, minwidth=80, stretch=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return table

    def start(self):
        if self._closing or server_manager.activo:
            return
        def worker():
            try:
                server_manager.iniciar(host=self.host, port=self.port)
            except Exception as exc:
                msg = str(exc)
                self.root.after(0, lambda: messagebox.showerror("Servidor", msg) if not self._closing else None)
            finally:
                self.root.after(0, self.refresh)
        threading.Thread(target=worker, daemon=True).start()

    def stop(self):
        threading.Thread(target=server_manager.detener, daemon=True).start()

    def open_intrashop(self):
        webbrowser.open(url_visible(ip_lan(), self.port) + "/intrashop/")

    def open_admin(self):
        webbrowser.open(url_visible(ip_lan(), self.port) + "/intrashop/admin")

    @staticmethod
    def _safe_datetime(value):
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    def _snapshot(self):
        with sqlite3.connect(settings.db_path, timeout=3) as conn:
            conn.row_factory = sqlite3.Row
            # La IP observada no define identidad: sólo ip_vinculada confirma.
            from intrashop_entregas import ensure_schema
            ensure_schema(conn)
            conn.commit()
            totems = [dict(row) for row in conn.execute(
                "SELECT id,nombre,ip_vinculada,ip_address,ultimo_contacto,retirado "
                "FROM intrashop_totems ORDER BY id"
            )]
            bindings = [dict(row) for row in conn.execute(
                "SELECT terminal_id,terminal_type,nombre,pos_external_id FROM intrashop_mp_bindings ORDER BY terminal_type,nombre")]
            pending_rows = [dict(row) for row in conn.execute("SELECT id,estado,pos_external_id,total FROM intrashop_checkouts WHERE estado IN ('reserved','creating','waiting','verifying','uncertain','paid') ORDER BY created_at DESC LIMIT 100")]
        return totems, bindings, pending_rows

    @staticmethod
    def _fill(table, rows, identity_index=0):
        # No restaurar selección por columna Estado: puede repetirse en
        # múltiples filas y provocar asignaciones QR/IP al tótem equivocado.
        selected = table.selection()
        old_values = table.item(selected[0], "values") if selected else ()
        previous = old_values[identity_index] if len(old_values) > identity_index else None
        table.delete(*table.get_children())
        for row in rows:
            values, tag = row
            table.insert("", "end", values=values, tags=(tag,) if tag else ())
        if previous is not None:
            for item in table.get_children():
                values = table.item(item, "values")
                if len(values) > identity_index and values[identity_index] == previous:
                    table.selection_set(item)
                    break

    def refresh(self):
        if self._closing:
            return
        if self._timer is not None:
            self.root.after_cancel(self._timer)
            self._timer = None
        running = server_manager.activo and bool(getattr(server_manager._server, "started", False))
        self.status.set("● Servidor activo" if running else "○ Servidor detenido")
        self.url.set("http://" + ip_lan() + ":" + str(self.port))
        if self._loading:
            # Una mutación hecha durante el refresco debe verse de inmediato
            # al terminar la lectura actual, no 15 segundos después.
            self._refresh_requested = True
        else:
            self._loading = True
            def worker():
                try:
                    data = self._snapshot()
                    error = None
                except (sqlite3.Error, OSError) as exc:
                    data = None
                    error = str(exc)
                def finish():
                    self._loading = False
                    if self._closing:
                        return
                    if data:
                        self._render(*data)
                    else:
                        self.notice.set("No se pudo consultar el estado: " + str(error))
                    if self._refresh_requested:
                        self._refresh_requested = False
                        self.root.after(0, self.refresh)
                self.root.after(0, finish)
            threading.Thread(target=worker, daemon=True).start()
        self._timer = self.root.after(self.REFRESH_MS, self.refresh)

    def _render(self, totems, bindings, pending_rows):
        now = datetime.now()
        device_rows = []
        online_count = 0
        assigned_totems = {b["terminal_id"] for b in bindings if b["terminal_type"] == "totem"}
        show_retired = bool(self.mostrar_eliminados.get())
        for item in totems:
            retired = bool(item["retirado"])
            if retired and not show_retired:
                continue
            last = self._safe_datetime(item["ultimo_contacto"])
            online = bool(
                not retired and item["ip_vinculada"]
                and last and timedelta(0) <= now - last <= timedelta(seconds=self.ONLINE_SECONDS)
            )
            online_count += int(online)
            status = "× Eliminado" if retired else ("● En línea" if online else "○ Sin señal")
            qr_status = "—" if retired else ("● Vinculado" if item["id"] in assigned_totems else "○ Pendiente")
            device_rows.append(((status, item["nombre"], item["id"],
                                 item["ip_vinculada"] or "—", item["ip_address"] or "—",
                                 item["ultimo_contacto"], qr_status),
                                "retired" if retired else ("online" if online else "offline")))
        self._fill(self.totems, device_rows, identity_index=2)
        self._fill(self.pending_tree, [((p["id"],p["estado"],p["pos_external_id"],p["total"]),None) for p in pending_rows])
        self._fill(self.qr_tree, [
            ((b["terminal_id"], b["terminal_type"], b["nombre"], b["pos_external_id"]), None)
            for b in bindings])
        try:
            from pos_auth import _sessions
            # Varias autenticaciones del mismo operador/terminal no son
            # múltiples puestos conectados. Mostrar solo la sesión más reciente.
            unique = {}
            for session in list(_sessions.values()):
                user, exp = session[:2]
                if exp <= time.time():
                    continue
                terminal = session[3] if len(session) > 3 else ""
                key = (user.casefold(), terminal or "sin-terminal")
                if key not in unique or exp > unique[key][1]:
                    unique[key] = (user, exp)
            active = list(unique.values())
        except Exception:
            active = []
        self._fill(self.clients, [
            ((user, time.strftime("%d/%m/%Y %H:%M", time.localtime(exp))), None)
            for user, exp in active])
        self.summary.set(
            f"Tótems: {len(totems)} · En línea: {online_count} · QR asignados: {len(bindings)}"
            f" · Operadores: {len(active)} · Operaciones bloqueantes: {len(pending_rows)}")
        self.notice.set("Última actualización: " + datetime.now().strftime("%H:%M:%S"))

    def _selected_checkout(self):
        selected = self.pending_tree.selection()
        if not selected:
            messagebox.showinfo("Conciliación", "Seleccioná un checkout.")
            return None
        return self.pending_tree.item(selected[0], "values")[0]

    def reconcile_selected(self):
        checkout_id = self._selected_checkout()
        if not checkout_id:
            return
        self.notice.set("Consultando Mercado Pago…")
        def worker():
            try:
                from intrashop_api import reconcile_checkout
                result = reconcile_checkout(checkout_id, operador="POS_SERVER_LOCAL")
                msg = "Resultado: " + str(result.get("estado")) + " — " + str(result.get("message", ""))
                self.root.after(0, lambda: self._reconcile_result(msg))
            except Exception as exc:
                error = str(exc)
                self.root.after(0, lambda: messagebox.showerror("Conciliación", error))
        threading.Thread(target=worker, daemon=True).start()

    def _reconcile_result(self, msg):
        if not self._closing:
            messagebox.showinfo("Conciliación", msg)
            self.refresh()

    def release_selected(self):
        checkout_id = self._selected_checkout()
        if not checkout_id:
            return
        if not messagebox.askyesno("Verificación obligatoria",
            "¿Confirmaste en Mercado Pago que NO hubo cobro y que el QR está cerrado?"):
            return
        confirmation = simpledialog.askstring("Liberación manual",
            "Escribí LIBERAR SIN COBRO para confirmar:", parent=self.root)
        if confirmation != "LIBERAR SIN COBRO":
            return
        try:
            from intrashop_api import release_checkout, ReleaseRequest
            result = release_checkout(checkout_id,
                ReleaseRequest(confirmacion="VERIFIQUE EN MERCADO PAGO QUE NO EXISTE COBRO"),
                operador="POS_SERVER_LOCAL")
            messagebox.showinfo("Reserva liberada", str(result))
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Liberación", str(exc))
    def copy_checkout_id(self):
        selected = self.pending_tree.selection()
        if not selected:
            messagebox.showinfo("Conciliación", "Seleccioná un checkout.")
            return
        checkout_id = self.pending_tree.item(selected[0], "values")[0]
        self.root.clipboard_clear()
        self.root.clipboard_append(checkout_id)
        messagebox.showinfo("Conciliación", "ID copiado. Verificá este pago en Mercado Pago antes de liberar la reserva.")

    def unbind_qr(self):
        selection = self.qr_tree.selection()
        if not selection:
            messagebox.showinfo("Asignaciones", "Seleccioná un QR para desvincular.")
            return
        terminal = self.qr_tree.item(selection[0], "values")[0]
        if not messagebox.askyesno(
            "Desvincular QR",
            "¿Quitar la asociación de " + terminal + "?\n\n"
            "No se eliminará el POS de Mercado Pago."):
            return
        try:
            with sqlite3.connect(settings.db_path, timeout=5) as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT pos_external_id FROM intrashop_mp_bindings WHERE terminal_id=?", (terminal,)).fetchone()
                if not row:
                    raise ValueError("La asignación ya no existe.")
                busy = conn.execute("""SELECT 1 FROM intrashop_checkouts WHERE pos_external_id=?
                    AND estado IN ('reserved','creating','waiting','verifying','uncertain','paid') LIMIT 1""", (row[0],)).fetchone()
                if busy:
                    raise ValueError("Existen cobros pendientes. Conciliá antes de desvincular.")
                conn.execute("DELETE FROM intrashop_mp_bindings WHERE terminal_id=?", (terminal,))
                conn.commit()
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("No se pudo desvincular", str(exc))
            return
        self.refresh()

    def close(self):
        if self._tray_available and not self._exit_requested:
            self.root.withdraw()
            return
        self._closing = True
        if self._timer is not None:
            self.root.after_cancel(self._timer)
        server_manager.detener()
        if self._single_socket is not None:
            self._single_socket.close()
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ServerConsole().run()
