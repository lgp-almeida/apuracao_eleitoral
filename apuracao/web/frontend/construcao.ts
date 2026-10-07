/* Impressão digital da fonte do front-end, gravada pelo build em ../static/build.json.
 * test_frontend_build.py (pytest, sem Node) refaz a mesma conta: fonte mudou sem build novo = teste falha.
 * Regra: SHA-256 sobre os arquivos em ordem (caminho POSIX relativo), cada um como "caminho\0conteúdo\0". */
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

export const ARQUIVOS_RAIZ = [
  "index.html", "package.json", "package-lock.json", "tsconfig.json", "tsconfig.node.json", "vite.config.ts",
  "construcao.ts",
];
export const PASTAS = ["src", "public"];

function listar(raiz: string, pasta: string): string[] {
  return readdirSync(join(raiz, pasta)).flatMap((nome) => {
    const caminho = join(pasta, nome);
    return statSync(join(raiz, caminho)).isDirectory() ? listar(raiz, caminho) : [caminho];
  });
}

export function arquivosDaFonte(raiz: string): string[] {
  const todos = [...ARQUIVOS_RAIZ, ...PASTAS.flatMap((p) => listar(raiz, p))];
  return todos.map((c) => relative(raiz, join(raiz, c)).split(sep).join("/")).sort();
}

export function impressaoDaFonte(raiz: string): { sha256: string; arquivos: number } {
  const h = createHash("sha256");
  const arquivos = arquivosDaFonte(raiz);
  for (const c of arquivos) {
    h.update(c); h.update("\0"); h.update(readFileSync(join(raiz, c))); h.update("\0");
  }
  return { sha256: h.digest("hex"), arquivos: arquivos.length };
}
