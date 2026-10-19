/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL do backend em produção (ex.: https://api.exemplo.com). Vazio = mesma origem / proxy do Vite. */
  readonly VITE_API_URL?: string;
}
