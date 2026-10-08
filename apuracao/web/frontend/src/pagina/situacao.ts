/* Cabeçalho da página: título, selo do ambiente e a situação do coletor (/api/status), a cada ciclo. */
import { api } from "../core/api";
import { el, refs } from "../core/dom";
import { hora, pct } from "../core/formatos";
import { dadosRegua, desenharRegua } from "./regua";

export interface Status {
  uf: string;
  tem_dados: boolean;
  destacar_padrao?: string[] | null;
  cargos?: number[];
  ultimo_boletim?: { titulo: string; gerado_em: string } | null;
  progresso: { ABRANGENCIA: string; UF: string; ELEICAO: number | string; PCT_SECOES_TOTALIZADAS: number | null;
    DT_TOTALIZACAO?: string | null; TOTALIZACAO_FINAL?: boolean }[];
  coletor: {
    ambiente?: string | null; turno?: number | null; ano?: number | null; erro?: string | null;
    ultimo_ciclo_fim?: string | null; ultimo_ciclo_inicio?: string | null;
  };
}

/** Um item por eleição: "RJ (eleição 6257): 45,00% das seções", "Brasil (eleição 6259): 100,00% das seções — final".
 * Cada um vira um elemento próprio no cabeçalho (sem juntar com "·"). */
export const itensProgresso = (s: Pick<Status, "progresso">): string[] => s.progresso.map((p) =>
  `${p.ABRANGENCIA === "br" ? "Brasil" : p.UF} (eleição ${p.ELEICAO}): ${pct(p.PCT_SECOES_TOTALIZADAS)} das seções` +
  (p.TOTALIZACAO_FINAL ? " — final" : ""));

/** Só os cargos presentes nos dados (ex.: 2º turno de 2022 no RJ só tem presidente) nos seletores de cargo. */
export function limitarCargos(cargos: readonly number[], seletores: readonly HTMLSelectElement[]): void {
  if (!cargos.length) return;
  for (const sel of seletores) {
    for (const op of sel.options) op.hidden = op.disabled = !cargos.includes(Number(op.value));
    if (sel.selectedOptions[0]?.disabled) {
      sel.value = String(cargos.find((c) => [...sel.options].some((o) => o.value === String(c))));
      sel.dispatchEvent(new Event("change"));
    }
  }
}

/** @param aoReceber o resto da página com o status novo (UF, ano, turno, destaque padrão…) */
export function criarSituacao(aoReceber: (s: Status) => void) {
  const r = refs({ box: "#situacao", titulo: "#titulo", ambiente: "#ambiente", rotuloLocais: "#rotulo-locais", vazio: "#painel-vazio",
    regua: "#regua", trilho: "#regua-trilho" });
  return async function atualizar(): Promise<void> {
    let s: Status;
    try { s = await api("api/status"); } catch (e) {
      r.box.replaceChildren(el("div", { class: "erro" }, `⚠ Servidor indisponível: ${(e as Error).message}. A página tenta de novo em 1 minuto.`));
      return;
    }
    const ano = s.coletor.ano || 2026;  // resultados históricos (importar_resultado_historico.py) trazem o ano
    r.titulo.textContent = `Apuração ${ano} — ${s.uf}`;
    document.title = `Apuração ${ano} — ${s.uf}`;
    r.rotuloLocais.textContent = ` Locais de votação ${ano}`;
    const amb = s.coletor.ambiente || "?";
    r.ambiente.textContent = amb === "oficial" ? "OFICIAL" : `ambiente: ${amb}`;
    r.ambiente.className = "selo" + (amb === "oficial" ? " oficial" : "");
    const quando = s.coletor.ano ? "Importado em" : "Última coleta";
    const itens = itensProgresso(s);
    const linhas = [itens.length ? el("ul", { class: "situacao-itens" }, itens.map((t) => el("li", {}, t)))
      : el("div", {}, "Sem dados de apuração."),
    el("div", {}, `${quando}: ${hora(s.coletor.ultimo_ciclo_fim || s.coletor.ultimo_ciclo_inicio)}`)];
    if (s.coletor.erro) linhas.push(el("div", { class: "erro" }, "⚠ ", s.coletor.erro));
    r.box.replaceChildren(...linhas);
    r.vazio.hidden = s.tem_dados;
    desenharRegua(r.regua, r.trilho, dadosRegua(s));
    aoReceber(s);
  };
}
