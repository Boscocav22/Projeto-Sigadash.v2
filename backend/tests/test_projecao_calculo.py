"""Algoritmo de projeção (porta do notebook regress_copy_6.ipynb).

Os testes que rodam o CSV completo levam ~25 s cada; rode com RODAR_TESTES_LENTOS=1.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.projecao.calculo import ProjecaoErro, calcular_projecao, ler_csv, periodo_seguinte_ao_ultimo
from app.projecao.preparo import ROTULO_DA_CATEGORIA, para_semestre, preparar_tabela
from tests.conftest import CSV, ROOT

sys.path.insert(0, str(ROOT / "python"))
from alunos_mining import mine_alunos  # noqa: E402
from common import load_csv  # noqa: E402

REFERENCIA_NOTEBOOK = Path(__file__).parent / "dados" / "resumo_projetado_notebook.csv"
lento = pytest.mark.skipif(not os.environ.get("RODAR_TESTES_LENTOS"), reason="defina RODAR_TESTES_LENTOS=1")


def test_2020_3_conta_como_2021_1_igual_ao_notebook():
    assert para_semestre(2020.3) == para_semestre(2021.1)
    assert para_semestre(2018.2) == 2018 * 2 + 2


def test_categorias_iguais_as_do_dashboard(amostra_csv):
    """Situação por aluno×período = alunos_periodo da mineração do dashboard (inclui a regra dos 13 semestres)."""
    copia = preparar_tabela(ler_csv(amostra_csv))
    por_rotulo = {v: k for k, v in ROTULO_DA_CATEGORIA.items()}
    nossa = (
        copia.groupby(["codigo_estudante", "CD_PERD_LETV"])["DS_TP_SIT_ACAD"].last().map(por_rotulo).reset_index()
    )
    nossa["chave"] = nossa["codigo_estudante"].astype(str) + "|" + nossa["CD_PERD_LETV"].map(lambda f: f"{f:.1f}")

    dash = pd.DataFrame(mine_alunos(load_csv(amostra_csv))["alunos_periodo"])
    dash["chave"] = dash["codigo_estudante"] + "|" + dash["periodo"]

    junto = nossa.merge(dash, on="chave")
    assert len(junto) > 500
    assert (junto["DS_TP_SIT_ACAD"] == junto["categoria"]).all()
    assert "RETIDO" in set(junto["categoria"])  # a amostra exercita a regra dos 13 semestres
    # Só ficam de fora pares de 2020.3 descartados pela célula 6 do notebook (sem média final).
    so_dashboard = set(dash["chave"]) - set(nossa["chave"])
    assert all(c.endswith("|2020.3") for c in so_dashboard)


def test_periodo_alvo_e_o_seguinte_ao_ultimo():
    assert periodo_seguinte_ao_ultimo(pd.DataFrame({"CD_PERD_LETV": [2024.1, 2025.2, 2020.3]})) == "2026.1"
    assert periodo_seguinte_ao_ultimo(pd.DataFrame({"CD_PERD_LETV": [2024.2, 2025.1]})) == "2025.2"


def test_csv_ausente(tmp_path):
    with pytest.raises(ProjecaoErro, match="não encontrado"):
        ler_csv(tmp_path / "nao_existe.csv")


def test_csv_sem_colunas(tmp_path):
    arq = tmp_path / "x.csv"
    arq.write_text("a;b\n1;2\n", encoding="utf-8")
    with pytest.raises(ProjecaoErro, match="não tem as colunas"):
        ler_csv(arq)


def test_csv_vazio(tmp_path):
    arq = tmp_path / "x.csv"
    arq.write_text(CSV.read_text(encoding="utf-8-sig").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(ProjecaoErro, match="vazio"):
        ler_csv(arq)


def test_algoritmo_real_em_um_curso(tmp_path):
    """Roda o Random Forest de verdade num curso pequeno (~2 s)."""
    tabela = pd.read_csv(CSV, sep=";")
    arq = tmp_path / "fisica.csv"
    tabela[tabela["NM_PROGR_FORM"] == "FISICA DE MATERIAIS"].to_csv(arq, sep=";", index=False)

    r = calcular_projecao(arq, ["2025.1", "2025.2"])

    assert r["erros"] == []
    assert {l["curso"] for l in r["linhas"]} == {"FISICA DE MATERIAIS"}
    assert {l["situacao"] for l in r["linhas"]} <= set(ROTULO_DA_CATEGORIA.values())
    assert all(l["periodo_base"] == "2024.2" for l in r["linhas"])  # 2025.1 ignorado
    total = sum(l["quantidade"] for l in r["linhas"])
    for l in r["linhas"]:
        assert l["proporcao"] == pytest.approx(l["quantidade"] / total, abs=1e-4)


@lento
def test_modo_notebook_reproduz_o_resumo_do_notebook():
    """Com a célula 4 original, a porta gera exatamente o resumo_projetado_todos_os_cursos.csv do notebook."""
    r = calcular_projecao(CSV, ["2025.1", "2025.2"], categorias="notebook")
    nosso = pd.DataFrame(r["linhas"]).rename(columns={"curso": "NM_PROGR_FORM"})
    ref = pd.read_csv(REFERENCIA_NOTEBOOK)
    junto = nosso.merge(ref, on=["NM_PROGR_FORM", "situacao"], how="outer", indicator=True)
    assert (junto["_merge"] == "both").all()
    assert (junto["quantidade"] == junto["quantidade_projetada"]).all()
    assert (junto["proporcao"] - junto["proporcao_projetada"]).abs().max() < 1e-9
    assert set(junto["periodo_alvo_x"]) == {"2026.1"}


@lento
def test_csv_completo_com_categorias_do_dashboard():
    r = calcular_projecao(CSV, ["2025.1", "2025.2"])
    assert r["periodo_alvo"] == "2026.1"
    assert r["erros"] == []
    assert len({l["curso"] for l in r["linhas"]}) == 10
