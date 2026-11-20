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


def asignar(terminal_id, terminal_type, pos_external_id, store_external_id, qr_url="", nombre="", caja_id=None):
    data={"terminal_id":terminal_id,"terminal_type":terminal_type,
          "pos_external_id":pos_external_id,"store_external_id":store_external_id,
          "qr_url":qr_url,"nombre":nombre,"caja_id":caja_id}
    if modo_actual()=="cliente":
        return _remote("PUT","",data)
    import intrashop_checkout_store as store
    from intrashop_api import _connect
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.ensure_schema(conn)
        if terminal_type not in ("totem", "caja"):
            raise ValueError("Tipo de terminal inválido")
        if terminal_type == "totem":
            from intrashop_entregas import ensure_schema
            ensure_schema(conn)
            found = conn.execute("SELECT 1 FROM intrashop_totems WHERE id=?", (terminal_id,)).fetchone()
            if not found:
                raise ValueError("El tótem no está registrado en POS Server")
        if caja_id is not None:
            if terminal_type != "totem":
                raise ValueError("La caja de cobro solo puede vincularse a tótems")
            active = conn.execute(
                "SELECT 1 FROM cajas WHERE id=? AND estado='abierta'", (int(caja_id),)
            ).fetchone()
            if not active:
                raise ValueError("La caja seleccionada no está abierta")
        duplicate = conn.execute(
            "SELECT nombre, terminal_id FROM intrashop_mp_bindings "
            "WHERE pos_external_id=? AND terminal_id<>? LIMIT 1",
            (pos_external_id, terminal_id)).fetchone()
        if duplicate:
            raise ValueError("Este POS de Mercado Pago ya está vinculado a " +
                             (duplicate["nombre"] or duplicate["terminal_id"]))
        busy=conn.execute("""SELECT 1 FROM intrashop_checkouts
            WHERE pos_external_id IN (?,(SELECT pos_external_id FROM intrashop_mp_bindings WHERE terminal_id=?))
            AND estado IN ('reserved','creating','waiting','verifying','uncertain','paid') LIMIT 1""",
            (pos_external_id,terminal_id)).fetchone()
        if busy:
            raise ValueError("El QR tiene un pago pendiente")
        conn.execute("""INSERT INTO intrashop_mp_bindings
            (terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,nombre,caja_id)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(terminal_id) DO UPDATE SET
            terminal_type=excluded.terminal_type,pos_external_id=excluded.pos_external_id,
            store_external_id=excluded.store_external_id,qr_url=excluded.qr_url,
            nombre=excluded.nombre,caja_id=excluded.caja_id""",
            (terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,nombre,caja_id))
        conn.commit()
    return {"ok":True}
