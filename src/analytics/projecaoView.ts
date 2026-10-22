/**
 * Recorte da projeção para os 8 cards do Painel de Alunos.
 * O backend devolve quantidades por curso×situação; aqui só se filtra e soma.
 */
import type { Categoria } from "../types/mined";
import { CATEGORIAS } from "../types/mined";
import type { LinhaProjecao, SituacaoProjecao } from "../services/projecaoApi";

export const CATEGORIA_DA_SITUACAO: Record<SituacaoProjecao, Categoria> = {
  "ALUNOS ATIVOS": "ATIVO",
  EVASÃO: "EVADIDO",
  "ALUNOS RETIDOS": "RETIDO",
  CONCLUSÃO: "FORMADO",
};

export interface ProjecaoKpi {
  categoria: Categoria;
  quantidade: number;
  /** Em %, sobre o total projetado do recorte (todas as situações). */
  taxa: number;
}

export interface ProjecaoView {
  kpis: ProjecaoKpi[];
  total: number;
  periodosBase: string[];
}

export function computeProjecaoView(
  linhas: LinhaProjecao[],
  filtros: { curso: string | null; indicadoresSelecionados: Categoria[] }
): ProjecaoView {
  const porCategoria = new Map<Categoria, number>();
  const periodosBase = new Set<string>();
  let total = 0;

  for (const l of linhas) {
    if (filtros.curso !== null && l.curso !== filtros.curso) continue;
    const cat = CATEGORIA_DA_SITUACAO[l.situacao];
    if (!cat) continue;
    porCategoria.set(cat, (porCategoria.get(cat) ?? 0) + l.quantidade);
    total += l.quantidade;
    periodosBase.add(l.periodo_base);
  }

  // Mesma regra dos cards observados: nenhum indicador marcado = todos; taxas sobre o total do recorte.
  const visiveis =
    filtros.indicadoresSelecionados.length > 0
      ? CATEGORIAS.filter((c) => filtros.indicadoresSelecionados.includes(c))
      : CATEGORIAS;

  return {
    kpis: visiveis.map((categoria) => {
      const quantidade = porCategoria.get(categoria) ?? 0;
      return { categoria, quantidade, taxa: total > 0 ? (quantidade / total) * 100 : 0 };
    }),
    total,
    periodosBase: [...periodosBase].sort(),
  };
}
