// Copy the few front-end files we serve ourselves from node_modules into static/vendor.
import { cpSync, mkdirSync } from "node:fs";

const out = "static/vendor";
mkdirSync(`${out}/leaflet/images`, { recursive: true });
mkdirSync(`${out}/fonts`, { recursive: true });
const copies = [
  ["node_modules/htmx.org/dist/htmx.min.js", `${out}/htmx.min.js`],
  ["node_modules/@alpinejs/csp/dist/cdn.min.js", `${out}/alpine-csp.min.js`],
  ["node_modules/leaflet/dist/leaflet.js", `${out}/leaflet/leaflet.js`],
  // leaflet.js ends with a sourceMappingURL; WhiteNoise's manifest storage fails without it.
  ["node_modules/leaflet/dist/leaflet.js.map", `${out}/leaflet/leaflet.js.map`],
  ["node_modules/leaflet/dist/leaflet.css", `${out}/leaflet/leaflet.css`],
  ["node_modules/leaflet/dist/images", `${out}/leaflet/images`],
  ["node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2", `${out}/fonts/inter-latin-wght-normal.woff2`],
  ["node_modules/@fontsource-variable/inter/files/inter-latin-ext-wght-normal.woff2", `${out}/fonts/inter-latin-ext-wght-normal.woff2`],
];
for (const [from, to] of copies) cpSync(from, to, { recursive: true });
console.log("vendored", copies.length, "items into", out);
