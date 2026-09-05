import pytest
from fastapi.testclient import TestClient

import murdoku.webapp as webapp_module
from murdoku.webapp import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # cada test usa su propia carpeta de niveles, para no tocar ni leer los
    # niveles reales que el usuario tenga generados en puzzles/generated.
    monkeypatch.setattr(webapp_module, "PUZZLES_DIR", tmp_path / "generated")
    return TestClient(app)


def _generar(client: TestClient, **overrides) -> str:
    data = {"difficulty": "easy", "theme": "", "name": ""} | overrides
    response = client.post("/generar", data=data, follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    return location.removeprefix("/jugar/")


def test_inicio_links_to_listado_and_generar(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/niveles"' in response.text
    assert 'href="/generar"' in response.text


def test_listado_vacio_muestra_mensaje(client: TestClient):
    response = client.get("/niveles")
    assert response.status_code == 200
    assert "Todavia no has generado ningun nivel." in response.text


def test_generar_form_lists_every_difficulty(client: TestClient):
    response = client.get("/generar")
    assert response.status_code == 200
    for label in ("Facil", "Medio", "Dificil", "Experto"):
        assert label in response.text


def test_generar_submit_creates_a_puzzle_and_redirects_to_jugar(client: TestClient):
    puzzle_id = _generar(client, name="El misterio del vestuario")
    response = client.get(f"/jugar/{puzzle_id}")
    assert response.status_code == 200
    assert "El misterio del vestuario" in response.text


def test_generar_submit_defaults_to_caso_generado_when_name_is_blank(client: TestClient):
    puzzle_id = _generar(client)
    response = client.get(f"/jugar/{puzzle_id}")
    assert "Caso generado" in response.text


def test_generar_submit_falls_back_to_easy_on_an_unknown_difficulty(client: TestClient):
    # un valor de dificultad que no existe (manipulado a mano en el form)
    # no debe tumbar el generador -- se trata como "easy".
    puzzle_id = _generar(client, difficulty="imposible")
    response = client.get(f"/jugar/{puzzle_id}")
    assert response.status_code == 200


def test_generar_submit_with_theme_calls_reskin_puzzle(client: TestClient, monkeypatch):
    seen = {}

    def _fake_reskin(puzzle, theme, client):
        seen["theme"] = theme
        return puzzle.model_copy(update={"theme_vocabulary": {"__marker__": theme}})

    monkeypatch.setattr(webapp_module, "_client", lambda: object())
    monkeypatch.setattr(webapp_module, "reskin_puzzle", _fake_reskin)

    puzzle_id = _generar(client, theme="piratas")
    assert seen["theme"] == "piratas"

    response = client.get(f"/jugar/{puzzle_id}")
    assert response.status_code == 200


def test_generar_submit_without_theme_never_calls_reskin_puzzle(client: TestClient, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("reskin_puzzle no deberia llamarse sin tema")

    monkeypatch.setattr(webapp_module, "reskin_puzzle", _boom)
    _generar(client, theme="")


def test_generar_submit_warns_when_theming_falls_back_to_generic(client: TestClient, monkeypatch):
    # reskin_puzzle devuelve el puzzle tal cual (sin theme_vocabulary)
    # cuando ningun intento de tematizar supero la verificacion -- la
    # webapp debe avisar de eso en vez de servir un caso generico en
    # silencio, como si el tema pedido se hubiera aplicado.
    monkeypatch.setattr(webapp_module, "_client", lambda: object())
    monkeypatch.setattr(webapp_module, "reskin_puzzle", lambda puzzle, theme, client: puzzle)

    puzzle_id = _generar(client, theme="futbol")

    jugar = client.get(f"/jugar/{puzzle_id}")
    assert "No se pudo aplicar la tematica" in jugar.text

    listado = client.get("/niveles")
    assert "(no aplicado)" in listado.text


def test_generar_submit_no_warning_when_theming_succeeds(client: TestClient, monkeypatch):
    monkeypatch.setattr(webapp_module, "_client", lambda: object())
    monkeypatch.setattr(
        webapp_module,
        "reskin_puzzle",
        lambda puzzle, theme, client: puzzle.model_copy(update={"theme_vocabulary": {"silla": "trono"}}),
    )

    puzzle_id = _generar(client, theme="medieval")

    jugar = client.get(f"/jugar/{puzzle_id}")
    assert "No se pudo aplicar la tematica" not in jugar.text

    listado = client.get("/niveles")
    assert "(no aplicado)" not in listado.text


def test_generar_submit_without_theme_has_no_theme_failed_warning(client: TestClient):
    puzzle_id = _generar(client, theme="")
    jugar = client.get(f"/jugar/{puzzle_id}")
    assert "No se pudo aplicar la tematica" not in jugar.text


def test_listado_escapes_a_scenario_name_containing_markup(client: TestClient):
    # el nombre del caso lo escribe el usuario en el formulario -- si se
    # inyecta tal cual en el listado, un nombre como este ejecutaria un
    # script cada vez que alguien abre /niveles.
    _generar(client, name='<script>alert(1)</script>')
    response = client.get("/niveles")
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_listado_escapes_a_theme_containing_markup(client: TestClient, monkeypatch):
    monkeypatch.setattr(webapp_module, "_client", lambda: object())
    monkeypatch.setattr(webapp_module, "reskin_puzzle", lambda puzzle, theme, client: puzzle)
    _generar(client, theme='"><img src=x onerror=alert(1)>')
    response = client.get("/niveles")
    assert "<img src=x" not in response.text


def test_editar_nombre_form_escapes_a_name_containing_quotes(client: TestClient):
    # un nombre con comillas dobles sin escapar rompe fuera del atributo
    # value="..." e inyecta markup arbitrario en el propio formulario.
    puzzle_id = _generar(client, name='"><script>alert(1)</script>')
    response = client.get(f"/niveles/{puzzle_id}/editar")
    assert "<script>alert(1)</script>" not in response.text


def test_listado_shows_a_card_for_each_generated_puzzle(client: TestClient):
    _generar(client, name="Caso Uno")
    _generar(client, name="Caso Dos")
    response = client.get("/niveles")
    assert "Caso Uno" in response.text
    assert "Caso Dos" in response.text
    assert "Editar nombre" in response.text
    assert "Borrar" in response.text


def test_jugar_unknown_puzzle_returns_404(client: TestClient):
    response = client.get("/jugar/no-existe")
    assert response.status_code == 404


def test_editar_nombre_form_prefills_the_current_name(client: TestClient):
    puzzle_id = _generar(client, name="Nombre original")
    response = client.get(f"/niveles/{puzzle_id}/editar")
    assert response.status_code == 200
    assert 'value="Nombre original"' in response.text


def test_editar_nombre_form_unknown_puzzle_returns_404(client: TestClient):
    response = client.get("/niveles/no-existe/editar")
    assert response.status_code == 404


def test_editar_nombre_submit_renames_and_redirects(client: TestClient):
    puzzle_id = _generar(client, name="Nombre original")
    response = client.post(
        f"/niveles/{puzzle_id}/editar", data={"name": "Nombre nuevo"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/niveles"

    listado = client.get("/niveles")
    assert "Nombre nuevo" in listado.text
    assert "Nombre original" not in listado.text


def test_editar_nombre_submit_blank_falls_back_to_caso_generado(client: TestClient):
    puzzle_id = _generar(client, name="Nombre original")
    client.post(f"/niveles/{puzzle_id}/editar", data={"name": "  "}, follow_redirects=False)
    listado = client.get("/niveles")
    assert "Caso generado" in listado.text


def test_borrar_nivel_removes_it_from_the_listado(client: TestClient):
    puzzle_id = _generar(client, name="Caso a borrar")
    response = client.post(f"/niveles/{puzzle_id}/borrar", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/niveles"

    listado = client.get("/niveles")
    assert "Caso a borrar" not in listado.text
    assert "Todavia no has generado ningun nivel." in listado.text


def test_borrar_nivel_unknown_puzzle_does_not_error(client: TestClient):
    response = client.post("/niveles/no-existe/borrar", follow_redirects=False)
    assert response.status_code == 303
