#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod connection;
use std::sync::Mutex;
use tauri::State;

struct Commerce {
    base: String,
    client: reqwest::Client,
}
#[derive(Default)]
struct Session(Mutex<Option<Commerce>>);

#[tauri::command]
async fn verificar_kit_totem(bytes: Vec<u8>, huella: String, state: State<'_, Session>) -> Result<connection::VerifiedKit, String> {
    let kit = connection::read_kit(&bytes, &huella)?;
    connection::verify_server(&kit).await?;
    let client = connection::client_for(&kit)?;
    *state.0.lock().map_err(|_| "Estado de conexión inválido")? = Some(Commerce {base: kit.servidor.clone(), client});
    Ok(kit)
}

#[tauri::command]
async fn tienda_request(method: String, path: String, body: Option<String>, state: State<'_, Session>) -> Result<serde_json::Value, String> {
    if !connection::allowed_request(&method, &path) { return Err("Operación no autorizada".into()); }
    let (base, client) = {
        let guard = state.0.lock().map_err(|_| "Estado de conexión inválido")?;
        let commerce = guard.as_ref().ok_or("Importá el kit del comercio primero")?;
        (commerce.base.clone(), commerce.client.clone())
    };
    let verb = reqwest::Method::from_bytes(method.as_bytes()).map_err(|_| "Método inválido")?;
    let mut request = client.request(verb, format!("{base}{path}"));
    if let Some(value) = body {
        if method != "POST" || value.len() > 131072 { return Err("Solicitud inválida".into()); }
        request = request.header("Content-Type", "application/json").body(value);
    }
    let mut response = request.send().await.map_err(|_| "Sin conexión segura a POS Server")?;
    let status = response.status().as_u16();
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "Respuesta incompleta")? {
        if bytes.len() + chunk.len() > 8 * 1024 * 1024 { return Err("Respuesta demasiado grande".into()); }
        bytes.extend_from_slice(&chunk);
    }
    let data: serde_json::Value = serde_json::from_slice(&bytes).map_err(|_| "Respuesta inválida de POS Server")?;
    Ok(serde_json::json!({"status": status, "body": data}))
}

fn main() {
    tauri::Builder::default()
        .manage(Session::default())
        .invoke_handler(tauri::generate_handler![verificar_kit_totem, tienda_request])
        .run(tauri::generate_context!())
        .expect("error while running IntraShop");
}
