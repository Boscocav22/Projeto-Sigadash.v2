/**
disciplinasView.ts — filtra, agrega e ordena as matrículas colunares.

Aprovado/reprovado já vêm resolvidos do Python ("DISPENSADO" conta como
aprovado, outras situações não entram em nenhuma das duas contagens).
Aqui só se decide o recorte (curso, períodos, disciplinas) e a apresentação:
ordem crescente/decrescente e corte Top 10 dos rankings.
*/
import type { MinedData } from "../types/mined";

export interface DisciplinasFiltro {
  /** null = Todos os Cursos */
  curso: string | null;
  /** [] = Todos os Períodos */
  periodosSelecionados: string[];
  /** [] = Todas as Disciplinas */
  disciplinasSelecionadas: string[];
}

export interface RankingItem {
  disciplina: string;
  valor: number;
}

export interface DisciplinasKpis {
  totalMatriculas: number;
  totalAprovados: number;
  totalReprovados: number;
  /** aprovados / (aprovados + reprovados) */
  taxaAprovacao: number;
  /** reprovados / (aprovados + reprovados) */
  taxaReprovacao: number;
}

export interface SeriePeriodo {
  periodo: string;
  aprovados: number;
  reprovados: number;
}

export interface LinhaTabela {
  curso: string;
  disciplina: string;
  matriculas: number;
  aprovados: number;
  reprovados: number;
  taxaAprovacao: number;
  mediaFinal: number | null;
  mediaFaltas: number | null;
}

export interface DisciplinasView {
  kpis: DisciplinasKpis;
  rankingMaisAprovados: RankingItem[];
  rankingMaisReprovados: RankingItem[];
  rankingMelhorMedia: RankingItem[];
  rankingMelhorFrequencia: RankingItem[];
  rankingMaisFaltas: RankingItem[];
  rankingPiorMedia: RankingItem[];
  serieHistorica: SeriePeriodo[];
  tabela: LinhaTabela[];
}

export const TOP_N = 10;

/**
 * Mínimo de matrículas com nota/falta registrada para uma disciplina entrar
 * nos rankings de média e de faltas. 1 = sem restrição (comportamento atual).
 */
export const MIN_AMOSTRA_MEDIAS = 1;

// Acumuladores
interface Acc {
  matriculas: number;
  aprovados: number;
  reprovados: number;
  somaMedia: number;
  nMedia: number;
  somaFaltas: number;
  nFaltas: number;
}

const novoAcc = (): Acc => ({
  matriculas: 0,
  aprovados: 0,
  reprovados: 0,
  somaMedia: 0,
  nMedia: 0,
  somaFaltas: 0,
  nFaltas: 0,
});

const pct = (num: number, den: number) => (den > 0 ? (num / den) * 100 : 0);

/** Disciplinas existentes para o curso escolhido (para o dropdown). */
export function disciplinasDoCurso(data: MinedData, curso: string | null): string[] {
  const { cursos, disciplinas, rows } = data.disciplinasRows;
  if (curso === null) return disciplinas;
  const cIdx = cursos.indexOf(curso);
  if (cIdx < 0) return [];
  const presentes = new Uint8Array(disciplinas.length);
  for (const r of rows) if (r[0] === cIdx) presentes[r[1]] = 1;
  return disciplinas.filter((_, i) => presentes[i] === 1);
}

function ranking(
  nomes: string[],
  accs: Acc[],
  valor: (a: Acc) => number | null,
  ordem: "asc" | "desc"
): RankingItem[] {
  const itens: RankingItem[] = [];
  accs.forEach((a, i) => {
    if (a.matriculas === 0) return;
    const v = valor(a);
    if (v === null) return;
    itens.push({ disciplina: nomes[i], valor: v });
  });
  itens.sort((x, y) => (ordem === "desc" ? y.valor - x.valor : x.valor - y.valor) || x.disciplina.localeCompare(y.disciplina, "pt-BR"));
  return itens.slice(0, TOP_N);
}

export function computeDisciplinasView(data: MinedData, filtro: DisciplinasFiltro): DisciplinasView {
  const { cursos, disciplinas, periodos, rows } = data.disciplinasRows;
  const nD = disciplinas.length;

  const cursoIdx = filtro.curso === null ? -1 : cursos.indexOf(filtro.curso);
  const cursoInexistente = filtro.curso !== null && cursoIdx < 0;

  // Set de índices de disciplina selecionados (vazio = todas).
  const disciplinasSelecionadasIdx = new Set<number>();
  for (const d of filtro.disciplinasSelecionadas) {
    const i = disciplinas.indexOf(d);
    if (i >= 0) disciplinasSelecionadasIdx.add(i);
  }
  const todasDisciplinas = disciplinasSelecionadasIdx.size === 0;
  // havia seleção, mas nenhuma disciplina selecionada existe nos dados
  const discInexistente = filtro.disciplinasSelecionadas.length > 0 && todasDisciplinas;

  // Set de índices de período, montado uma vez por render.
  const periodosSelecionadosIdx = new Set<number>();
  for (const p of filtro.periodosSelecionados) {
    const i = periodos.indexOf(p);
    if (i >= 0) periodosSelecionadosIdx.add(i);
  }
  const todosPeriodos = periodosSelecionadosIdx.size === 0;

  const porDisciplina: Acc[] = Array.from({ length: nD }, novoAcc);
  const porCursoDisc = new Map<number, Acc>();
  const aprovPer = new Array<number>(periodos.length).fill(0);
  const reprovPer = new Array<number>(periodos.length).fill(0);

  let totalMatriculas = 0;
  let totalAprovados = 0;
  let totalReprovados = 0;

  if (!cursoInexistente && !discInexistente) {
    for (const r of rows) {
      const [c, d, p, ap, rp, media, faltas] = r;
      if (cursoIdx >= 0 && c !== cursoIdx) continue;
      if (!todasDisciplinas && !disciplinasSelecionadasIdx.has(d)) continue;
      if (!todosPeriodos && !periodosSelecionadosIdx.has(p)) continue;

      totalMatriculas++;
      totalAprovados += ap;
      totalReprovados += rp;
      aprovPer[p] += ap;
      reprovPer[p] += rp;

      const key = c * nD + d;
      let cd = porCursoDisc.get(key);
      if (!cd) porCursoDisc.set(key, (cd = novoAcc()));

      for (const acc of [porDisciplina[d], cd]) {
        acc.matriculas++;
        acc.aprovados += ap;
        acc.reprovados += rp;
        if (media !== null) {
          acc.somaMedia += media;
          acc.nMedia++;
        }
        if (faltas !== null) {
          acc.somaFaltas += faltas;
          acc.nFaltas++;
        }
      }
    }
  }

  const decididos = totalAprovados + totalReprovados;
  const kpis: DisciplinasKpis = {
    totalMatriculas,
    totalAprovados,
    totalReprovados,
    taxaAprovacao: pct(totalAprovados, decididos),
    taxaReprovacao: pct(totalReprovados, decididos),
  };

  const mediaNota = (a: Acc) => (a.nMedia >= MIN_AMOSTRA_MEDIAS && a.nMedia > 0 ? a.somaMedia / a.nMedia : null);
  const mediaFaltas = (a: Acc) =>
    a.nFaltas >= MIN_AMOSTRA_MEDIAS && a.nFaltas > 0 ? a.somaFaltas / a.nFaltas : null;

  const serieHistorica: SeriePeriodo[] = [];
  periodos.forEach((periodo, i) => {
    if (!todosPeriodos && !periodosSelecionadosIdx.has(i)) return;
    serieHistorica.push({ periodo, aprovados: aprovPer[i], reprovados: reprovPer[i] });
  });

  const tabela: LinhaTabela[] = [];
  for (const [key, a] of porCursoDisc) {
    const c = Math.floor(key / nD);
    const d = key % nD;
    tabela.push({
      curso: cursos[c],
      disciplina: disciplinas[d],
      matriculas: a.matriculas,
      aprovados: a.aprovados,
      reprovados: a.reprovados,
      taxaAprovacao: pct(a.aprovados, a.aprovados + a.reprovados),
      mediaFinal: a.nMedia > 0 ? a.somaMedia / a.nMedia : null,
      mediaFaltas: a.nFaltas > 0 ? a.somaFaltas / a.nFaltas : null,
    });
  }
  tabela.sort(
    (x, y) => x.curso.localeCompare(y.curso, "pt-BR") || x.disciplina.localeCompare(y.disciplina, "pt-BR")
  );

  return {
    kpis,
    rankingMaisAprovados: ranking(disciplinas, porDisciplina, (a) => a.aprovados, "desc"),
    rankingMaisReprovados: ranking(disciplinas, porDisciplina, (a) => a.reprovados, "desc"),
    rankingMelhorMedia: ranking(disciplinas, porDisciplina, mediaNota, "desc"),
    rankingPiorMedia: ranking(disciplinas, porDisciplina, mediaNota, "asc"),
    rankingMelhorFrequencia: ranking(disciplinas, porDisciplina, mediaFaltas, "asc"),
    rankingMaisFaltas: ranking(disciplinas, porDisciplina, mediaFaltas, "desc"),
    serieHistorica,
    tabela,
  };
}
