// Lint da página. Regra de segurança em TODO o código, inclusive o legado: texto do TSE nunca vira HTML.
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

const SEM_HTML = "conteúdo vindo dos dados entra por textContent ou el()/svg() (o TSE testa nomes com aspas e símbolos)";
const semHtml = {
  "no-restricted-properties": ["error",
    { property: "innerHTML", message: SEM_HTML },
    { property: "outerHTML", message: SEM_HTML },
    { property: "insertAdjacentHTML", message: SEM_HTML },
    { object: "document", property: "write", message: SEM_HTML },
  ],
  "no-eval": "error",
  "no-implied-eval": "error",
};

export default defineConfig([
  { ignores: ["node_modules/"] },
  {  // código novo: TypeScript estrito
    files: ["src/**/*.ts", "tests/**/*.ts"],
    extends: [js.configs.recommended, tseslint.configs.strict],
    languageOptions: { globals: globals.browser },
    rules: {
      ...semHtml,
      // "_" no começo = não usado de propósito (assinatura de callback, dublê de teste)
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
  {  // configuração do build (Node)
    files: ["*.ts", "*.js"],
    extends: [js.configs.recommended, tseslint.configs.strict],
    languageOptions: { globals: globals.node },
  },
]);
