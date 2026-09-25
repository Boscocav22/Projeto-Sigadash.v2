/**
alunosView.ts — filtra e conta.
 
A categoria de cada (aluno, período) já vem pronta do Python
(alunos_periodo.json) e a situação mais recente do histórico completo vem
pronta em alunos_resumo.json. Esta camada só decide quais linhas entram no
recorte atual do usuário e conta.
 
Situação "no recorte":
- periodosSelecionados vazio ("Todos os Períodos"): usa alunos_resumo
  diretamente = situação mais recente disponível do aluno, considerando todo
  o histórico dele (não é soma de períodos).
- periodosSelecionados não-vazio: para cada aluno, dentre as linhas de
  alunos_periodo cujo período está no conjunto, pega a MAIS RECENTE.
  Ex.: Aluno X — {2022.1, 2022.2} -> ATIVO; {2022.1, 2022.2, 2023.1} -> RETIDO.
 
Indicadores (multiseleção): aplicados depois da contagem. Quando há
indicadores marcados, só essas categorias são devolvidas nos KPIs e nos
gráficos. Nenhum marcado = Todos os Indicadores.
*/
import type { AlunoPeriodo, AlunoResumo, Categoria, MinedData } from "../types/mined";
import { CATEGORIAS } from "../types/mined";

export interface AlunosFiltro {
  /** null = Todos os Cursos */
  curso: string | null;
  /** [] = Todos os Períodos */
  periodosSelecionados: string[];
  /** [] = Todos os Indicadores */
  indicadoresSelecionados: Categoria[];
}

export interface KpiCategoria {
  categoria: Categoria;
  total: number;
  /** % sobre o total de alunos no recorte */
  taxa: number;
}

export interface SeriePonto {
  periodo: string;
  ativos: number;
  evadidos: number;
  retidos: number;
  formados: number;
}

export type SerieKey = Exclude<keyof SeriePonto, "periodo">;

export const SERIE_KEY: Record<Categoria, SerieKey> = {
  ATIVO: "ativos",
  EVADIDO: "evadidos",
  RETIDO: "retidos",
  FORMADO: "formados",
};

export interface SemestreValor {
  semestre: number;
  valor: number;
}

export interface TipoSaidaValor {
  tipo: string;
  valor: number;
}

export interface AlunosView {
  totalAlunos: number;
  /** Só as categorias visíveis (as marcadas no filtro Indicador, ou as 4). */
  kpis: KpiCategoria[];
  categoriasVisiveis: Categoria[];
  serieHistorica: SeriePonto[];
  /** [] quando EVADIDO não está entre as categorias visíveis. */
  evasaoPorSemestre: SemestreValor[];
  /** [] quando FORMADO não está entre as categorias visíveis. */
  formacaoPorSemestre: SemestreValor[];
  /** [] quando EVADIDO não está entre as categorias visíveis. É o valor exibido pelo HBarLabel. */
  evasaoPorTipoSaida: TipoSaidaValor[];
}

/** Índice cronológico dos períodos (a lista do Python já vem ordenada). */
function rankPeriodos(periodos: string[]): Map<string, number> {
  const m = new Map<string, number>();
  periodos.forEach((p, i) => m.set(p, i));
  return m;
}

/** Histograma denso de 1..max (semestres sem valor aparecem com 0). */
function histogramaSemestres(contagem: Map<number, number>): SemestreValor[] {
  if (contagem.size === 0) return [];
  const max = Math.max(...contagem.keys());
  const out: SemestreValor[] = [];
  for (let s = 1; s <= max; s++) out.push({ semestre: s, valor: contagem.get(s) ?? 0 });
  return out;
}

function inc<K>(m: Map<K, number>, k: K) {
  m.set(k, (m.get(k) ?? 0) + 1);
}

/** Situação de cada aluno no recorte (curso + períodos). */
function situacoesNoRecorte(
  data: MinedData,
  curso: string | null,
  selecionados: Set<string>,
  rank: Map<string, number>
): Categoria[] {
  if (selecionados.size === 0) {
    const out: Categoria[] = [];
    for (const a of data.alunosResumo) {
      if (curso !== null && a.curso !== curso) continue;
      out.push(a.situacao_atual);
    }
    return out;
  }

  const melhor = new Map<string, AlunoPeriodo>();
  for (const r of data.alunosPeriodo) {
    if (!selecionados.has(r.periodo)) continue;
    if (curso !== null && r.curso !== curso) continue;
    const atual = melhor.get(r.codigo_estudante);
    if (!atual || (rank.get(r.periodo) ?? -1) > (rank.get(atual.periodo) ?? -1)) {
      melhor.set(r.codigo_estudante, r);
    }
  }
  return Array.from(melhor.values(), (r) => r.categoria);
}

export function computeAlunosView(data: MinedData, filtro: AlunosFiltro): AlunosView {
  const { curso } = filtro;
  const rank = rankPeriodos(data.alunosFiltros.periodos);
  const selecionados = new Set(filtro.periodosSelecionados.filter((p) => rank.has(p)));

  // ordem canônica (ATIVO, EVADIDO, RETIDO, FORMADO), independente da ordem dos cliques
  const marcados = new Set(filtro.indicadoresSelecionados);
  const categoriasVisiveis: Categoria[] =
    marcados.size > 0 ? CATEGORIAS.filter((c) => marcados.has(c)) : [...CATEGORIAS];
  const mostraEvasao = categoriasVisiveis.includes("EVADIDO");
  const mostraFormacao = categoriasVisiveis.includes("FORMADO");

  // ── KPIs ────────────────────────────────────────────────────────────────
  const situacoes = situacoesNoRecorte(data, curso, selecionados, rank);
  const totalAlunos = situacoes.length;
  const porCategoria = new Map<Categoria, number>();
  for (const c of situacoes) inc(porCategoria, c);
  const kpis: KpiCategoria[] = categoriasVisiveis.map((categoria) => {
    const total = porCategoria.get(categoria) ?? 0;
    return { categoria, total, taxa: totalAlunos > 0 ? (total / totalAlunos) * 100 : 0 };
  });

  // ── Série histórica (contagem por período, direto de alunos_periodo) ────
  const periodosSerie =
    selecionados.size > 0
      ? data.alunosFiltros.periodos.filter((p) => selecionados.has(p))
      : data.alunosFiltros.periodos;
  const serieMap = new Map<string, SeriePonto>(
    periodosSerie.map((p) => [p, { periodo: p, ativos: 0, evadidos: 0, retidos: 0, formados: 0 }])
  );
  for (const r of data.alunosPeriodo) {
    if (curso !== null && r.curso !== curso) continue;
    const ponto = serieMap.get(r.periodo);
    if (!ponto) continue;
    ponto[SERIE_KEY[r.categoria]] += 1;
  }
  const serieHistorica = periodosSerie.map((p) => serieMap.get(p)!);

  // ── Evasão / formação (eventos do resumo, filtrados pelo período do evento) ─
  const noRecorte = (periodo: string) => selecionados.size === 0 || selecionados.has(periodo);
  const evSemestre = new Map<number, number>();
  const evTipo = new Map<string, number>();
  const formSemestre = new Map<number, number>();

  for (const a of data.alunosResumo as AlunoResumo[]) {
    if (curso !== null && a.curso !== curso) continue;
    if (mostraEvasao && a.evasao && noRecorte(a.evasao.periodo)) {
      inc(evSemestre, a.evasao.semestre);
      inc(evTipo, a.evasao.tipo);
    }
    if (mostraFormacao && a.formacao && noRecorte(a.formacao.periodo)) {
      inc(formSemestre, a.formacao.semestre);
    }
  }

  const evasaoPorTipoSaida = Array.from(evTipo, ([tipo, valor]) => ({ tipo, valor })).sort(
    (a, b) => b.valor - a.valor || a.tipo.localeCompare(b.tipo, "pt-BR")
  );

  return {
    totalAlunos,
    kpis,
    categoriasVisiveis,
    serieHistorica,
    evasaoPorSemestre: histogramaSemestres(evSemestre),
    formacaoPorSemestre: histogramaSemestres(formSemestre),
    evasaoPorTipoSaida,
  };
}
