/* Seletor de UF do site de várias UFs: cada uma montada em /<uf>/ e as disponíveis em /ufs.json. No site de uma
 * UF esse arquivo não existe e o seletor fica escondido. Trocar de UF mantém a aba e o endereço (#…). */
import { api } from "../core/api";
import { el, refs } from "../core/dom";

interface Ufs { ufs: { uf: string; nome: string; disponivel: boolean }[] }

export async function iniciarSeletorUf(): Promise<void> {
  let d: Ufs;
  try { d = await api("../ufs.json"); } catch { return; }  // site de uma UF: não há ufs.json
  const r = refs({ sel: "#seletor-uf", rotulo: "#seletor-uf-rotulo" });
  const sel = r.sel as HTMLSelectElement;
  const atual = location.pathname.split("/").filter(Boolean).at(-1)?.toUpperCase();
  sel.replaceChildren(...d.ufs.map((u) => el("option", { value: u.uf, disabled: !u.disponivel, selected: u.uf === atual },
    `${u.uf} — ${u.nome}${u.disponivel ? "" : " (sem dados)"}`)));
  sel.addEventListener("change", () => { location.href = `../${sel.value.toLowerCase()}/${location.hash}`; });
  r.rotulo.hidden = false;
}
