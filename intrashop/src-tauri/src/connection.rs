//! Kit público del comercio. No extraer archivos ni aceptar CA sin confirmación.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{io::{Read, Cursor}, net::Ipv4Addr, time::Duration};
use x509_parser::{pem::parse_x509_pem, prelude::*};

#[derive(Deserialize)]
struct Manifest {
    schema: String,
    tipo: String,
    servidor: String,
    ca_sha256: String,
}

#[derive(Serialize)]
pub struct VerifiedKit {
    pub servidor: String,
    pub huella: String,
    #[serde(skip)]
    pem: Vec<u8>,
}

fn private_url(value: &str) -> Result<String, String> {
    let ip = value.strip_prefix("https://").ok_or("Se requiere HTTPS")?
        .parse::<Ipv4Addr>().map_err(|_| "Se requiere una IPv4 LAN")?;
    if !ip.is_private() {
        return Err("La dirección no pertenece a una red privada".into());
    }
    Ok(format!("https://{ip}"))
}

fn read_entry<R: Read + std::io::Seek>(
    archive: &mut zip::ZipArchive<R>, name: &str, limit: usize,
) -> Result<Vec<u8>, String> {
    let mut count = 0;
    for i in 0..archive.len() {
        if archive.by_index(i).map_err(|_| "ZIP inválido")?.name() == name {
            count += 1;
        }
    }
    if count != 1 { return Err("Entrada ausente o duplicada".into()); }
    let entry = archive.by_name(name).map_err(|_| "Kit incompleto")?;
    if entry.size() > limit as u64 {
        return Err("Entrada demasiado grande".into());
    }
    let mut bytes = Vec::new();
    entry.take(limit as u64 + 1).read_to_end(&mut bytes)
        .map_err(|_| "No se pudo leer el kit")?;
    if bytes.len() > limit { return Err("Entrada demasiado grande".into()); }
    Ok(bytes)
}

pub fn read_kit(bytes: &[u8], confirmed: &str) -> Result<VerifiedKit, String> {
    if bytes.len() > 1024 * 1024 { return Err("Kit demasiado grande".into()); }
    let mut archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(|_| "ZIP inválido")?;
    let manifest: Manifest = serde_json::from_slice(&read_entry(&mut archive, "conexion.json", 16384)?)
        .map_err(|_| "Manifest inválido")?;
    if manifest.schema != "intrashop-client-kit/v1" || manifest.tipo != "totem" {
        return Err("Seleccioná un kit de tótem IntraShop".into());
    }
    let servidor = private_url(&manifest.servidor)?;
    let pem = read_entry(&mut archive, "intrashop-root-ca.crt", 32768)?;
    let pem_text = std::str::from_utf8(&pem).map_err(|_| "Certificado inválido")?;
    if !pem_text.trim_start().starts_with("-----BEGIN CERTIFICATE-----") ||
        pem_text.matches("-----BEGIN").count() != 1 {
        return Err("El kit debe contener solamente un certificado público".into());
    }
    let (remaining, cert_pem) = parse_x509_pem(&pem).map_err(|_| "Certificado inválido")?;
    if cert_pem.label != "CERTIFICATE" || !remaining.iter().all(|b| b.is_ascii_whitespace()) {
        return Err("El kit debe contener solamente un certificado público".into());
    }
    let (rest, cert) = X509Certificate::from_der(&cert_pem.contents).map_err(|_| "Certificado inválido")?;
    if !rest.is_empty() || !cert.is_ca() || !cert.validity().is_valid() {
        return Err("La CA no es válida".into());
    }
    let huella = format!("{:X}", Sha256::digest(&cert_pem.contents));
    let confirmed: String = confirmed.chars().filter(|c| !c.is_whitespace() && *c != ':').collect();
    if huella != manifest.ca_sha256.to_ascii_uppercase() || huella != confirmed.to_ascii_uppercase() {
        return Err("La huella no coincide con POS Server".into());
    }
    Ok(VerifiedKit { servidor, huella, pem })
}

pub fn client_for(kit: &VerifiedKit) -> Result<reqwest::Client, String> {
    let ca = reqwest::Certificate::from_pem(&kit.pem).map_err(|_| "CA inválida")?;
    reqwest::Client::builder()
        .tls_built_in_root_certs(false)
        .add_root_certificate(ca)
        .https_only(true)
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(8))
        .cookie_store(false)
        .build().map_err(|_| "No se pudo preparar TLS".into())
}

pub async fn verify_server(kit: &VerifiedKit) -> Result<(), String> {
    let client = client_for(kit)?;
    let mut response = client.get(format!("{}/health", kit.servidor)).send().await
        .map_err(|_| "No se pudo verificar la conexión HTTPS con POS Server")?;
    if response.status() != reqwest::StatusCode::OK {
        return Err("POS Server no está disponible".into());
    }
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "Respuesta inválida")? {
        if body.len() + chunk.len() > 16384 { return Err("Respuesta demasiado grande".into()); }
        body.extend_from_slice(&chunk);
    }
    let data: serde_json::Value = serde_json::from_slice(&body).map_err(|_| "Respuesta inválida")?;
    if data["service"] != "pos-lan" || data["ok"] != true {
        return Err("El destino no es POS Server".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_private_https_ip() {
        assert_eq!(private_url("https://192.168.1.5").unwrap(), "https://192.168.1.5");
        for url in ["http://192.168.1.5", "https://8.8.8.8", "https://127.0.0.1",
                    "https://192.168.1.5/path", "https://user@192.168.1.5", "https://10.0.0.1:8000"] {
            assert!(private_url(url).is_err(), "{url}");
        }
    }
    #[test]
    fn invalid_zip_rejected() {
        assert!(read_kit(b"invalid", "00").is_err());
    }
}


// Only the storefront's fixed API surface, never an arbitrary URL or admin path.
pub fn allowed_request(method: &str, path: &str) -> bool {
    if path.len() > 4096 || path.contains('#') || path.contains('\\') || path.contains('\r') || path.contains('\n') {
        return false;
    }
    let route = path.split('?').next().unwrap_or("");
    match (method, route) {
        ("GET", "/tienda/productos" | "/tienda/totems/identity") => true,
        ("POST", "/tienda/totems/pair" | "/tienda/checkout") => path == route,
        _ => {
            let Some(rest) = route.strip_prefix("/tienda/checkout/") else { return false; };
            let id = if method == "POST" {
                let Some(id) = rest.strip_suffix("/cancel") else { return false; };
                id
            } else if method == "GET" { rest } else { return false; };
            path == route && !id.is_empty() && id.len() <= 80 &&
                id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
        }
    }
}

#[cfg(test)]
#[test]
fn storefront_only() {
    assert!(allowed_request("GET", "/tienda/productos?termino=pan"));
    assert!(allowed_request("POST", "/tienda/checkout/a-b/cancel"));
    assert!(!allowed_request("GET", "/tienda/admin/checkouts-pending"));
    assert!(!allowed_request("GET", "/tienda/checkout/../admin"));
    assert!(!allowed_request("POST", "/tienda/checkout/a%2fb/cancel"));
    assert!(!allowed_request("GET", "https://192.168.1.4/health"));
}


pub fn allowed_image(path: &str) -> bool {
    path.strip_prefix("/tienda/productos/")
        .and_then(|s| s.strip_suffix("/imagen"))
        .map(|id| !id.is_empty() && id.len() <= 20 && id.bytes().all(|b| b.is_ascii_digit()))
        .unwrap_or(false)
}

#[test]
fn image_path_is_restricted() {
    assert!(allowed_image("/tienda/productos/42/imagen"));
    assert!(!allowed_image("/tienda/productos/../imagen"));
    assert!(!allowed_image("/tienda/productos/42/imagen?url=http://other"));
}
