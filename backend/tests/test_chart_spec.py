import pytest

from app.services.chart_spec import classificar_colunas, escolher_grafico, grafico_por_regra, validar_grafico

EVASAO_COLS = ["curso", "total_alunos", "evadidos", "taxa_evasao_pct"]
EVASAO = [
    ["ENGENHARIA MECATRÔNICA", 156, 109, 69.9],
    ["ENGENHARIA TELECOMUNICAÇÕES", 650, 378, 58.2],
    ["ENGENHARIA CIVIL", 2100, 900, 42.9],
]
CONCLUINTES_COLS = ["periodo_letivo", "concluintes"]
CONCLUINTES = [["2012.1", 3], ["2012.2", 2], ["2013.1", 8]]
APROV_COLS = ["curso", "aprovados", "reprovados"]
APROV = [["CIVIL", 900, 300], ["MECÂNICA", 700, 280]]


def test_classifica_colunas():
    assert classificar_colunas(EVASAO_COLS, EVASAO) == {
        "curso": "categorica",
        "total_alunos": "numerica",
        "evadidos": "numerica",
        "taxa_evasao_pct": "numerica",
    }
    assert classificar_colunas(CONCLUINTES_COLS, CONCLUINTES)["periodo_letivo"] == "temporal"
    assert classificar_colunas(["codigo_estudante", "media"], [[1, 7.5], [2, 6.0]])["codigo_estudante"] == "categorica"


def test_aceita_sugestao_valida_do_modelo():
    spec = validar_grafico(
        {"tipo": "barra_horizontal", "x": "curso", "y": ["taxa_evasao_pct"], "titulo": "Evasão"}, EVASAO_COLS, EVASAO
    )
    assert spec and spec.y == ["taxa_evasao_pct"]


def test_aceita_duas_series_na_mesma_escala():
    spec = validar_grafico({"tipo": "barra", "x": "curso", "y": ["aprovados", "reprovados"]}, APROV_COLS, APROV)
    assert spec and spec.y == ["aprovados", "reprovados"]


@pytest.mark.parametrize(
    "sugestao",
    [
        None,
        "barra",
        {"tipo": "pizza", "x": "curso", "y": ["evadidos"]},                       # tipo não permitido
        {"tipo": "barra", "x": "curso_inexistente", "y": ["evadidos"]},           # coluna inexistente
        {"tipo": "barra", "x": "curso", "y": ["curso"]},                          # y repetindo x
        {"tipo": "barra", "x": "taxa_evasao_pct", "y": ["curso"]},                # y com texto
        {"tipo": "linha", "x": "curso", "y": ["evadidos"]},                       # linha sem eixo temporal
        {"tipo": "barra", "x": "curso", "y": ["total_alunos", "taxa_evasao_pct"]},  # escalas diferentes
        {"tipo": "barra", "x": "curso", "y": []},
    ],
)
def test_recusa_sugestao_invalida(sugestao):
    assert validar_grafico(sugestao, EVASAO_COLS, EVASAO) is None


def test_regra_serie_temporal_vira_linha():
    spec = grafico_por_regra(CONCLUINTES_COLS, CONCLUINTES)
    assert spec and (spec.tipo, spec.x, spec.y) == ("linha", "periodo_letivo", ["concluintes"])


def test_regra_prefere_taxa_e_usa_barra_horizontal_para_nomes_longos():
    spec = grafico_por_regra(EVASAO_COLS, EVASAO)
    assert spec and (spec.tipo, spec.x, spec.y) == ("barra_horizontal", "curso", ["taxa_evasao_pct"])


def test_regra_barra_vertical_para_rotulos_curtos():
    spec = grafico_por_regra(["curso", "total"], [["CIVIL", 10], ["MECÂNICA", 7]])
    assert spec and spec.tipo == "barra"


@pytest.mark.parametrize(
    "colunas, dados",
    [
        (["media_turma"], [[5.7]]),                                   # valor único
        (["curso", "coordenador"], [["CIVIL", "A"], ["MEC", "B"]]),   # nada numérico
        (["disciplina", "taxa"], [[f"D{i}", i] for i in range(16)]),  # categorias demais
    ],
)
def test_regra_nao_desenha_quando_nao_e_obvio(colunas, dados):
    assert grafico_por_regra(colunas, dados) is None


def test_escolher_usa_regra_quando_sugestao_e_invalida():
    spec, origem = escolher_grafico({"tipo": "pizza"}, CONCLUINTES_COLS, CONCLUINTES)
    assert origem == "regra" and spec and spec.tipo == "linha"


def test_escolher_prefere_o_modelo():
    sugestao = {"tipo": "barra", "x": "periodo_letivo", "y": ["concluintes"], "titulo": "Concluintes"}
    spec, origem = escolher_grafico(sugestao, CONCLUINTES_COLS, CONCLUINTES)
    assert origem == "modelo" and spec and spec.tipo == "barra"


def test_barra_vertical_com_nomes_longos_vira_horizontal():
    spec = validar_grafico({"tipo": "barra", "x": "curso", "y": ["taxa_evasao_pct"]}, EVASAO_COLS, EVASAO)
    assert spec and spec.tipo == "barra_horizontal"


def test_barra_vertical_com_nomes_curtos_continua_vertical():
    spec = validar_grafico({"tipo": "barra", "x": "curso", "y": ["aprovados", "reprovados"]}, APROV_COLS, APROV)
    assert spec and spec.tipo == "barra"
