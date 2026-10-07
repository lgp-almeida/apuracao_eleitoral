import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";
import { impressaoDaFonte } from "./construcao.ts";

const RAIZ = import.meta.dirname;
const SAIDA = resolve(RAIZ, "../static");
// site em `npm run dev`: as rotas de dados vão para o site Python já no ar (python site_apuracao.py ...)
const SITE = process.env.APURACAO_SITE ?? "http://localhost:8000";

/** Grava build.json com a impressão digital da fonte (conferida por test_frontend_build.py). */
function impressaoDigital(): Plugin {
  return {
    name: "apuracao-impressao-digital",
    apply: "build",
    closeBundle() {
      writeFileSync(resolve(SAIDA, "build.json"), JSON.stringify(impressaoDaFonte(RAIZ), null, 2) + "\n");
    },
  };
}

export default defineConfig({
  root: RAIZ,
  // caminhos RELATIVOS: o site de várias UFs monta cada uma em /<uf>/ (apuracao/web/multi.py)
  base: "./",
  build: { outDir: SAIDA, emptyOutDir: true, assetsDir: "assets", sourcemap: false },
  server: { proxy: { "/api": SITE, "/geo": SITE, "/ufs.json": SITE } },
  plugins: [impressaoDigital()],
});
