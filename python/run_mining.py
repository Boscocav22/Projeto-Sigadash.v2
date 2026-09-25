"""
run_mining.py — orquestrador de linha de comando (script de build de dados).

Uso (a partir da raiz do projeto):
    python python/run_mining.py
    python python/run_mining.py --csv public/data/df_tabela_final.csv --out public/data/generated

Rodar apos mudar o CSV. Não é servidor: só gera os 4 JSONs que o frontend carrega.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from alunos_mining import mine_alunos
from common import load_csv
from disciplinas_mining import mine_disciplinas

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "public" / "data" / "df_tabela_final.csv"
DEFAULT_OUT = ROOT / "public" / "data" / "generated"


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024  # type: ignore[assignment]
    return f"{n} B"


def _write_json(out_dir: Path, name: str, payload: Any) -> None:
    path = out_dir / f"{name}.json"
    t0 = time.perf_counter()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    dt = time.perf_counter() - t0
    print(f"  ✔ {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"
          f"  ({_fmt_size(path.stat().st_size)}, {dt:.2f}s)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera os JSONs minerados do Sigadash.v2")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.csv.exists():
        print(f"CSV não encontrado: {args.csv}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    t_total = time.perf_counter()

    t0 = time.perf_counter()
    df = load_csv(args.csv)
    print(f"• CSV lido: {len(df):,} linhas em {time.perf_counter() - t0:.2f}s")

    t0 = time.perf_counter()
    alunos = mine_alunos(df)
    print(f"• Mineração de alunos: {time.perf_counter() - t0:.2f}s")

    t0 = time.perf_counter()
    disciplinas = mine_disciplinas(df)
    print(f"• Mineração de disciplinas: {time.perf_counter() - t0:.2f}s")

    print(f"• Gravando em {args.out}")
    for name, payload in {**alunos, **disciplinas}.items():
        _write_json(args.out, name, payload)

    print(f"• Concluído em {time.perf_counter() - t_total:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
