"""Rutas LAN administrativas para OAuth MP. Nunca retornan tokens al cliente."""
from __future__ import annotations

import logging

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pos_auth import require_config
from services import mp_oauth_bridge as bridge
from services.mercadopago_service import mp_service

router = APIRouter(prefix="/tienda/admin/mp-oauth", tags=["Mercado Pago OAuth POS"])
logger = logging.getLogger(__name__)


class StartIn(BaseModel):
    hub_url: str = Field(default="", max_length=256)


def _failure(error):
    logger.warning("Mercado Pago OAuth: %s", type(error).__name__)
    raise HTTPException(status_code=502, detail=str(error)[:250])


@router.post("/start")
def start(body: StartIn, operador: str = Depends(require_config)):
    try:
        return bridge.start(body.hub_url or None)
    except Exception as error:
        _failure(error)


@router.get("/status")
def status(operador: str = Depends(require_config)):
    try:
        return bridge.status()
    except Exception as error:
        _failure(error)


@router.post("/disconnect")
def disconnect(operador: str = Depends(require_config)):
    try:
        return bridge.disconnect()
    except Exception as error:
        _failure(error)


@router.get("/pos")
def list_pos(operador: str = Depends(require_config)):
    """Consulta puntos de venta con las credenciales del servidor central."""
    try:
        if not bridge.connected():
            raise HTTPException(status_code=409, detail="Conectá Mercado Pago primero.")
        token, _, _, _ = mp_service.credenciales()
        if not token:
            raise HTTPException(status_code=502, detail="No se pudo obtener la credencial OAuth.")
        results = mp_service.listar_pos()
        store_cache = {}
        for pos in results:
            store_id = pos.get("store_id")
            if not store_id:
                continue
            if store_id not in store_cache:
                response = requests.get(
                    "https://api.mercadopago.com/stores/" + str(store_id),
                    headers={"Authorization": "Bearer " + token}, timeout=12,
                )
                store_cache[store_id] = (response.json().get("external_id", "")
                                         if response.status_code == 200 else "")
            pos["external_store_id"] = store_cache[store_id]
        return {"results": results}
    except HTTPException:
        raise
    except Exception as error:
        _failure(error)

class CreatePosIn(BaseModel):
    nombre: str = Field(default="POS Nuevo", min_length=1, max_length=45)
    store_id: str = Field(default="", max_length=40)


@router.post("/pos/create")
def create_pos(body: CreatePosIn, operador: str = Depends(require_config)):
    """Crea el POS con OAuth del servidor. No expone el token a la caja cliente."""
    if not bridge.connected():
        raise HTTPException(status_code=409, detail="Conectá Mercado Pago primero.")
    pos_external_id, qr_url, error = mp_service.crear_pos_adicional(body.nombre, body.store_id)
    if error:
        raise HTTPException(status_code=502, detail=error)
    return {"pos_external_id": pos_external_id, "qr_url": qr_url}
