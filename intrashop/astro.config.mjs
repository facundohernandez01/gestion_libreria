import { defineConfig } from "astro/config";

export default defineConfig({
  server: { host: "0.0.0.0", port: 4321 },
  // POS Server publica bajo /intrashop/; Tauri aloja los archivos en /.
  // La variable sólo se activa desde dev:tauri/build:tauri, no en la web LAN.
  base: process.env.INTRASHOP_TARGET === "tauri" ? "/" : "/intrashop/",
  output: "static"
});
