import json
from pathlib import Path
from pydantic import BaseModel
from google.adk.tools import LongRunningFunctionTool


BASE_DIR = Path("src/ai-agent-output").resolve()


def _read_json(file_path: str) -> dict:
    """
    Reads JSON safely from disk.
    """

    path = (BASE_DIR / file_path).resolve()

    if not str(path).startswith(str(BASE_DIR)):
        raise ValueError("Access denied: invalid path")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    


read_json_tool = LongRunningFunctionTool(
    func=_read_json)