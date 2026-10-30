"""Administración de asignaciones MP desde caja local o cliente LAN."""
import httpx
from core.settings import settings
from core.db_factory import modo_actual, _server_url


def _remote(method, path, data=None):
    from adapters.entregas import _session_token
    base = _server_url() if modo_actual()=="cliente" else "http://127.0.0.1:"+str(settings.api_port)
    response = httpx.request(method, base.rstrip("/")+"/tienda/admin/mp-bindings"+path,
        json=data, headers={"Authorization":"Bearer "+(_session_token or "")}, timeout=8)
    response.raise_for_status()
    return response.json()


def listar():
    if modo_actual()=="cliente":
        return _remote("GET","")
    import intrashop_checkout_store as store
    from intrashop_api import _connect
    with _connect() as conn:
        store.ensure_schema(conn)
        return [dict(r) for r in conn.execute("SELECT * FROM intrashop_mp_bindings ORDER BY terminal_type,nombre")]


def asignar(terminal_id, terminal_type, pos_external_id, store_external_id, qr_url="", nombre=""):
    data={"terminal_id":terminal_id,"terminal_type":terminal_type,
          "pos_external_id":pos_external_id,"store_external_id":store_external_id,
          "qr_url":qr_url,"nombre":nombre}
    if modo_actual()!="local":
        return _remote("PUT","",data)
    import intrashop_checkout_store as store
    from intrashop_api import _connect
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.ensure_schema(conn)
        busy=conn.execute("""SELECT 1 FROM intrashop_checkouts
            WHERE pos_external_id IN (?,(SELECT pos_external_id FROM intrashop_mp_bindings WHERE terminal_id=?))
            AND estado IN ('reserved','creating','waiting','verifying','uncertain','paid') LIMIT 1""",
            (pos_external_id,terminal_id)).fetchone()
        if busy:
            raise ValueError("El QR tiene un pago pendiente")
        conn.execute("""INSERT INTO intrashop_mp_bindings
            (terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,nombre)
            VALUES (?,?,?,?,?,?) ON CONFLICT(terminal_id) DO UPDATE SET
            terminal_type=excluded.terminal_type,pos_external_id=excluded.pos_external_id,
            store_external_id=excluded.store_external_id,qr_url=excluded.qr_url,nombre=excluded.nombre""",
            (terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,nombre))
        conn.commit()
    return {"ok":True}
