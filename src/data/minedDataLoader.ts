/**
 * Carrega os quatro JSONs gerados pelo Python, em paralelo.
 */
import type { AlunoPeriodo, AlunoResumo, AlunosFiltros, DisciplinasRows, MinedData } from "../types/mined";

const GENERATED_DIR = "/data/generated/";

const HINT = "Gere os arquivos com: python python/run_mining.py (a partir da raiz do projeto).";

async function fetchJson<T>(file: string): Promise<T> {
  const url = `${GENERATED_DIR}${file}`;
  let res: Response;
  try {
    res = await fetch(url);
  } catch (err) {
    throw new Error(`Falha de rede ao buscar ${url}: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (!res.ok) {
    throw new Error(`Arquivo ${url} não encontrado (HTTP ${res.status}). ${HINT}`);
  }
  // O dev server do Vite responde index.html (HTTP 200) para arquivos inexistentes.
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("text/html")) {
    throw new Error(`Arquivo ${url} não existe (o servidor devolveu HTML). ${HINT}`);
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new Error(`Arquivo ${url} não é um JSON válido. ${HINT}`);
  }
}

export async function loadMinedData(): Promise<MinedData> {
  const [alunosPeriodo, alunosResumo, alunosFiltros, disciplinasRows] = await Promise.all([
    fetchJson<AlunoPeriodo[]>("alunos_periodo.json"),
    fetchJson<AlunoResumo[]>("alunos_resumo.json"),
    fetchJson<AlunosFiltros>("alunos_filtros.json"),
    fetchJson<DisciplinasRows>("disciplinas_rows.json"),
  ]);
  return { alunosPeriodo, alunosResumo, alunosFiltros, disciplinasRows };
}
