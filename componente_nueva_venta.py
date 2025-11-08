# componente_nueva_venta.py
import flet as ft

class NuevaVentaView(ft.Container):
    def __init__(self, db_manager, caja_id, on_confirmar=None, filter_mode=None):
        super().__init__()
        self.db = db_manager
        self.caja_id = caja_id
        self.on_confirmar = on_confirmar
        self.open = False  # property para overlay
        self.filter_mode = filter_mode  # 'codigo' o 'descripcion' o None

        # estado
        self.resultados = []
        self.carrito = []

    def _buscar(self, texto, modo):
        # TODO: llamar a la DB; aquí stub con coincidencias simples
        items = [
            {"codigo": "123", "descripcion": "Libro A", "precio": 120.0, "stock": 5},
            {"codigo": "456", "descripcion": "Goma", "precio": 10.0, "stock": 20},
            {"codigo": "789", "descripcion": "Lápiz", "precio": 25.5, "stock": 10},
        ]
        if not texto:
            return items
        if modo == "codigo":
            return [i for i in items if i["codigo"] == texto]
        else:
            return [i for i in items if texto.lower() in i["descripcion"].lower()]

    def build(self):
        self.input = ft.TextField(label="Buscar producto", expand=True, on_submit=self._on_submit)
        self.selector = ft.Dropdown(
            width=180,
            value=self.filter_mode if self.filter_mode in ("codigo", "descripcion") else "descripcion",
            options=[ft.dropdown.Option("descripcion", "Descripción"), ft.dropdown.Option("codigo", "Código")]
        )
        self.result_list = ft.Column()
        self.carrito_list = ft.Column()
        add_btn = ft.ElevatedButton("Agregar al carrito", on_click=self._agregar_desde_input)
        confirm_btn = ft.ElevatedButton("Confirmar venta", bgcolor=ft.Colors.GREEN, on_click=self._confirmar)
        abort_btn = ft.ElevatedButton("Abortar", bgcolor=ft.Colors.RED, on_click=self._abort)

        # Construir contenido del modal
        content = ft.Column([
            ft.Row([self.input, self.selector, add_btn]),
            ft.Text("Resultados:"),
            self.result_list,
            ft.Divider(),
            ft.Text("Carrito:"),
            self.carrito_list,
            ft.Row([abort_btn, confirm_btn], alignment=ft.MainAxisAlignment.END)
        ], spacing=10, width=700, height=600)

        # Inicializar búsqueda (si se inició con filtro por código, ponemos foco)
        return ft.Container(content, padding=20, bgcolor=ft.Colors.WHITE, border_radius=4)

    def _render_resultados(self, resultados):
        self.result_list.controls.clear()
        for r in resultados:
            btn = ft.ElevatedButton(f"{r['descripcion']} - ${r['precio']} (stk {r['stock']})",
                on_click=lambda e, item=r: self._add_item(item))
            self.result_list.controls.append(btn)
        self.update()

    def _render_carrito(self):
        self.carrito_list.controls.clear()
        for it in self.carrito:
            self.carrito_list.controls.append(ft.Text(f"{it['descripcion']} x{it.get('cantidad',1)} - ${it['precio']}"))
        self.update()

    def _on_submit(self, e):
        modo = self.selector.value
        texto = e.control.value
        resultados = self._buscar(texto, modo)
        self._render_resultados(resultados)
        # Si modo es 'codigo' y hay un resultado único, agregar al carrito automáticamente
        if modo == "codigo" and len(resultados) == 1:
            self._add_item(resultados[0])

    def _agregar_desde_input(self, e):
        # Añade según el texto actual y el selector
        texto = self.input.value
        resultados = self._buscar(texto, self.selector.value)
        if resultados:
            self._add_item(resultados[0])

    def _add_item(self, item):
        # Agregar copia simple
        self.carrito.append(dict(item, cantidad=1))
        self._render_carrito()

    def _confirmar(self, e):
        # Aquí se debería guardar la venta e imprimir si corresponde
        # Llamamos al callback y cerramos el modal
        if self.on_confirmar:
            self.on_confirmar()
        # cerrar overlay: el caller debe remover este container de overlay; como convención, setear open False
        self.open = False
        self.page.update()

    def _abort(self, e):
        self.open = False
        self.page.update()
