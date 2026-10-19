from app.core.config import Settings
from app.services.answer_writer import SEM_RESULTADOS
from app.services.chat_service import FORA_DO_ESCOPO
from tests.conftest import FakeLLM


def test_fluxo_completo(make_client):
    llm = FakeLLM([
        {"relevante": True, "sql": "SELECT curso, COUNT(*) AS total FROM alunos GROUP BY curso"},
        "Há alunos de Engenharia Mecânica na amostra.",
    ])
    r = make_client(llm).post("/api/chat", json={"pergunta": "Quantos alunos por curso?"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resposta"] == "Há alunos de Engenharia Mecânica na amostra."
    assert body["colunas"] == ["curso", "total"]
    assert body["total_linhas"] == len(body["dados"]) > 0
    assert body["sql"].startswith("SELECT curso")
    # o resultado da consulta foi enviado ao LLM para redigir a resposta
    assert "ENGENHARIA" in llm.chamadas[1]["messages"][0]["content"]
    assert llm.chamadas[0]["json_mode"] is True


def test_historico_vai_para_o_gerador_de_sql(make_client):
    llm = FakeLLM([{"relevante": True, "sql": "SELECT 1 AS x"}, "ok"])
    make_client(llm).post(
        "/api/chat",
        json={
            "pergunta": "E em 2023.1?",
            "historico": [
                {"role": "user", "text": "Média de Cálculo 1 em 2022.2?"},
                {"role": "assistant", "text": "A média foi 5,2."},
            ],
        },
    )
    msgs = llm.chamadas[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[-1]["content"] == "E em 2023.1?"


def test_pergunta_fora_do_escopo(make_client):
    llm = FakeLLM([{"relevante": False, "sql": None}])
    r = make_client(llm).post("/api/chat", json={"pergunta": "Quem é mais engraçado, Chaves ou Quico?"})
    assert r.status_code == 200
    assert r.json()["resposta"] == FORA_DO_ESCOPO
    assert r.json()["sql"] is None


def test_pedido_destrutivo_e_bloqueado(make_client):
    llm = FakeLLM([{"relevante": True, "sql": "DROP TABLE alunos"}, {"relevante": True, "sql": "DELETE FROM alunos"}])
    r = make_client(llm).post("/api/chat", json={"pergunta": "Apague todas as tabelas"})
    assert r.status_code == 422
    assert "leitura" in r.json()["detail"]


def test_corrige_sql_apos_erro(make_client):
    llm = FakeLLM([
        {"relevante": True, "sql": "SELECT coluna_inexistente FROM alunos"},
        {"relevante": True, "sql": "SELECT COUNT(*) AS total FROM alunos"},
        "Existem alunos na base.",
    ])
    r = make_client(llm).post("/api/chat", json={"pergunta": "Quantos alunos existem?"})
    assert r.status_code == 200, r.text
    assert r.json()["colunas"] == ["total"]
    correcao = llm.chamadas[1]["messages"][-1]["content"]
    assert "coluna_inexistente" in correcao


def test_resultado_vazio_nao_chama_o_redator(make_client):
    llm = FakeLLM([{"relevante": True, "sql": "SELECT AVG(media_final) AS m FROM matriculas WHERE periodo_letivo = '1900.1'"}])
    r = make_client(llm).post("/api/chat", json={"pergunta": "Média em 1900.1?"})
    assert r.json()["resposta"] == SEM_RESULTADOS
    assert len(llm.chamadas) == 1


def test_sem_chave_openai_responde_503(make_client, db_path):
    sem_chave = Settings(_env_file=None, openai_api_key=None, database_path=db_path)
    r = make_client(None, sem_chave).post("/api/chat", json={"pergunta": "Quantos alunos?"})
    assert r.status_code == 503
    assert "OPENAI_API_KEY" in r.json()["detail"]


def test_pergunta_vazia_e_rejeitada(make_client):
    r = make_client(FakeLLM([])).post("/api/chat", json={"pergunta": ""})
    assert r.status_code == 422


def test_health(make_client):
    r = make_client(None).get("/api/health")
    assert r.json() == {"status": "ok", "banco": True, "llm_configurado": True}
