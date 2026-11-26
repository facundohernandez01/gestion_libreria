#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod connection;

// Sólo inspección y verificación; todavía no cambia el transporte de checkout.
#[tauri::command]
async fn verificar_kit_totem(bytes: Vec<u8>, huella: String) -> Result<connection::VerifiedKit, String> {
    let kit = connection::read_kit(&bytes, &huella)?;
    connection::verify_server(&kit).await?;
    Ok(kit)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![verificar_kit_totem])
        .run(tauri::generate_context!())
        .expect("error while running IntraShop");
}
