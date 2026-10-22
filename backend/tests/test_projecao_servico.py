from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_servico_projecao
from app.main import create_app
from app.projecao.calculo import ProjecaoErro
from app.projecao.servico import ServicoProjecao

RESULTADO = {
    "periodo_alvo": "2026.1",
    "periodos_ignorados": ["2025.1", "2025.2"],
    "linhas": [
        {"curso": "C1", "periodo_base": "2024.2", "periodo_alvo": "2026.1", "situacao": "ALUNOS ATIVOS", "quantidade": 9, "proporcao": 0.9},
        {"curso": "C1", "periodo_base": "2024.2", "periodo_alvo": "2026.1", "situacao": "EVASÃO", "quantidade": 1, "proporcao": 0.1},
    ],
    "erros": [],
    "gerado_em": "2026-10-22T10:00:00+00:00",
    "duracao_s": 1.0,
}


class Calculadora:
    def __init__(self, erro: Exception | None = None):
        self.chamadas = 0
        self.erro = erro

    def __call__(self, csv_path, periodos_ignorados):
        self.chamadas += 1
        if self.erro:
            raise self.erro
        return RESULTADO


@pytest.fixture
def arquivos(tmp_path):
    csv = tmp_path / "dados.csv"
    csv.write_text("conteudo v1", encoding="utf-8")
    algoritmo = tmp_path / "algoritmo.py"
    algoritmo.write_text("versao 1", encoding="utf-8")
    return csv, algoritmo, tmp_path / "cache" / "projecao.json"


def _servico(arquivos, calc, ignorados=("2025.1", "2025.2")):
    csv, algoritmo, cache = arquivos
    return ServicoProjecao(csv, cache, list(ignorados), calcular=calc, arquivos_do_algoritmo=[algoritmo])


def _rodar(servico, forcar=False):
    servico.iniciar(forcar)
    servico.aguardar(5)
    return servico.estado()


def test_calcula_e_grava_cache(arquivos):
    calc = Calculadora()
    estado = _rodar(_servico(arquivos, calc))
    assert estado["status"] == "pronto" and estado["origem"] == "calculo"
    assert estado["periodo_alvo"] == "2026.1" and len(estado["linhas"]) == 2
    assert calc.chamadas == 1
    assert arquivos[2].exists()


def test_reinicio_usa_o_cache_sem_retreinar(arquivos):
    _rodar(_servico(arquivos, Calculadora()))
    calc = Calculadora()
    estado = _rodar(_servico(arquivos, calc))  # "reinício da API"
    assert estado["status"] == "pronto" and estado["origem"] == "cache"
    assert calc.chamadas == 0


def test_csv_novo_invalida_o_cache(arquivos):
    _rodar(_servico(arquivos, Calculadora()))
    arquivos[0].write_text("conteudo v2", encoding="utf-8")
    calc = Calculadora()
    assert _rodar(_servico(arquivos, calc))["origem"] == "calculo"
    assert calc.chamadas == 1


def test_algoritmo_alterado_invalida_o_cache(arquivos):
    _rodar(_servico(arquivos, Calculadora()))
    arquivos[1].write_text("versao 2", encoding="utf-8")
    calc = Calculadora()
    _rodar(_servico(arquivos, calc))
    assert calc.chamadas == 1


def test_outros_periodos_ignorados_invalidam_o_cache(arquivos):
    _rodar(_servico(arquivos, Calculadora()))
    calc = Calculadora()
    _rodar(_servico(arquivos, calc, ignorados=("2025.2",)))
    assert calc.chamadas == 1


def test_atualizar_forca_recalculo(arquivos):
    calc = Calculadora()
    servico = _servico(arquivos, calc)
    _rodar(servico)
    _rodar(servico, forcar=True)
    assert calc.chamadas == 2


def test_cache_corrompido_e_ignorado(arquivos):
    arquivos[2].parent.mkdir(parents=True)
    arquivos[2].write_text("{nao e json", encoding="utf-8")
    calc = Calculadora()
    assert _rodar(_servico(arquivos, calc))["status"] == "pronto"
    assert calc.chamadas == 1


def test_falha_do_algoritmo_vira_status_erro(arquivos):
    estado = _rodar(_servico(arquivos, Calculadora(ProjecaoErro("CSV inválido"))))
    assert estado["status"] == "erro" and estado["mensagem"] == "CSV inválido"
    estado = _rodar(_servico(arquivos, Calculadora(RuntimeError("boom"))))
    assert estado["status"] == "erro" and "boom" in estado["mensagem"]


def test_falha_no_recalculo_mantem_o_ultimo_resultado(arquivos):
    calc = Calculadora()
    servico = _servico(arquivos, calc)
    _rodar(servico)
    calc.erro = RuntimeError("boom")
    estado = _rodar(servico, forcar=True)
    assert estado["status"] == "erro" and len(estado["linhas"]) == 2


def test_csv_ausente(tmp_path):
    from app.projecao.calculo import calcular_projecao

    servico = ServicoProjecao(tmp_path / "nao_existe.csv", tmp_path / "c.json", [], calcular=calcular_projecao)
    estado = _rodar(servico)
    assert estado["status"] == "erro" and "não encontrado" in estado["mensagem"]


def test_um_calculo_por_vez(arquivos):
    import threading

    liberar = threading.Event()

    def lento(csv_path, ignorados):
        liberar.wait(5)
        return RESULTADO

    servico = _servico(arquivos, lento)
    assert servico.iniciar() is True
    assert servico.estado()["status"] == "processando"
    assert servico.iniciar(forcar=True) is False
    liberar.set()
    servico.aguardar(5)
    assert servico.estado()["status"] == "pronto"


def test_endpoints(arquivos):
    calc = Calculadora()
    servico = _servico(arquivos, calc)
    app = create_app()
    app.dependency_overrides[get_servico_projecao] = lambda: servico
    client = TestClient(app)

    assert client.get("/api/projecao").json()["status"] == "desativado"

    r = client.post("/api/projecao/atualizar")
    assert r.status_code == 202
    servico.aguardar(5)
    body = client.get("/api/projecao").json()
    assert body["status"] == "pronto"
    assert body["linhas"][0] == RESULTADO["linhas"][0]
    assert calc.chamadas == 1
