"""Consola local del servidor POS, independiente de Flet.

Ejecutar: python pos_server_gui.py
Empaquetar: pyinstaller --onefile --windowed --name IntraShopServer pos_server_gui.py
"""
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from core.settings import settings
from server_manager import server_manager, ip_lan


class ServerConsole:
    def __init__(self):
        self.root=tk.Tk()
        self.root.title("IntraShop · Servidor LAN")
        self.root.geometry("650x470")
        self.root.minsize(520,350)
        self.status=tk.StringVar(value="Servidor detenido")
        self.url=tk.StringVar(value="http://"+ip_lan()+":"+str(settings.api_port))
        outer=ttk.Frame(self.root,padding=18)
        outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="Servidor IntraShop",font=("Arial",18,"bold")).pack(anchor="w")
        ttk.Label(outer,textvariable=self.url).pack(anchor="w",pady=(3,12))
        ttk.Label(outer,textvariable=self.status).pack(anchor="w")
        actions=ttk.Frame(outer)
        actions.pack(fill="x",pady=12)
        ttk.Button(actions,text="Iniciar servidor",command=self.start).pack(side="left",padx=(0,8))
        ttk.Button(actions,text="Detener",command=self.stop).pack(side="left")
        ttk.Label(outer,text="Tótems registrados (último contacto)").pack(anchor="w",pady=(12,4))
        self.totems=ttk.Treeview(outer,columns=("nombre","id","contacto"),show="headings",height=8)
        for col,title,width in (("nombre","Nombre",190),("id","ID",190),("contacto","Último contacto",170)):
            self.totems.heading(col,text=title)
            self.totems.column(col,width=width)
        self.totems.pack(fill="both",expand=True)
        self.sessions=tk.StringVar(value="Sesiones POS: 0")
        ttk.Label(outer,textvariable=self.sessions).pack(anchor="w",pady=8)
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.refresh()

    def start(self):
        def run():
            try:
                server_manager.iniciar(host="0.0.0.0",port=settings.api_port)
            except Exception as exc:
                self.root.after(0,lambda:messagebox.showerror("Servidor",str(exc)))
        threading.Thread(target=run,daemon=True).start()

    def stop(self):
        threading.Thread(target=server_manager.detener,daemon=True).start()

    def refresh(self):
        running=server_manager.activo and bool(getattr(server_manager._server,"started",False))
        self.status.set("● ACTIVO · API disponible en LAN" if running else "● DETENIDO")
        self.url.set(server_manager.url() if running else "http://"+ip_lan()+":"+str(settings.api_port))
        try:
            from pos_auth import _sessions
            import time
            self.sessions.set("Sesiones POS activas: "+str(sum(exp>time.time() for _,exp in _sessions.values())))
        except Exception:
            pass
        try:
            with sqlite3.connect(settings.db_path,timeout=1) as conn:
                rows=conn.execute("SELECT nombre,id,ultimo_contacto FROM intrashop_totems ORDER BY nombre").fetchall()
            for key in self.totems.get_children():
                self.totems.delete(key)
            for row in rows:
                self.totems.insert("", "end",values=row)
        except sqlite3.Error:
            pass
        self.root.after(3000,self.refresh)

    def close(self):
        self.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__=="__main__":
    ServerConsole().run()
