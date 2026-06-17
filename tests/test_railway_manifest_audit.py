from scripts.railway_manifest_audit import audit


def _status(manifest, config_file="/railway.toml"):
    return {
        "environments": {
            "edges": [
                {
                    "node": {
                        "name": "Pi-Dev-Ops-pr-344",
                        "serviceInstances": {
                            "edges": [
                                {
                                    "node": {
                                        "serviceName": "Pi-Dev-Ops",
                                        "latestDeployment": {
                                            "id": "dep_1",
                                            "status": "BUILDING",
                                            "meta": {
                                                "commitHash": "abc123",
                                                "configFile": config_file,
                                                "serviceManifest": manifest,
                                            },
                                        },
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        }
    }


def test_audit_passes_dockerfile_manifest():
    report = audit(
        _status({
            "build": {"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"},
            "deploy": {
                "startCommand": "uvicorn app.server.main:app --host 0.0.0.0 --port 8080 --workers 1",
                "healthcheckPath": "/health",
                "healthcheckTimeout": 30,
            },
        }),
        environment="Pi-Dev-Ops-pr-344",
        service="Pi-Dev-Ops",
    )

    assert report["ok"] is True
    assert report["checked"] == 1
    assert report["results"][0]["mismatches"] == []


def test_audit_accepts_railway_json_config_and_absolute_dockerfile_path():
    report = audit(
        _status(
            {
                "build": {"builder": "DOCKERFILE", "dockerfilePath": "/Dockerfile"},
                "deploy": {
                    "startCommand": "uvicorn app.server.main:app --host 0.0.0.0 --port 8080 --workers 1",
                    "healthcheckPath": "/health",
                    "healthcheckTimeout": 30,
                },
            },
            config_file="/railway.json",
        ),
        environment="Pi-Dev-Ops-pr-344",
        service="Pi-Dev-Ops",
    )

    assert report["ok"] is True
    assert report["results"][0]["mismatches"] == []


def test_audit_fails_railpack_manifest_drift():
    report = audit(
        _status({
            "build": {"builder": "RAILPACK", "dockerfilePath": None},
            "deploy": {"startCommand": None, "healthcheckPath": None, "healthcheckTimeout": None},
        }),
        environment="Pi-Dev-Ops-pr-344",
        service="Pi-Dev-Ops",
    )

    assert report["ok"] is False
    assert report["results"][0]["mismatches"][0] == {
        "path": "build.builder",
        "expected": "DOCKERFILE",
        "actual": "RAILPACK",
    }


def test_audit_fails_when_railway_ignores_config_as_code():
    report = audit(
        _status({
            "build": {"builder": "RAILPACK", "dockerfilePath": None},
            "deploy": {"startCommand": None, "healthcheckPath": None, "healthcheckTimeout": None},
        }, config_file=None),
        environment="Pi-Dev-Ops-pr-344",
        service="Pi-Dev-Ops",
    )

    assert report["ok"] is False
    assert report["results"][0]["mismatches"][0] == {
        "path": "configFile",
        "expected": ["/railway.json", "/railway.toml"],
        "actual": None,
    }
