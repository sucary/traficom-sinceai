from pathlib import Path
import sys

BACKEND_SOURCE = Path(__file__).resolve().parents[1] / "src"
if str(BACKEND_SOURCE) not in sys.path:
    sys.path.insert(0, str(BACKEND_SOURCE))

from app.web_api import main


if __name__ == "__main__":
    sys.exit(main())
