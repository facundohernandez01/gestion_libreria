"""Prueba funcional real de Astro en Chromium.

Levantar antes: npm run preview -- --host 127.0.0.1 --port 4173 (intrashop/).
Se intercepta solo Mercado Pago/DB: no realiza cobros reales ni usa libreria.db.
"""
import json
import os

from playwright.sync_api import sync_playwright


PRODUCT = {
    "id": 41, "codigo": "TEST-PROD", "descripcion": "Hamburguesa de prueba",
    "categoria": "Comida", "marca": "Test", "precio_lista": 3500,
    "stock_actual": 10, "imagen_url": "",
}


def test_carrito_borrado_qr_cancelacion_y_emparejamiento():
    authorized = {"value": False}
    cancellation = {"count": 0}
    routes = []

    def handler(route):
        req = route.request
        path = req.url.split("/tienda/", 1)[1]
        routes.append((req.method, path))
        headers = {
            "Access-Control-Allow-Origin": "http://127.0.0.1:4173",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
        if req.method == "OPTIONS":
            route.fulfill(status=204, headers=headers)
            return
        if path.startswith("totems/identity"):
            body = {
                "paired": True, "authorized": authorized["value"],
                "qr_assigned": True, "id": "totem-001",
                "nombre": "Tótem 001", "ip": "192.168.1.50",
            }
        elif path.startswith("totems/pair"):
            assert req.method == "POST"
            assert json.loads(req.post_data)["codigo"] == "ABCDE-FGHIJ"
            authorized["value"] = True
            body = {"ok": True, "totem_id": "totem-001"}
        elif path.startswith("productos"):
            body = [PRODUCT]
        elif path.startswith("checkout") and path.endswith("/cancel"):
            cancellation["count"] += 1
            body = {"ok": True, "status": "cancelling"}
        elif path.startswith("checkout/"):
            body = {"status": "waiting", "qr_url": "https://example.com/test-qr.svg",
                    "message": "Esperando pago de prueba"}
        elif path == "checkout":
            assert req.method == "POST"
            payload = json.loads(req.post_data)
            assert payload["totem_id"] == "totem-001"
            assert payload["items"] == [{"producto_id": 41, "cantidad": 1}]
            body = {
                "checkout_id": "test-qr-001", "total": 3500,
                "items": [{
                    "producto_id": 41, "cantidad": 1,
                    "descripcion": PRODUCT["descripcion"], "precio_unitario": 3500,
                }],
            }
        else:
            route.fulfill(status=404, headers=headers, json={"detail": "mock unknown route"})
            return
        route.fulfill(status=200, headers=headers, json=body)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.route("**:8000/tienda/**", handler)
        page.goto(
            os.environ.get("INTRASHOP_E2E_URL", "http://127.0.0.1:4173/intrashop/"),
            wait_until="networkidle",
        )
        page.get_by_text("Hamburguesa de prueba").first.wait_for()
        assert page.locator("#pairing-panel").is_visible()
        assert page.locator("#checkout").is_disabled()
        page.locator("#pairing-code").fill("ABCDE-FGHIJ")
        page.locator("#pairing-submit").click()
        page.get_by_text("QR listo, dispositivo autorizado").wait_for()
        assert page.locator("#pairing-panel").is_hidden()

        page.locator("[data-add='41']").click()
        assert page.locator("#cart-drawer").get_attribute("aria-hidden") == "false"
        assert page.locator("#cart-count").inner_text() == "1"
        page.locator("[data-remove='41']").click()
        assert page.locator("#cart-count").inner_text() == "0"
        assert page.locator("#cart-items").get_by_text("Tu carrito está vacío").is_visible()
        assert page.locator("#checkout").is_disabled()

        page.locator("#cart-close").click()
        page.locator("[data-add='41']").click()
        assert page.locator("#checkout").is_enabled()
        page.locator("#checkout").click()
        page.locator("#payment-modal").wait_for(state="visible")
        page.locator("#payment-cancel").click()
        page.locator("#payment-modal").wait_for(state="hidden")
        page.wait_for_function("() => window.document.querySelector('#payment-modal').hidden")
        # HTTP cancel va en segundo plano, no bloquea el cierre visual.
        page.wait_for_timeout(350)
        assert cancellation["count"] == 1
        assert ("POST", "totems/pair") in routes
        browser.close()
