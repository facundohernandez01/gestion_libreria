"""Panel de control LAN para POS_Server. Sin servicios adicionales."""
from __future__ import annotations

import sqlite3
import socket
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from tkinter import ttk, messagebox, simpledialog

from core.settings import settings
from server_manager import server_manager, ip_lan


class ServerConsole:
    REFRESH_MS = 15000
    ONLINE_SECONDS = 90

    def __init__(self, host="0.0.0.0", port=None):
        self.host = host
        self.port = port or settings.api_port
        self.root = tk.Tk()
        self.root.title("IntraShop | Panel del servidor")
        self.root.geometry("1020x710")
        self.root.minsize(830, 560)
        self.root.configure(bg="#f3f5f9")
        self._closing = False
        self._loading = False
        self._timer = None
        self._tray = None
        self._tray_available = False
        self._exit_requested = False
        self._single_socket = None
        self._single_port = 49000 + (int(self.port) % 1000)
        self._init_single_instance()
        self.status = tk.StringVar(value="Iniciando servidor…")
        self.url = tk.StringVar(value="http://" + ip_lan() + ":" + str(self.port))
        self.summary = tk.StringVar(value="Cargando dispositivos…")
        self.notice = tk.StringVar(value="")
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

        ttk.Label(devices, text="Verde: actividad en los últimos 90 segundos. Gris: sin señal reciente.").pack(anchor="w", pady=(0, 8))
        self.totems = self._table(devices, [
            ("estado", "Estado", 110), ("nombre", "Nombre", 220), ("id", "Identificador", 260),
            ("ip", "IP registrada", 140), ("contacto", "Último contacto", 170)])
        self.totems.tag_configure("online", foreground="#12834a")
        self.totems.tag_configure("offline", foreground="#7a8799")

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
            menu.add_command(label="Editar nombre del tótem", command=self.rename_totem)
            menu.add_command(label="Eliminar tótem sin asignaciones", command=self.delete_totem)
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
        selection = self.totems.selection()
        if not selection:
            return
        values = self.totems.item(selection[0], "values")
        totem_id, name = values[2], values[1]
        if not messagebox.askyesno("Eliminar tótem",
                "¿Eliminar el registro de «" + name + "»?\\n"
                "Solo se permite si no tiene QR asignado ni comandas asociadas."):
            return
        try:
            with sqlite3.connect(settings.db_path, timeout=5) as conn:
                conn.execute("BEGIN IMMEDIATE")
                for sql in (
                    "SELECT 1 FROM intrashop_mp_bindings WHERE terminal_id=? LIMIT 1",
                    "SELECT 1 FROM intrashop_entregas WHERE totem_id=? LIMIT 1",
                    "SELECT 1 FROM intrashop_checkouts WHERE totem_id=? LIMIT 1",
                ):
                    if conn.execute(sql, (totem_id,)).fetchone():
                        raise ValueError("El tótem tiene asignaciones o historial de pedidos. No puede eliminarse.")
                conn.execute("DELETE FROM intrashop_totems WHERE id=?", (totem_id,))
                conn.commit()
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("No se pudo eliminar", str(exc))
            return
        self.refresh()

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
        webbrowser.open("http://127.0.0.1:" + str(self.port) + "/intrashop/")

    def open_admin(self):
        webbrowser.open("http://127.0.0.1:" + str(self.port) + "/intrashop/admin")

    @staticmethod
    def _safe_datetime(value):
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    def _snapshot(self):
        with sqlite3.connect(settings.db_path, timeout=3) as conn:
            conn.row_factory = sqlite3.Row
            # Una lectura agrupada cada 15 s; no se hace polling de la red.
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(intrashop_totems)")}
            ip_col = "ip" if "ip" in columns else ("ip_address" if "ip_address" in columns else None)
            fields = "id,nombre,ultimo_contacto" + ("," + ip_col if ip_col else "")
            totems = [dict(row) for row in conn.execute("SELECT " + fields + " FROM intrashop_totems ORDER BY nombre COLLATE NOCASE")]
            bindings = [dict(row) for row in conn.execute(
                "SELECT terminal_id,terminal_type,nombre,pos_external_id FROM intrashop_mp_bindings ORDER BY terminal_type,nombre")]
            pending_rows = [dict(row) for row in conn.execute("SELECT id,estado,pos_external_id,total FROM intrashop_checkouts WHERE estado IN ('reserved','creating','waiting','verifying','uncertain','paid') ORDER BY created_at DESC LIMIT 100")]
        return totems, bindings, pending_rows

    @staticmethod
    def _fill(table, rows):
        selected = table.selection()
        previous = table.item(selected[0], "values")[0] if selected else None
        table.delete(*table.get_children())
        for row in rows:
            values, tag = row
            table.insert("", "end", values=values, tags=(tag,) if tag else ())
        if previous:
            for item in table.get_children():
                if table.item(item, "values")[0] == previous:
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
        if not self._loading:
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
                self.root.after(0, finish)
            threading.Thread(target=worker, daemon=True).start()
        self._timer = self.root.after(self.REFRESH_MS, self.refresh)

    def _render(self, totems, bindings, pending_rows):
        now = datetime.now()
        device_rows = []
        online_count = 0
        for item in totems:
            last = self._safe_datetime(item["ultimo_contacto"])
            online = bool(last and timedelta(0) <= now - last <= timedelta(seconds=self.ONLINE_SECONDS))
            online_count += int(online)
            device_rows.append((("● En línea" if online else "○ Sin señal",
                                 item["nombre"], item["id"], item.get("ip", item.get("ip_address", "—")),
                                 item["ultimo_contacto"]), "online" if online else "offline"))
        self._fill(self.totems, device_rows)
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
