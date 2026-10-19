import pytest

from app.core.errors import UnsafeSQLError
from app.db.catalog import TABELAS_PERMITIDAS
from app.services.sql_guard import validate_select


@pytest.mark.parametrize(
    "sql, esperado",
    [
        ("SELECT COUNT(*) FROM alunos", "SELECT COUNT(*) FROM alunos"),
        ("```sql\nSELECT curso FROM alunos;\n```", "SELECT curso FROM alunos"),
        ("WITH t AS (SELECT curso FROM alunos) SELECT * FROM t", None),
        ("SELECT curso FROM alunos UNION SELECT curso FROM matriculas", None),
        ("SELECT a.curso FROM alunos a JOIN matriculas m ON m.codigo_estudante = a.codigo_estudante", None),
    ],
)
def test_aceita_consultas_de_leitura(sql, esperado):
    assert validate_select(sql, TABELAS_PERMITIDAS) == (esperado or sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "DROP TABLE alunos",
        "DELETE FROM alunos",
        "UPDATE alunos SET curso = 'x'",
        "INSERT INTO alunos SELECT * FROM alunos",
        "SELECT 1; DELETE FROM alunos",
        "PRAGMA table_info(alunos)",
        "ATTACH DATABASE 'x.db' AS x",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM main.alunos",
        "SELECT * FROM json_each('[1]')",
        "WITH t AS (DELETE FROM alunos RETURNING *) SELECT * FROM t",
        "SELEC curso FROM",
    ],
)
def test_bloqueia_consultas_inseguras_ou_invalidas(sql):
    with pytest.raises(UnsafeSQLError):
        validate_select(sql, TABELAS_PERMITIDAS)
