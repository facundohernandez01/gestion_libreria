"""Panel de control LAN para POS_Server. Sin servicios adicionales."""
from __future__ import annotations

import sqlite3
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from tkinter import ttk, messagebox

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
        self.status = tk.StringVar(value="Iniciando servidor…")
        self.url = tk.StringVar(value="http://" + ip_lan() + ":" + str(self.port))
        self.summary = tk.StringVar(value="Cargando dispositivos…")
        self.notice = tk.StringVar(value="")
        self._style()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.start()

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
        notebook.add(devices, text="Tótems")
        notebook.add(assignments, text="Asignaciones QR")
        notebook.add(sessions, text="Operadores POS")

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
        ttk.Label(page, textvariable=self.notice, style="Sub.TLabel").pack(anchor="w", pady=(10, 0))

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
            from intrashop_entregas import ensure_schema
            from intrashop_checkout_store import ensure_schema as ensure_checkout_schema
            ensure_schema(conn)
            ensure_checkout_schema(conn)
            conn.commit()
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(intrashop_totems)")}
            ip_col = "ip" if "ip" in columns else ("ip_address" if "ip_address" in columns else None)
            fields = "id,nombre,ultimo_contacto" + ("," + ip_col if ip_col else "")
            totems = [dict(row) for row in conn.execute("SELECT " + fields + " FROM intrashop_totems ORDER BY nombre COLLATE NOCASE")]
            bindings = [dict(row) for row in conn.execute(
                "SELECT terminal_id,terminal_type,nombre,pos_external_id FROM intrashop_mp_bindings ORDER BY terminal_type,nombre")]
            pending = conn.execute("SELECT COUNT(*) FROM intrashop_checkouts WHERE estado='uncertain'").fetchone()[0]
        return totems, bindings, pending

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

    def _render(self, totems, bindings, pending):
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
        self._fill(self.qr_tree, [
            ((b["terminal_id"], b["terminal_type"], b["nombre"], b["pos_external_id"]), None)
            for b in bindings])
        try:
            from pos_auth import _sessions
            active = [(user, exp) for user, exp in list(_sessions.values()) if exp > time.time()]
        except Exception:
            active = []
        self._fill(self.clients, [
            ((user, time.strftime("%d/%m/%Y %H:%M", time.localtime(exp))), None)
            for user, exp in active])
        self.summary.set(
            f"Tótems: {len(totems)} · En línea: {online_count} · QR asignados: {len(bindings)}"
            f" · Operadores: {len(active)} · Pagos a conciliar: {pending}")
        self.notice.set("Última actualización: " + datetime.now().strftime("%H:%M:%S"))

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
        self._closing = True
        if self._timer is not None:
            self.root.after_cancel(self._timer)
        server_manager.detener()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ServerConsole().run()
