import sys
import os
import tempfile
from pathlib import Path

BACKEND=Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0,str(BACKEND))

TEST_DB=Path(tempfile.gettempdir())/f"careconnect-pytest-{os.getpid()}.db"
os.environ["DATABASE_URL"]="sqlite:///"+TEST_DB.as_posix()

def pytest_sessionfinish(session,exitstatus):
    from app.main import engine
    engine.dispose()
    for suffix in ("","-wal","-shm"):
        Path(str(TEST_DB)+suffix).unlink(missing_ok=True)
