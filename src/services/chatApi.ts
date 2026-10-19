/**
 * Cliente do backend do Assistente IA (backend/, FastAPI).
 * Em desenvolvimento o Vite encaminha /api para http://localhost:8000.
 */

const API_URL = import.meta.env.VITE_API_URL ?? "";

export type HistoricoItem = { role: "user" | "assistant"; text: string };

/** Como desenhar `dados`: só nomes de colunas; os valores vêm sempre de `dados`. */
export type Grafico = {
  tipo: "barra" | "barra_horizontal" | "linha";
  x: string;
  y: string[];
  titulo: string;
};

export type ChatResposta = {
  resposta: string;
  sql: string | null;
  colunas: string[];
  dados: unknown[][];
  total_linhas: number;
  truncado: boolean;
  grafico: Grafico | null;
};

export async function perguntar(pergunta: string, historico: HistoricoItem[]): Promise<ChatResposta> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pergunta, historico }),
    });
  } catch {
    throw new Error("Não foi possível conectar ao assistente. Verifique se o backend está rodando.");
  }

  if (!res.ok) {
    let detalhe = `Erro ${res.status} ao consultar o assistente.`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detalhe = body.detail;
    } catch {
      // corpo não-JSON: mantém a mensagem genérica
    }
    throw new Error(detalhe);
  }
  return (await res.json()) as ChatResposta;
}
