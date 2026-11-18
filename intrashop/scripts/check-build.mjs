import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const target = process.argv[2];
assert.ok(["tauri", "server"].includes(target), "Uso: node scripts/check-build.mjs [tauri|server]");
const base = target === "tauri" ? "/" : "/intrashop/";
const dist = new URL(`../${target === "tauri" ? "dist-tauri" : "dist"}/`, import.meta.url);
const root = decodeURIComponent(dist.pathname);

for (const page of ["index.html", "admin/index.html", "entregas/index.html"]) {
  const file = join(root, page);
  assert.ok(existsSync(file), `Página ausente: ${file}`);
  const html = readFileSync(file, "utf8");
  assert.ok(html.includes(`href="${base}"`),
    `Enlaces de inicio no coinciden con el base de ${target} en ${page}`);

  const urls = [...html.matchAll(/(?:href|src)="(\/[^\"#?]+[^\"]*)"/g)]
    .map((match) => match[1]);
  for (const url of urls) {
    assert.ok(url.startsWith(base),
      `Ruta fuera del base ${base} (${page}): ${url}`);
    const local = url.slice(base.length).split("?")[0].split("#")[0];
    // Rutas amigables de Astro (admin/, entregas/) deben tener index.html.
    const artifact = local.endsWith("/") ? join(root, local, "index.html") : join(root, local);
    assert.ok(existsSync(artifact), `El archivo enlazado no existe: ${url}`);
  }
}
assert.ok(existsSync(join(root, "intrashop-logo.svg")), "Logo no empaquetado");
console.log(`IntraShop ${target}: tres páginas, rutas y recursos correctos (${base})`);
