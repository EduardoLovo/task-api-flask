import pytest

from tests.conftest import create_task, expect_error, register_user


@pytest.fixture
def alice(client):
    return register_user(client)


@pytest.fixture
def bob(client):
    return register_user(client)


def titles(res):
    return [task["title"] for task in res.get_json()["data"]]


def test_exige_autenticacao(client):
    expect_error(client.get("/tasks"), 401, "MISSING_TOKEN")
    expect_error(client.get("/tasks/1"), 401, "MISSING_TOKEN")


class TestCreate:
    def test_cria_com_valores_padrao_e_location(self, client, alice):
        res = client.post("/tasks", json={"title": "  Estudar Flask  "}, headers=alice["auth"])
        assert res.status_code == 201
        task = res.get_json()["data"]
        assert res.headers["Location"] == f"/tasks/{task['id']}"
        assert task == {
            "id": task["id"],
            "title": "Estudar Flask",
            "description": None,
            "status": "pending",
            "priority": "medium",
            "dueDate": None,
            "createdAt": task["createdAt"],
            "updatedAt": task["updatedAt"],
        }
        assert list(task) == ["id", "title", "description", "status", "priority", "dueDate", "createdAt", "updatedAt"]

    def test_cria_com_todos_os_campos(self, client, alice):
        res = client.post(
            "/tasks",
            json={
                "title": "Deploy",
                "description": "Subir para produção",
                "status": "in_progress",
                "priority": "high",
                "dueDate": "2026-12-31",
            },
            headers=alice["auth"],
        )
        assert res.status_code == 201
        task = res.get_json()["data"]
        assert (task["status"], task["priority"], task["dueDate"]) == ("in_progress", "high", "2026-12-31")

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            ({}, "title"),
            ({"title": "   "}, "title"),
            ({"title": "x" * 121}, "title"),
            ({"title": 42}, "title"),
            ({"title": "a", "status": "feito"}, "status"),
            ({"title": "a", "priority": "urgent"}, "priority"),
            ({"title": "a", "dueDate": "31/12/2026"}, "dueDate"),
            ({"title": "a", "dueDate": "2026-02-30"}, "dueDate"),
            ({"title": "a", "description": "x" * 1001}, "description"),
            ({"title": "a", "userId": 2}, "userId"),
            ({"title": "a", "due_date": "2026-12-31"}, "due_date"),
        ],
        ids=[
            "titulo-ausente",
            "titulo-vazio",
            "titulo-longo",
            "titulo-nao-texto",
            "status-invalido",
            "prioridade-invalida",
            "data-formato-errado",
            "data-impossivel",
            "descricao-longa",
            "campo-extra",
            "snake-case-nao-aceito",
        ],
    )
    def test_400(self, client, alice, body, field):
        error = expect_error(client.post("/tasks", json=body, headers=alice["auth"]), 400, "VALIDATION_ERROR")
        assert field in [d["field"] for d in error["details"]]


class TestList:
    def test_lista_so_as_tarefas_do_proprio_usuario(self, client, alice, bob):
        create_task(client, alice["auth"], title="Da Alice")
        create_task(client, bob["auth"], title="Do Bob")
        res = client.get("/tasks", headers=alice["auth"])
        assert res.status_code == 200
        assert titles(res) == ["Da Alice"]
        assert res.get_json()["meta"] == {"page": 1, "limit": 10, "total": 1, "totalPages": 1}

    def test_lista_vazia(self, client, alice):
        res = client.get("/tasks", headers=alice["auth"])
        assert res.get_json() == {"data": [], "meta": {"page": 1, "limit": 10, "total": 0, "totalPages": 0}}

    def test_filtra_por_status_prioridade_e_busca(self, client, alice):
        create_task(client, alice["auth"], title="Comprar pão", status="done", priority="low")
        create_task(client, alice["auth"], title="Comprar leite", status="pending", priority="low")
        create_task(client, alice["auth"], title="Estudar", description="comprar livro", priority="high")

        assert titles(client.get("/tasks?status=done", headers=alice["auth"])) == ["Comprar pão"]
        by_search = client.get("/tasks?search=comprar&priority=low", headers=alice["auth"])
        assert by_search.get_json()["meta"]["total"] == 2
        assert titles(client.get("/tasks?search=livro", headers=alice["auth"])) == ["Estudar"]

    def test_trata_curinga_da_busca_como_texto(self, client, alice):
        create_task(client, alice["auth"], title="100% feito")
        create_task(client, alice["auth"], title="outra coisa")
        assert titles(client.get("/tasks?search=%25", headers=alice["auth"])) == ["100% feito"]

    def test_pagina_e_ordena(self, client, alice):
        for title, priority in [("b", "low"), ("a", "high"), ("c", "medium")]:
            create_task(client, alice["auth"], title=title, priority=priority)

        page1 = client.get("/tasks?sortBy=title&order=asc&limit=2&page=1", headers=alice["auth"])
        assert titles(page1) == ["a", "b"]
        assert page1.get_json()["meta"] == {"page": 1, "limit": 2, "total": 3, "totalPages": 2}

        page2 = client.get("/tasks?sortBy=title&order=asc&limit=2&page=2", headers=alice["auth"])
        assert titles(page2) == ["c"]

        by_priority = client.get("/tasks?sortBy=priority&order=desc", headers=alice["auth"])
        assert [t["priority"] for t in by_priority.get_json()["data"]] == ["high", "medium", "low"]

    def test_ordena_por_prazo_com_sem_prazo_no_final(self, client, alice):
        create_task(client, alice["auth"], title="sem prazo")
        create_task(client, alice["auth"], title="depois", dueDate="2026-12-01")
        create_task(client, alice["auth"], title="antes", dueDate="2026-11-01")
        for order in ("asc", "desc"):
            res = client.get(f"/tasks?sortBy=dueDate&order={order}", headers=alice["auth"])
            assert titles(res)[-1] == "sem prazo"

    @pytest.mark.parametrize(
        ("query", "field"),
        [
            ("page=0", "page"),
            ("page=abc", "page"),
            ("page=1.5", "page"),
            ("limit=101", "limit"),
            ("status=feito", "status"),
            ("sortBy=senha", "sortBy"),
            ("order=up", "order"),
            ("search=", "search"),
            ("status=done&status=pending", "status"),
            ("foo=bar", "foo"),
        ],
    )
    def test_400_para_query_invalida(self, client, alice, query, field):
        error = expect_error(client.get(f"/tasks?{query}", headers=alice["auth"]), 400, "VALIDATION_ERROR")
        assert error["details"][0]["location"] == "query"
        assert error["details"][0]["field"] == field


class TestGet:
    def test_devolve_a_tarefa(self, client, alice):
        task = create_task(client, alice["auth"])
        res = client.get(f"/tasks/{task['id']}", headers=alice["auth"])
        assert res.status_code == 200
        assert res.get_json()["data"] == task

    def test_404_tarefa_inexistente(self, client, alice):
        expect_error(client.get("/tasks/9999", headers=alice["auth"]), 404, "TASK_NOT_FOUND")

    def test_403_tarefa_de_outro_usuario(self, client, alice, bob):
        task = create_task(client, bob["auth"])
        expect_error(client.get(f"/tasks/{task['id']}", headers=alice["auth"]), 403, "FORBIDDEN")

    @pytest.mark.parametrize("task_id", ["abc", "0", "-1", "1.5", "01", "9999999999999999"])
    def test_400_para_id_invalido(self, client, alice, task_id):
        error = expect_error(client.get(f"/tasks/{task_id}", headers=alice["auth"]), 400, "VALIDATION_ERROR")
        assert error["details"][0] == {
            "location": "params",
            "field": "id",
            "message": "ID deve ser um número inteiro positivo",
        }


class TestUpdate:
    def test_atualiza_so_os_campos_enviados(self, client, alice):
        task = create_task(client, alice["auth"], title="Original", priority="low")
        res = client.patch(f"/tasks/{task['id']}", json={"status": "done"}, headers=alice["auth"])
        assert res.status_code == 200
        updated = res.get_json()["data"]
        assert (updated["title"], updated["priority"], updated["status"]) == ("Original", "low", "done")
        assert updated["updatedAt"] >= task["updatedAt"]

    def test_permite_limpar_descricao_e_prazo_com_null(self, client, alice):
        task = create_task(client, alice["auth"], description="x", dueDate="2026-12-31")
        res = client.patch(f"/tasks/{task['id']}", json={"description": None, "dueDate": None}, headers=alice["auth"])
        updated = res.get_json()["data"]
        assert (updated["description"], updated["dueDate"]) == (None, None)

    def test_400_para_corpo_vazio(self, client, alice):
        task = create_task(client, alice["auth"])
        error = expect_error(client.patch(f"/tasks/{task['id']}", json={}, headers=alice["auth"]), 400, "VALIDATION_ERROR")
        assert error["details"][0]["message"] == "Informe ao menos um campo para atualizar"

    @pytest.mark.parametrize("field", ["title", "status", "priority"])
    def test_400_para_null_em_campo_obrigatorio(self, client, alice, field):
        task = create_task(client, alice["auth"])
        res = client.patch(f"/tasks/{task['id']}", json={field: None}, headers=alice["auth"])
        expect_error(res, 400, "VALIDATION_ERROR")

    def test_400_reune_erros_de_params_e_body(self, client, alice):
        error = expect_error(
            client.patch("/tasks/abc", json={"status": "x"}, headers=alice["auth"]), 400, "VALIDATION_ERROR"
        )
        assert [d["location"] for d in error["details"]] == ["params", "body"]

    def test_404_e_403(self, client, alice, bob):
        bob_task = create_task(client, bob["auth"])
        expect_error(client.patch("/tasks/9999", json={"title": "x"}, headers=alice["auth"]), 404, "TASK_NOT_FOUND")
        expect_error(
            client.patch(f"/tasks/{bob_task['id']}", json={"title": "x"}, headers=alice["auth"]), 403, "FORBIDDEN"
        )


class TestDelete:
    def test_remove_e_devolve_204_sem_corpo(self, client, alice):
        task = create_task(client, alice["auth"])
        res = client.delete(f"/tasks/{task['id']}", headers=alice["auth"])
        assert res.status_code == 204
        assert res.data == b""
        expect_error(client.get(f"/tasks/{task['id']}", headers=alice["auth"]), 404, "TASK_NOT_FOUND")

    def test_403_ao_remover_tarefa_de_outro_usuario_sem_apagar(self, client, alice, bob):
        task = create_task(client, bob["auth"])
        expect_error(client.delete(f"/tasks/{task['id']}", headers=alice["auth"]), 403, "FORBIDDEN")
        assert client.get(f"/tasks/{task['id']}", headers=bob["auth"]).status_code == 200
