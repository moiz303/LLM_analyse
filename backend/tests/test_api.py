from fastapi.testclient import TestClient


def test_model_health_and_prediction(test_app):
    client = TestClient(test_app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    model_response = client.get("/api/model")
    assert model_response.status_code == 200
    model = model_response.json()
    assert model["model_id"] == "test_model"
    assert model["baseline"]["metrics"]["accuracy_top1"] == 0.75

    prediction = client.post(
        "/api/predict",
        json={"parameters": {"param_a": 0.5, "param_b": 1.0}},
    )
    assert prediction.status_code == 200
    assert prediction.json()["prediction"]["accuracy_top1"] == 0.75


def test_invalid_prediction_is_rejected(test_app):
    client = TestClient(test_app)
    response = client.post("/api/predict", json={"parameters": {"param_a": 0.5}})
    assert response.status_code == 422


def test_reset_reads_source_not_user_buffer(test_app):
    client = TestClient(test_app)
    client.post(
        "/api/predict",
        json={"parameters": {"param_a": 0.9, "param_b": 1.4}},
    )
    reset = client.post("/api/reset")
    assert reset.status_code == 200
    assert reset.json()["configuration"] == {"param_a": 0.5, "param_b": 1.0}
    source_buffer = test_app.state.settings.model_path.read_text()
    assert '"source_experiment"' not in source_buffer