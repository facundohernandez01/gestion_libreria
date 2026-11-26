"""Arqueo y cierre de caja: un único cálculo para POS local y POS Server.

El efectivo esperado contiene solamente ventas cobradas en efectivo;
Mercado Pago y tarjetas se muestran aparte y nunca suman al cajón.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CASH_METHODS = frozenset({"efectivo", "cash"})
PENDING_STATUSES = ("reserved", "creating", "waiting", "verifying", "uncertain", "paid")


def _money(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (TypeError, InvalidOperation) as exc:
        raise ValueError("Ingresá un importe válido para el arqueo.") from exc
    if not result.is_finite():
        raise ValueError("El importe del arqueo debe ser finito.")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_schema(conn) -> None:
    """Migración aditiva que no modifica cierres ni relaciones existentes."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cajas)")}
    for name in ("efectivo_esperado", "efectivo_contado", "diferencia_arqueo"):
        if name not in cols:
            conn.execute(f"ALTER TABLE cajas ADD COLUMN {name} REAL")
    import intrashop_checkout_store as store
    store.ensure_schema(conn)


def resumen_caja(conn, caja_id: int) -> dict:
    """Fotografía del turno; se recalcula dentro de la transacción de cierre."""
    ensure_schema(conn)
    caja = conn.execute(
        "SELECT * FROM cajas WHERE id=?", (int(caja_id),)
    ).fetchone()
    if caja is None:
        raise ValueError("La caja no existe.")
    if caja["estado"] != "abierta":
        raise ValueError("La caja ya está cerrada. Actualizá la pantalla.")
    apertura = _money(caja["importe_apertura"])
    rows = conn.execute(
        """SELECT COALESCE(NULLIF(TRIM(metodo_pago),''),'efectivo') AS metodo_pago,
                  COUNT(*) AS cantidad, COALESCE(SUM(total),0) AS total
           FROM ventas WHERE caja_id=? AND estado='completada'
           GROUP BY COALESCE(NULLIF(TRIM(metodo_pago),''),'efectivo')
           ORDER BY metodo_pago""", (int(caja_id),)
    ).fetchall()
    ventas_por_medio = []
    ventas_efectivo = Decimal("0")
    total_ventas = Decimal("0")
    cantidad_ventas = 0
    for row in rows:
        valor = _money(row["total"])
        cantidad = int(row["cantidad"])
        metodo = str(row["metodo_pago"])
        total_ventas += valor
        cantidad_ventas += cantidad
        if metodo.lower() in CASH_METHODS:
            ventas_efectivo += valor
        ventas_por_medio.append({
            "metodo_pago": metodo, "total": float(valor), "cantidad": cantidad,
        })
    gastos = conn.execute(
        "SELECT id,concepto,monto,fecha FROM gastos WHERE caja_id=? ORDER BY id DESC",
        (int(caja_id),)
    ).fetchall()
    total_gastos = sum((_money(r["monto"]) for r in gastos), Decimal("0"))
    efectivo_esperado = apertura + ventas_efectivo - total_gastos
    pendientes = conn.execute(
        """SELECT COUNT(*) AS cantidad FROM intrashop_checkouts
           WHERE estado IN ('reserved','creating','waiting','verifying','uncertain','paid')
             AND (caja_id=? OR caja_id IS NULL)""",
        (int(caja_id),),
    ).fetchone()["cantidad"]
    return {
        "caja_id": int(caja_id),
        "fecha_apertura": str(caja["fecha_apertura"] or ""),
        "usuario_apertura": str(caja["usuario_apertura"] or ""),
        "importe_apertura": float(apertura),
        "total_ventas": float(total_ventas),
        "cantidad_ventas": cantidad_ventas,
        "ventas_efectivo": float(ventas_efectivo),
        "ventas_otros_medios": float(total_ventas - ventas_efectivo),
        "ventas_por_medio": ventas_por_medio,
        "total_gastos": float(total_gastos),
        "gastos": [dict(r) for r in gastos],
        "efectivo_esperado": float(efectivo_esperado),
        "cobros_pendientes": int(pendientes),
    }


def cerrar_caja(conn, caja_id: int, *, importe_contado=None,
                observaciones: str = "", usuario: str = "",
                snapshot: dict | None = None) -> dict:
    """Cerrar solo una caja abierta, con snapshot y UPDATE en la misma tx.

    Debe invocarse después de BEGIN IMMEDIATE. No se admite cierre de
    caja con reservas de QR pendientes o sin aclaración de un descuadre.
    """
    resumen = resumen_caja(conn, caja_id)
    if snapshot:
        # Un arqueo presentado al operador no puede cerrar importes nuevos
        # silenciosamente si se registraron ventas/gastos después de abrirlo.
        for campo in ("efectivo_esperado", "total_ventas", "total_gastos"):
            valor = snapshot.get(campo)
            if valor is not None and _money(valor) != _money(resumen[campo]):
                raise ValueError(
                    "Se registraron movimientos mientras contabas la caja. "
                    "Actualizá el resumen y verificá nuevamente los importes."
                )
    if resumen["cobros_pendientes"]:
        raise ValueError(
            f"Hay {resumen['cobros_pendientes']} cobro(s) IntraShop pendiente(s) "
            "en esta caja. Finalizalos o concilialos antes del cierre."
        )
    esperado = _money(resumen["efectivo_esperado"])
    contado = esperado if importe_contado is None else _money(importe_contado)
    if contado < 0:
        raise ValueError("El efectivo contado no puede ser negativo.")
    diferencia = contado - esperado
    comentario = (observaciones or "").strip()
    if diferencia != 0 and not comentario:
        raise ValueError("Registrá una observación que explique el faltante o sobrante.")
    cursor = conn.execute(
        """UPDATE cajas SET fecha_cierre=CURRENT_TIMESTAMP,
               importe_cierre=?, efectivo_esperado=?, efectivo_contado=?,
               diferencia_arqueo=?, total_ventas=?, total_gastos=?,
               observaciones_cierre=?, usuario_cierre=?, estado='cerrada'
           WHERE id=? AND estado='abierta'""",
        (float(contado), float(esperado), float(contado), float(diferencia),
         resumen["total_ventas"], resumen["total_gastos"], comentario,
         usuario or "", int(caja_id)),
    )
    if cursor.rowcount != 1:
        raise ValueError("La caja fue cerrada desde otra terminal. Actualizá.")
    return {
        "ok": True, "caja_id": int(caja_id),
        "efectivo_esperado": float(esperado),
        "efectivo_contado": float(contado),
        "diferencia_arqueo": float(diferencia),
        "total_ventas": resumen["total_ventas"],
        "total_gastos": resumen["total_gastos"],
        "cantidad_ventas": resumen["cantidad_ventas"],
    }
