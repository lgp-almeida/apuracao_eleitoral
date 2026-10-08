/* Bloco "Planilha histórica" da aba Candidato: .xlsx por local, zona, bairro e seção (apuracao/planilha.py).
 * Endereço (só com o bloco aberto): &pl=1[&pl_ano=&pl_cargo=&pl_numero=&pl_municipio=&pl_comparar=]. Só preenche:
 * nunca baixa sozinho. */
import { salvarBlob } from "../../componentes/exportar";
import { baixar } from "../../core/api";
import { refs } from "../../core/dom";

const CAMPOS = [["pl_ano", "ano"], ["pl_cargo", "cargo"], ["pl_numero", "numero"], ["pl_municipio", "municipio"],
  ["pl_comparar", "comparar"]] as const;

export function criarPlanilha(gravar: () => void) {
  const r = refs({ caixa: "#caixa-planilha", form: "#form-planilha", ano: "#pl-ano", cargo: "#pl-cargo",
    numero: "#pl-numero", municipio: "#pl-municipio", comparar: "#pl-comparar", msg: "#pl-msg" });
  const caixa = r.caixa as HTMLDetailsElement;
  const campo = (c: (typeof CAMPOS)[number][1]) => r[c] as HTMLInputElement | HTMLSelectElement;

  r.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = new URLSearchParams({ ano: campo("ano").value, cargo: campo("cargo").value, numero: campo("numero").value });
    const mun = campo("municipio").value.trim();
    const cmp = campo("comparar").value.trim();
    if (mun) q.set("municipio", mun);
    if (cmp) q.set("comparar_com", cmp);
    r.msg.textContent = "Gerando planilha…";
    try {
      const { blob } = await baixar(`api/planilha?${q}`, "planilha.xlsx");
      salvarBlob(blob, `planilha_${q.get("numero")}_${q.get("ano")}.xlsx`);
      r.msg.textContent = "Planilha gerada.";
    } catch (err) { r.msg.textContent = `Erro: ${(err as Error).message}`; }
  });
  // mudanças no formulário e abrir/fechar o bloco também vão para o endereço
  caixa.addEventListener("toggle", gravar);
  for (const [, c] of CAMPOS) campo(c).addEventListener("change", gravar);

  return {
    /** A consulta de um candidato preenche o nº da planilha. */
    usarNumero(numero: string): void { campo("numero").value = numero; },
    escrever(q: URLSearchParams): void {
      if (!caixa.open) return;
      q.set("pl", "1");
      for (const [k, c] of CAMPOS) { const v = campo(c).value.trim(); if (v) q.set(k, v); }
    },
    aplicar(q: URLSearchParams): void {
      caixa.open = q.get("pl") === "1";
      if (!caixa.open) return;
      for (const [k, c] of CAMPOS) {
        const v = q.get(k), f = campo(c);
        if (v === null) continue;
        if (f instanceof HTMLSelectElement && ![...f.options].some((o) => o.value === v)) continue;  // valor desconhecido
        f.value = v;
      }
    },
  };
}
