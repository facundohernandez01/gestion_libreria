#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod connection;
use std::sync::Mutex;
use tauri::{State, Manager, AppHandle};
use serde::{Serialize, Deserialize};
use std::{fs, path::PathBuf};
use base64::Engine;

struct Commerce {
    base: String,
    client: reqwest::Client,
    fingerprint: String,
    cookie: Option<String>,
}
#[derive(Default)]
struct Session(Mutex<Option<Commerce>>);

#[derive(Serialize, Deserialize)]
struct Profile { bytes: Vec<u8>, huella: String }

fn profile_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|_| "No se encontró la configuración local")?;
    fs::create_dir_all(&dir).map_err(|_| "No se pudo preparar la configuración local")?;
    Ok(dir.join("commerce.json"))
}
fn secret_entry(base: &str, fingerprint: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new("com.gestionlibreria.intrashop", &format!("{base}|{fingerprint}"))
        .map_err(|_| "No se pudo acceder al almacén seguro del sistema".into())
}
fn valid_cookie(value: &str) -> bool {
    value.len() >= 32 && value.len() <= 128 && value.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}
fn restore_cookie(base: &str, fingerprint: &str) -> Option<String> {
    secret_entry(base, fingerprint).ok()?.get_password().ok().filter(|v| valid_cookie(v))
}
#[tauri::command]
async fn restaurar_comercio(app: AppHandle, state: State<'_, Session>) -> Result<Option<connection::VerifiedKit>, String> {
    let path = profile_path(&app)?;
    let data = match fs::read(path) {
        Ok(data) => data,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err("No se pudo leer la conexión guardada".into()),
    };
    if data.len() > 5 * 1024 * 1024 { return Err("Perfil local inválido".into()); }
    let profile: Profile = serde_json::from_slice(&data).map_err(|_| "Perfil local inválido")?;
    let kit = connection::read_kit(&profile.bytes, &profile.huella)?;
    let client = connection::client_for(&kit)?;
    let cookie = restore_cookie(&kit.servidor, &kit.huella);
    *state.0.lock().map_err(|_| "Estado de conexión inválido")? = Some(Commerce {
        base: kit.servidor.clone(), fingerprint: kit.huella.clone(), client, cookie
    });
    Ok(Some(kit))
}

#[tauri::command]
async fn verificar_kit_totem(bytes: Vec<u8>, huella: String, app: AppHandle, state: State<'_, Session>) -> Result<connection::VerifiedKit, String> {
    let kit = connection::read_kit(&bytes, &huella)?;
    connection::verify_server(&kit).await?;
    let client = connection::client_for(&kit)?;
    let path = profile_path(&app)?;
    let data = serde_json::to_vec(&Profile {bytes, huella: kit.huella.clone()}).map_err(|_| "Perfil inválido")?;
    // Public CA and address only. The session is kept in the OS credential store.
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, data).map_err(|_| "No se pudo guardar la conexión")?;
    fs::rename(&tmp, &path).map_err(|_| "No se pudo guardar la conexión")?;
    let cookie = restore_cookie(&kit.servidor, &kit.huella);
    *state.0.lock().map_err(|_| "Estado de conexión inválido")? = Some(Commerce {
        base: kit.servidor.clone(), fingerprint: kit.huella.clone(), client, cookie
    });
    Ok(kit)
}

#[tauri::command]
async fn tienda_request(method: String, path: String, body: Option<String>, state: State<'_, Session>) -> Result<serde_json::Value, String> {
    if !connection::allowed_request(&method, &path) { return Err("Operación no autorizada".into()); }
    let (base, client, fingerprint, cookie) = {
        let guard = state.0.lock().map_err(|_| "Estado de conexión inválido")?;
        let commerce = guard.as_ref().ok_or("Importá el kit del comercio primero")?;
        (commerce.base.clone(), commerce.client.clone(), commerce.fingerprint.clone(), commerce.cookie.clone())
    };
    let verb = reqwest::Method::from_bytes(method.as_bytes()).map_err(|_| "Método inválido")?;
    let mut request = client.request(verb, format!("{base}{path}"));
    if let Some(cookie) = cookie { request = request.header("Cookie", format!("intrashop_terminal={cookie}")); }
    if let Some(value) = body {
        if method != "POST" || value.len() > 131072 { return Err("Solicitud inválida".into()); }
        request = request.header("Content-Type", "application/json").body(value);
    }
    let mut response = request.send().await.map_err(|_| "Sin conexión segura a POS Server")?;
    let status = response.status().as_u16();
    if path == "/tienda/totems/pair" && status == 200 {
        let value = response.headers().get_all(reqwest::header::SET_COOKIE).iter()
            .filter_map(|h| h.to_str().ok())
            .filter_map(|h| h.split(';').next())
            .find_map(|h| h.strip_prefix("intrashop_terminal="))
            .filter(|v| valid_cookie(v))
            .ok_or("POS Server no devolvió una sesión válida")?.to_owned();
        let mut guard = state.0.lock().map_err(|_| "Estado de conexión inválido")?;
        let commerce = guard.as_mut().ok_or("Conexión modificada")?;
        if commerce.base != base || commerce.fingerprint != fingerprint { return Err("Conexión modificada".into()); }
        commerce.cookie = Some(value.clone());
        // Keep the current session usable if the OS vault is unavailable; the
        // caller receives an explicit warning rather than a plaintext fallback.
        if secret_entry(&base, &fingerprint).and_then(|e| e.set_password(&value).map_err(|_| "No se pudo guardar la sesión".into())).is_err() {
            return Ok(serde_json::json!({"status":200,"body":{"ok":true,"session_persisted":false}}));
        }
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "Respuesta incompleta")? {
        if bytes.len() + chunk.len() > 8 * 1024 * 1024 { return Err("Respuesta demasiado grande".into()); }
        bytes.extend_from_slice(&chunk);
    }
    let data: serde_json::Value = serde_json::from_slice(&bytes).map_err(|_| "Respuesta inválida de POS Server")?;
    Ok(serde_json::json!({"status": status, "body": data}))
}

#[tauri::command]
async fn tienda_imagen(path: String, state: State<'_, Session>) -> Result<String, String> {
    if !connection::allowed_image(&path) { return Err("Imagen no autorizada".into()); }
    let (base, client) = {
        let guard = state.0.lock().map_err(|_| "Estado de conexión inválido")?;
        let commerce = guard.as_ref().ok_or("Importá el kit primero")?;
        (commerce.base.clone(), commerce.client.clone())
    };
    let mut response = client.get(format!("{base}{path}")).send().await.map_err(|_| "Imagen no disponible")?;
    if !response.status().is_success() { return Err("Imagen no disponible".into()); }
    let mime = response.headers().get(reqwest::header::CONTENT_TYPE)
        .and_then(|h| h.to_str().ok()).unwrap_or("").split(';').next().unwrap_or("").to_owned();
    if !["image/jpeg", "image/png", "image/webp", "image/gif"].contains(&mime.as_str()) {
        return Err("Formato de imagen no admitido".into());
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "Imagen incompleta")? {
        if bytes.len() + chunk.len() > 5 * 1024 * 1024 { return Err("Imagen demasiado grande".into()); }
        bytes.extend_from_slice(&chunk);
    }
    Ok(format!("data:{mime};base64,{}", base64::engine::general_purpose::STANDARD.encode(bytes)))
}

fn main() {
    tauri::Builder::default()
        .manage(Session::default())
        .invoke_handler(tauri::generate_handler![verificar_kit_totem, restaurar_comercio, tienda_request, tienda_imagen])
        .run(tauri::generate_context!())
        .expect("error while running IntraShop");
}
