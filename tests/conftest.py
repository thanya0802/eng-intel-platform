import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engintel import config, store  # noqa: E402

def point_config_at(base: Path):
    config.DATA_DIR = base
    config.RAW_DIR = base / "raw"
    config.STRUCTURED_DIR = base / "structured"
    config.INDEX_DIR = base / "index"
    config.DB_PATH = base / "warehouse.db"

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests are hermetic: a GEMINI_API_KEY in your shell must not switch them to the real API."""
    monkeypatch.setattr(config, "USE_LLM", False)

@pytest.fixture
def env(tmp_path):
    """Fresh, isolated warehouse + generated data for one test."""
    from data.generate import gen_pdfs, gen_structured
    point_config_at(tmp_path)
    gt = gen_structured(config.STRUCTURED_DIR)
    gen_pdfs(config.RAW_DIR)
    store.init_db()
    return {"gt": gt, "dir": tmp_path}

@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """Fully ingested + indexed environment shared by read-only tests."""
    from data.generate import gen_pdfs, gen_structured
    from engintel.ingest import ingest_folder
    from engintel.retrieval.index import build_index
    from engintel.structured import load_structured
    base = tmp_path_factory.mktemp("built")
    point_config_at(base)
    gt = gen_structured(config.STRUCTURED_DIR)
    gen_pdfs(config.RAW_DIR)
    store.init_db()
    load_structured(config.STRUCTURED_DIR, "test-structured")
    ingest_folder(config.RAW_DIR)
    build_index("lsa")
    return {"gt": gt, "dir": base}

@pytest.fixture
def use_built(built):
    point_config_at(built["dir"])   # other tests may have re-pointed config
    return built
