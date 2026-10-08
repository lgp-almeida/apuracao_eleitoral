/* Exportar um mapa (PNG/SVG/JPEG): o servidor redesenha com as cores e a legenda que a PÁGINA usou
 * (POST api/exportar/mapa, apuracao/web/exportar.py). */
import { cor } from "../../core/dom";
import { baixar } from "../../core/api";
import { salvarBlob } from "../exportar";
import type { ExportacaoMapa, MapaApuracao } from "./tipos";

export interface ContextoExportacao {
  /** "mapas" ou "comparacao" (vai no nome do arquivo). */
  aba: string;
  uf: string;
  /** Rótulo do cargo do mapa (subtítulo padrão). */
  cargo: string;
  /** "Simulado", "Oficial"… (subtítulo padrão). */
  ambiente: string;
  /** Endereço completo da página (fica no rodapé do arquivo). */
  link: string;
}

export type Cores = { fundo: string; texto: string; sem_dado: string; contorno: string };

const coresDaPagina = (): Cores => ({ fundo: cor("--superficie"), texto: cor("--texto"), sem_dado: cor("--sem-dado"),
  contorno: cor("--superficie") });

/** Corpo do pedido de exportação. */
export function corpoExportacao(e: ExportacaoMapa, formato: string, c: ContextoExportacao, cores: Cores) {
  return {
    formato, camada: e.camada, titulo: e.titulo, ano: e.ano ?? null,
    subtitulo: e.camada === "locais" ? `${c.uf} · locais de votação (cadastro de ${e.ano}); área do ponto ∝ eleitorado`
      : e.camada === "areas" ? `${c.uf} · áreas de ponderação do Censo 2022 (IBGE)`
        : e.subtitulo ? `${e.subtitulo} — ${c.uf} · bairros do IBGE`
          : `${c.cargo} — ${c.uf} · ${c.ambiente}`,
    nome: `mapa ${c.aba} ${e.titulo}`, cores: e.cores, legenda: e.legenda, ...cores,
    extras: [...(e.extras || []), `Link: ${c.link}`],
  };
}

/** Pede o arquivo ao servidor e o salva; `msg` mostra o andamento (some em 5 s). */
export async function exportarMapa(m: MapaApuracao | null | undefined, formato: string, msg: HTMLElement,
    c: ContextoExportacao): Promise<void> {
  if (!m || !m._export) { msg.textContent = " desenhe o mapa primeiro."; return; }
  const corpo = corpoExportacao(m._export, formato, c, coresDaPagina());
  msg.textContent = " gerando…";
  try {
    const { blob, nome } = await baixar("api/exportar/mapa", `mapa.${formato}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    salvarBlob(blob, nome);
    msg.textContent = " arquivo gerado.";
  } catch (e) { msg.textContent = ` erro: ${(e as Error).message}`; }
  setTimeout(() => { msg.textContent = ""; }, 5000);
}
