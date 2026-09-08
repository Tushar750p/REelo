import os
import tempfile

os.environ.setdefault("REELO_SECRET", "ci-test-secret-change-me")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")


def test_security_helpers_import():
    from security import install_security
    assert callable(install_security)


def test_production_infrastructure_rate_limit():
    from production_infra import rate_limit
    key = "ci-smoke-test"
    allowed, retry = rate_limit(key, limit=1, window=60)
    assert allowed is True
    allowed, retry = rate_limit(key, limit=1, window=60)
    assert allowed is False
    assert retry >= 1


def test_application_import():
    import app
    assert app.app.title == "REelo API"
