import pytest

from app.core.errors import DatabaseUnavailableError, SQLExecutionError
from app.db.catalog import TABELAS_PERMITIDAS, descricao_banco
from app.db.database import execute_select
from app.services.sql_generator import EXEMPLOS
from app.services.sql_guard import validate_select


def test_trunca_no_limite_de_linhas(db_path):
    r = execute_select(db_path, "SELECT * FROM matriculas", max_linhas=10, timeout_s=5)
    assert len(r.linhas) == 10
    assert r.truncado
    assert r.colunas[:3] == ["id", "codigo_estudante", "curso"]


@pytest.mark.parametrize("sql", ["DELETE FROM alunos", "CREATE TABLE x (a)", "PRAGMA writable_schema = 1"])
def test_conexao_nega_escrita_mesmo_sem_o_guard(db_path, sql):
    with pytest.raises(SQLExecutionError):
        execute_select(db_path, sql, max_linhas=10, timeout_s=5)


def test_timeout_interrompe_consulta_longa(db_path):
    sql = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT COUNT(*) FROM n"
    with pytest.raises(SQLExecutionError, match="demorou"):
        execute_select(db_path, sql, max_linhas=10, timeout_s=0.2)


def test_banco_ausente(tmp_path):
    with pytest.raises(DatabaseUnavailableError):
        execute_select(tmp_path / "nao_existe.db", "SELECT 1", max_linhas=1, timeout_s=1)


@pytest.mark.parametrize("pergunta, sql", EXEMPLOS)
def test_exemplos_few_shot_sao_validos(db_path, pergunta, sql):
    execute_select(db_path, validate_select(sql, TABELAS_PERMITIDAS), max_linhas=50, timeout_s=5)


def test_descricao_do_banco_traz_valores_reais(db_path):
    texto = descricao_banco(db_path)
    assert "TABLE matriculas" in texto
    assert "ENGENHARIA" in texto
    assert "'APROVADO'" in texto
