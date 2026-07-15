"""Production embedding/index routing must remain dimensionally consistent."""

import inspect
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_apply as da  # noqa: E402
import dream_digest as dd  # noqa: E402
import dream_runner as dr  # noqa: E402
import goethe  # noqa: E402


PRODUCTION_EMBED_MODEL = "qwen3-embedding:0.6b"
PRODUCTION_ERROR_INDEX = "lse-errors-1024"


def _valve_default(model, field_name):
    fields = getattr(model, "model_fields", None) or getattr(model, "__fields__")
    return fields[field_name].default


def test_all_production_kb_writers_default_to_qwen_1024(monkeypatch):
    monkeypatch.delenv("GOETHE_EMBED_MODEL", raising=False)
    assert _valve_default(goethe.Tools.Valves, "EMBED_MODEL") == PRODUCTION_EMBED_MODEL
    assert dr._embed_model_default() == PRODUCTION_EMBED_MODEL
    assert da._embed_model_default() == PRODUCTION_EMBED_MODEL


def test_error_surface_routes_only_to_1024_index():
    record_error_source = inspect.getsource(goethe.Tools.record_error)
    check_error_source = inspect.getsource(goethe.Tools.check_error_kb)
    crash_source = inspect.getsource(dr.record_crash_error)

    for source in (record_error_source, check_error_source, crash_source):
        assert PRODUCTION_ERROR_INDEX in source
        assert 'index="lse-errors",' not in source
    assert PRODUCTION_ERROR_INDEX in inspect.getsource(goethe.Tools.run_tests)
    assert dd.KB_INDICES == ("lse-kb", PRODUCTION_ERROR_INDEX, "lse-skills")
