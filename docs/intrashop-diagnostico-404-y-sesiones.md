# Diagnóstico de entregas IntraShop: HTTP 404

La ruta de la API en esta rama es `GET /tienda/admin/entregas?estado=`.
Un **404** significa que el proceso que atiende el puerto no cargó esa ruta,
aunque el archivo exista tras ejecutar `git pull`.

## Verificar en el servidor POS

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/openapi.json | grep -o '/tienda/admin/entregas'
sudo ss -ltnp '( sport = :8000 )'
```

Si `/health` no incluye `intrashop-entregas-v1` en `capabilities`,
se está ejecutando un proceso anterior. Reiniciá **esa instancia**,
ya sea servicio systemd, servicio Windows o servidor integrado al POS.
No levantes otra instancia sobre el puerto ocupado.

En Ubuntu, si se instaló el servicio documentado:

```bash
systemctl --user restart intrashop-pos.service
systemctl --user status intrashop-pos.service
```

Si el servidor se inicia desde Flet, cerrá el POS servidor y volvelo a abrir.
Las terminales cliente no necesitan reiniciar el servidor; sí deben reiniciar
su propio POS al cambiar de modo de conexión.

## Autenticación

Los endpoints de entrega ya no aceptan únicamente la API key compartida.
Se necesita iniciar sesión como usuario POS con permiso `ENTREGAS_INTRASHOP`.

```bash
curl -X POST http://127.0.0.1:8000/pos/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"usuario":"OPERADOR","clave":"CONTRASEÑA"}'
```

Usar el `access_token` devuelto:

```bash
curl http://127.0.0.1:8000/tienda/admin/entregas \
  -H 'Authorization: Bearer TOKEN'
```

Un `401` indica falta de sesión o sesión vencida; un `403`, usuario
sin permiso; un `404`, ruta ausente en el servidor en ejecución.

En la tienda web, `/entregas` solicita usuario y contraseña POS.
No almacenar el token ni la contraseña en la configuración pública Astro.

## Persistencia de red

El modo `local / servidor / cliente` y `SERVER_URL` se guardan en la
configuración SQLite de **cada terminal**. La configuración local tiene
prioridad sobre los valores de `.env`. También se pueden editar antes
del login con «Configurar conexión LAN de esta terminal». El cambio de
modo requiere reiniciar la aplicación; la pantalla de Ajustes distingue
la selección guardada de la conexión activa.

## Límites de seguridad

Los tokens de operador duran hasta 8 horas y están en memoria del proceso
servidor: reiniciar invalida las sesiones. El servidor reevalúa los permisos
en cada operación de entrega.

**Pendiente para producción:** eliminar contraseñas heredadas en texto plano,
reemplazarlas por hashes de contraseña y usar HTTPS en redes no confiables.
Las rutas generales del POS que todavía dependen de la API key compartida
requieren una migración de autorización propia. No exponer la API al exterior.
