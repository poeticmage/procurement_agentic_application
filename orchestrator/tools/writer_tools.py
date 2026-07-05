import yaml
from pathlib import Path
from google.adk.tools import FunctionTool

POLICY_DIR = Path(__file__).resolve().parents[1] / "agents" / "writer"

def _load_yaml(filename: str):
    with open(POLICY_DIR / filename, "r") as f:
        # print("POLICY_DIR =", POLICY_DIR)
        # print("FILE =", POLICY_DIR / "category_policies.yaml")
        return yaml.safe_load(f)


def get_category_policy(category: str):
    data = _load_yaml("category_policies.yaml")
    return data.get(category.lower())


def get_compliance_policy(category: str):
    data = _load_yaml("compliance.yaml")
    return data.get(category.lower())


def get_vendor_rules(category: str):
    data = _load_yaml("vendor_rules.yaml")
    return data.get(category.lower())


def get_procurement_method(category: str):
    data = _load_yaml("procurement_methods.yaml")
    return data.get(category.lower())


def get_approval_policy(category: str):
    data = _load_yaml("approvals.yaml")
    return data.get(category.lower())


def get_complete_policy_bundle(category: str):
    return {
        "category_policy": get_category_policy(category),
        "compliance_policy": get_compliance_policy(category),
        "vendor_rules": get_vendor_rules(category),
        "procurement_method": get_procurement_method(category),
        "approval_policy": get_approval_policy(category),
    }



category_policy_tool = FunctionTool(get_category_policy)

compliance_policy_tool = FunctionTool(get_compliance_policy)

vendor_rules_tool = FunctionTool(get_vendor_rules)

procurement_method_tool = FunctionTool(get_procurement_method)

approval_policy_tool = FunctionTool(get_approval_policy)

complete_policy_bundle_tool = FunctionTool(get_complete_policy_bundle)