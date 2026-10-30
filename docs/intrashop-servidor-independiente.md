# Servidor POS independiente (Linux)

El proceso `pos_server.py` ejecuta FastAPI sin abrir la aplicación de escritorio Flet. Comparte la SQLite y los ajustes del POS. No debe ejecutarse simultáneamente con otra instancia del servidor en el mismo puerto.

## Ejecutar manualmente

```bash
python pos_server.py --host 0.0.0.0 --port 8000
```

## systemd (Ubuntu)

Crear `~/.config/systemd/user/intrashop-pos.service` con las rutas reales de tu instalación:

```ini
[Unit]
Description=Servidor LAN IntraShop / POS
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/RUTA/AL/REPOSITORIO
ExecStart=/RUTA/AL/VENV/bin/python /RUTA/AL/REPOSITORIO/pos_server.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now intrashop-pos.service
systemctl --user status intrashop-pos.service
```

Para mantener el servicio después de cerrar sesión, configurar `loginctl enable-linger` para el usuario correspondiente si el entorno lo permite.

**Seguridad:** exponer el puerto únicamente en la LAN de confianza mediante firewall. Cambiar la API key predeterminada del POS antes de usarlo con clientes. No publicar el puerto 8000 en Internet.

## Tienda Astro

En `intrashop/`, configurar valores iniciales opcionales en `.env` antes de compilar:

```env
PUBLIC_POS_URL=http://192.168.1.100:8000
```

La API key se configura desde `/admin` en cada dispositivo. `PUBLIC_POS_API_KEY` existe como alternativa para entornos cerrados, pero cualquier clave `PUBLIC_` queda expuesta en el bundle web y no debe usarse como secreto de producción.

La tienda usa `localStorage` por dispositivo. Si el navegador se borra, se debe volver a configurar la conexión.

La administración de servicios desde los ajustes Flet del POS aún no está integrada; el servicio se gestiona con `systemctl` de forma independiente.
