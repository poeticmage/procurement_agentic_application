from google.adk.tools import FunctionTool
from orchestrator.core.procurement_schema import ProcurementRequest

def validate_procurement(data: dict):
    return ProcurementRequest(**data).model_dump()

procurement_schema_tool = FunctionTool(validate_procurement)