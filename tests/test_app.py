import pytest
from fastapi.testclient import TestClient

from app.csv_storage import CSV_FIELDS
from app.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def add_position(client: TestClient, name: str) -> None:
    response = client.post("/api/positions", json={"name": name})
    assert response.status_code == 201, response.text


def independent_rules(base_salary: float = 0, bonus: float = 0) -> list[dict]:
    return [
        {
            "level": level,
            "base_salary": base_salary,
            "bonus": bonus,
            "from_position": None,
            "from_level": None,
            "formula_salary": "",
            "formula_bonus": "",
        }
        for level in range(1, 5)
    ]


def test_index_and_empty_state(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "Salary Dependency Manager" in response.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/api/state").json() == {"positions": [], "dependencies": []}


def test_positions_rules_and_cross_position_calculation(client: TestClient):
    add_position(client, "Developer")
    add_position(client, "Manager")

    developer_rules = independent_rules()
    developer_rules[0]["base_salary"] = 30_000
    developer_rules[0]["bonus"] = 3_000
    developer_rules[1].update(
        {
            "from_position": "Developer",
            "from_level": 1,
            "formula_salary": "S * 1.2",
            "formula_bonus": "B + 500",
        }
    )
    response = client.put("/api/positions/Developer/rules", json={"rules": developer_rules})
    assert response.status_code == 200, response.text

    manager_rules = independent_rules()
    manager_rules[0].update(
        {
            "from_position": "Developer",
            "from_level": 2,
            "formula_salary": "S * 1.25",
            "formula_bonus": "B * 1.1",
        }
    )
    response = client.put("/api/positions/Manager/rules", json={"rules": manager_rules})
    assert response.status_code == 200, response.text

    state = response.json()
    developer = next(item for item in state["positions"] if item["name"] == "Developer")
    manager = next(item for item in state["positions"] if item["name"] == "Manager")
    assert developer["levels"][1]["base_salary"] == 36_000
    assert developer["levels"][1]["bonus"] == 3_500
    assert manager["levels"][0]["base_salary"] == 45_000
    assert manager["levels"][0]["bonus"] == pytest.approx(3_850)
    assert len(state["dependencies"]) == 2


def test_csv_round_trip_restores_values_and_dependencies(client: TestClient):
    add_position(client, "Architect")
    rules = independent_rules(10_000, 1_000)
    rules[1].update(
        {
            "from_position": "Architect",
            "from_level": 1,
            "formula_salary": "S + 2500",
            "formula_bonus": "B * 1.5",
        }
    )
    response = client.put("/api/positions/Architect/rules", json={"rules": rules})
    assert response.status_code == 200
    expected_state = response.json()

    exported = client.get("/api/export")
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert "META,salary-dependency-manager-web,1" in exported.content.decode("utf-8-sig")

    client.delete("/api/positions/Architect")
    assert client.get("/api/state").json()["positions"] == []

    imported = client.post(
        "/api/import",
        content=exported.content,
        headers={"Content-Type": "text/csv"},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json() == expected_state


@pytest.mark.parametrize(
    "content",
    [
        b"name,age,city\nAlice,30,Kyiv\n",
        (",".join(CSV_FIELDS) + "\n").encode(),
        b"",
        bytes([0xFF, 0xFE, 0xFD]),
    ],
)
def test_foreign_csv_is_rejected_without_state_loss(client: TestClient, content: bytes):
    add_position(client, "Original")
    before = client.get("/api/state").json()

    response = client.post(
        "/api/import",
        content=content,
        headers={"Content-Type": "text/csv"},
    )

    assert response.status_code == 400
    assert client.get("/api/state").json() == before


def test_cycle_is_rejected_atomically(client: TestClient):
    add_position(client, "A")
    add_position(client, "B")

    rules_a = independent_rules(100, 10)
    rules_a[0].update(
        {
            "from_position": "B",
            "from_level": 1,
            "formula_salary": "S",
            "formula_bonus": "B",
        }
    )
    assert client.put("/api/positions/A/rules", json={"rules": rules_a}).status_code == 200
    before = client.get("/api/state").json()

    rules_b = independent_rules(200, 20)
    rules_b[0].update(
        {
            "from_position": "A",
            "from_level": 1,
            "formula_salary": "S",
            "formula_bonus": "B",
        }
    )
    response = client.put("/api/positions/B/rules", json={"rules": rules_b})

    assert response.status_code == 400
    assert "циклічну" in response.json()["detail"]
    assert client.get("/api/state").json() == before


def test_delete_position_removes_related_dependencies(client: TestClient):
    add_position(client, "Source")
    add_position(client, "Target")
    rules = independent_rules()
    rules[0].update(
        {
            "from_position": "Source",
            "from_level": 1,
            "formula_salary": "S",
            "formula_bonus": "B",
        }
    )
    assert client.put("/api/positions/Target/rules", json={"rules": rules}).status_code == 200

    response = client.delete("/api/positions/Source")
    assert response.status_code == 200
    target = response.json()["positions"][0]
    assert response.json()["dependencies"] == []
    assert target["levels"][0]["from_position"] is None
