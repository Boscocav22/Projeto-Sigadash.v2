"""Executa a projeção em segundo plano ao iniciar a API e guarda o resultado em memória e em disco.

O cache em disco evita retreinar a cada reinício (ex.: `uvicorn --reload`): ele só é
reaproveitado se a "impressão digital" bater, isto é, mesmo CSV, mesmo código do
algoritmo e mesmos períodos ignorados. Qualquer mudança nisso dispara um novo cálculo.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from app.projecao.calculo import ProjecaoErro, calcular_projecao

log = logging.getLogger(__name__)

Status = Literal["processando", "pronto", "erro", "desativado"]
Calculadora = Callable[[Path, list[str]], dict]

_DIR_PROJECAO = Path(__file__).resolve().parent
_DIR_PYTHON = Path(__file__).resolve().parents[3] / "python"
# Arquivos cujo conteúdo define o resultado: mudou algum, o cache deixa de valer.
_ARQUIVOS_DO_ALGORITMO = [
    _DIR_PROJECAO / "classificador.py",
    _DIR_PROJECAO / "preparo.py",
    _DIR_PROJECAO / "calculo.py",
    _DIR_PYTHON / "alunos_mining.py",
    _DIR_PYTHON / "common.py",
]


def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def impressao_digital(csv_path: Path, periodos_ignorados: list[str], arquivos: list[Path] | None = None) -> str:
    h = hashlib.sha256()
    h.update(_sha256_arquivo(csv_path).encode())
    for arq in arquivos if arquivos is not None else _ARQUIVOS_DO_ALGORITMO:
        if arq.exists():
            h.update(_sha256_arquivo(arq).encode())
    h.update(json.dumps(sorted(periodos_ignorados)).encode())
    return h.hexdigest()


class ServicoProjecao:
    def __init__(
        self,
        csv_path: Path,
        cache_path: Path,
        periodos_ignorados: list[str],
        calcular: Calculadora = calcular_projecao,
        arquivos_do_algoritmo: list[Path] | None = None,
    ) -> None:
        self._csv_path = csv_path
        self._cache_path = cache_path
        self._periodos_ignorados = periodos_ignorados
        self._calcular = calcular
        self._arquivos = arquivos_do_algoritmo
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._status: Status = "desativado"
        self._mensagem: str | None = None
        self._origem: Literal["cache", "calculo"] | None = None
        self._resultado: dict | None = None

    # ── consulta ──────────────────────────────────────────────────────────
    def estado(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "mensagem": self._mensagem,
                "origem": self._origem,
                **(self._resultado or {}),
            }

    # ── execução ──────────────────────────────────────────────────────────
    def iniciar(self, forcar: bool = False) -> bool:
        """Dispara o cálculo em segundo plano. Devolve False se já há um em andamento."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._status = "processando"
            self._mensagem = None
            self._thread = threading.Thread(target=self._executar, args=(forcar,), name="projecao", daemon=True)
            self._thread.start()
            return True

    def aguardar(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _executar(self, forcar: bool) -> None:
        try:
            impressao = impressao_digital(self._csv_path, self._periodos_ignorados, self._arquivos) \
                if self._csv_path.exists() else None

            if not forcar and impressao is not None:
                resultado = self._ler_cache(impressao)
                if resultado is not None:
                    self._concluir(resultado, "cache")
                    log.info("projeção carregada do cache (%s)", self._cache_path)
                    return

            log.info("calculando projeção a partir de %s ...", self._csv_path)
            resultado = self._calcular(self._csv_path, self._periodos_ignorados)
            if impressao is not None:
                self._gravar_cache(impressao, resultado)
            self._concluir(resultado, "calculo")
            log.info("projeção pronta: %s, %d linhas", resultado.get("periodo_alvo"), len(resultado.get("linhas", [])))
        except ProjecaoErro as exc:
            self._falhar(str(exc))
        except Exception as exc:  # noqa: BLE001 — falha inesperada não pode derrubar a API
            log.exception("falha ao calcular a projeção")
            self._falhar(f"Falha inesperada ao calcular a projeção: {exc}")

    def _concluir(self, resultado: dict, origem: Literal["cache", "calculo"]) -> None:
        with self._lock:
            self._resultado = resultado
            self._origem = origem
            self._status = "pronto"
            self._mensagem = None

    def _falhar(self, mensagem: str) -> None:
        log.warning("projeção indisponível: %s", mensagem)
        with self._lock:
            # Mantém o último resultado válido, se houver, para o dashboard continuar mostrando algo.
            self._status = "erro"
            self._mensagem = mensagem

    # ── cache em disco ────────────────────────────────────────────────────
    def _ler_cache(self, impressao: str) -> dict | None:
        try:
            dados = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if dados.get("impressao") != impressao or not isinstance(dados.get("resultado"), dict):
            return None
        return dados["resultado"]

    def _gravar_cache(self, impressao: str, resultado: dict) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._cache_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"impressao": impressao, "gravado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "resultado": resultado},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tmp.replace(self._cache_path)
        except OSError as exc:
            # Sem cache o sistema funciona; só recalcula no próximo início.
            log.warning("não foi possível gravar o cache da projeção: %s", exc)
