/**
 * Cliente da projeção do próximo semestre (backend: GET /api/projecao).
 * O backend calcula ao iniciar; enquanto isso responde status "processando".
 */

const API_URL = import.meta.env.VITE_API_URL ?? "";

export type SituacaoProjecao = "ALUNOS ATIVOS" | "ALUNOS RETIDOS" | "EVASÃO" | "CONCLUSÃO";

export type LinhaProjecao = {
  curso: string;
  periodo_base: string;
  periodo_alvo: string;
  situacao: SituacaoProjecao;
  quantidade: number;
  proporcao: number;
};

export type ProjecaoResposta = {
  status: "processando" | "pronto" | "erro" | "desativado";
  mensagem: string | null;
  origem: "cache" | "calculo" | null;
  periodo_alvo: string | null;
  periodos_ignorados: string[];
  gerado_em: string | null;
  linhas: LinhaProjecao[];
  erros: { curso: string; erro: string }[];
};

export async function buscarProjecao(): Promise<ProjecaoResposta> {
  const res = await fetch(`${API_URL}/api/projecao`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as ProjecaoResposta;
}
