/**
 * Tipos dos JSONs gerados por python/run_mining.py.
 * Espelham o JSON campo a campo.
 */

export type Categoria = "ATIVO" | "EVADIDO" | "RETIDO" | "FORMADO";

export const CATEGORIAS: readonly Categoria[] = ["ATIVO", "EVADIDO", "RETIDO", "FORMADO"];

/** alunos_periodo.json — uma linha por (aluno, período). */
export interface AlunoPeriodo {
  codigo_estudante: string;
  curso: string;
  periodo: string;
  semestre: number;
  categoria: Categoria;
}

export interface EvasaoInfo {
  periodo: string;
  semestre: number;
  /** Texto bruto de DS_TP_SIT_ACAD (ex.: "DESVINCULADO"). */
  tipo: string;
}

export interface FormacaoInfo {
  periodo: string;
  semestre: number;
}

/** alunos_resumo.json — uma linha por aluno, situação mais recente do histórico completo. */
export interface AlunoResumo {
  codigo_estudante: string;
  curso: string;
  admissao: string | null;
  periodo_atual: string;
  semestre_atual: number;
  situacao_atual: Categoria;
  evasao: EvasaoInfo | null;
  formacao: FormacaoInfo | null;
}

/** alunos_filtros.json */
export interface AlunosFiltros {
  cursos: string[];
  /** Ordem cronológica. */
  periodos: string[];
}

/**
 * Uma matrícula em formato colunar:
 * [cursoIdx, disciplinaIdx, periodoIdx, aprovado, reprovado, media, faltas]
 */
export type DisciplinaRow = [number, number, number, 0 | 1, 0 | 1, number | null, number | null];

/** disciplinas_rows.json */
export interface DisciplinasRows {
  cursos: string[];
  disciplinas: string[];
  /** Ordem cronológica. */
  periodos: string[];
  rows: DisciplinaRow[];
}

export interface MinedData {
  alunosPeriodo: AlunoPeriodo[];
  alunosResumo: AlunoResumo[];
  alunosFiltros: AlunosFiltros;
  disciplinasRows: DisciplinasRows;
}
