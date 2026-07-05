
import json
import uuid
from dataclasses import dataclass
from google.genai import types
from google import genai
from datetime import datetime, timezone
from orchestrator.core.procurement_schema import ProcurementRequest
from orchestrator.core.workflow_state import WorkflowState
from orchestrator.tools.writer_tools import vendor_rules_tool
from orchestrator.tools.writer_tools import get_vendor_rules
from orchestrator.core.config import get_user_id, get_session_id
from orchestrator.tools.procurement_document_tool import write_procurement_pdf
from orchestrator.core.procurement_document_schema import ProcurementDocument
from orchestrator.prompts.root_agent_instructions import NEXT_QUESTION_PROMPT
from orchestrator.prompts.root_agent_instructions import MARKET_RESEARCH_PROMPT
from orchestrator.prompts.root_agent_instructions import RECOMMENDATION_REVIEW_PROMPT
from orchestrator.prompts.root_agent_instructions import VENDOR_SELECTION_PROMPT
from orchestrator.prompts.root_agent_instructions import BUDGET_CONFIRMATION_PROMPT
from orchestrator.prompts.root_agent_instructions import DELIVERY_TIMELINE_PROMPT
from orchestrator.prompts.root_agent_instructions import DELIVERY_LOCATION_PROMPT
from orchestrator.core.models import Money

_ACTIVE_PROCUREMENT_CONTEXT = None

# ---------------------------------------------------------------------------
# Utilities (unchanged)
# ---------------------------------------------------------------------------

def extract_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def coerce_dict(value) -> dict | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        dicts = [item for item in value if isinstance(item, dict)]
        if len(dicts) == 1:
            return dicts[0]
    return None

def coerce_dict_list(value) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        for key in (
            "recommended_vendors", "items", "vendors",
            "vendor_recommendations", "recommendations", "products",
        ):
            if key in value:
                return coerce_dict_list(value[key])
        return [value]
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                result.append(item)
            elif isinstance(item, list):
                result.extend(coerce_dict_list(item))
        return result
    return []

def coerce_llm_dict(value, fallback: dict) -> dict:
    coerced = coerce_dict(value)
    return coerced if coerced is not None else fallback

def apply_vendor_payload(context, raw) -> bool:
    vendor_items = [
        item for item in coerce_dict_list(raw)
        if isinstance(item, dict) and (item.get("vendor_name") or item.get("name"))
    ]
    if not vendor_items:
        return False
    for vendor in vendor_items:
        name = vendor.get("vendor_name") or vendor.get("name")
        if name and name not in context.vendor_history:
            context.vendor_history.append(name)
    context.vendor_recommendations = vendor_items
    return True

DOCUMENT_FACT_KEYS = {
    "category",
    "business_purpose",
    "normalized_budget_per_item",
    "calculated_total_budget",
    "product_model",
    "product_specifications",
    "shortlisted_products",
    "selected_product_summary",
    "shortlisted_vendors",
    "vendor_comparison_summary",
    "selected_vendor_summary",
    "procurement_method",
    "approval_requirements",
    "procurement_justification",
}


def ensure_document_facts(context):
    context.metadata.setdefault("document_facts", {
        "category": None,
        "business_purpose": None,
        "normalized_budget_per_item": None,
        "calculated_total_budget": None,
        "product_model": None,
        "product_specifications": [],
        "shortlisted_products": [],
        "selected_product_summary": None,
        "shortlisted_vendors": [],
        "vendor_comparison_summary": None,
        "selected_vendor_summary": None,
        "procurement_method": None,
        "approval_requirements": None,
        "procurement_justification": None,
    })
    return context.metadata["document_facts"]


LIST_FACT_KEYS = {
    "product_specifications",
    "shortlisted_products",
    "shortlisted_vendors",
}

DICT_FACT_KEYS = {
    "approval_requirements",
}


def _dedupe_list(values):
    seen = set()
    result = []
    for item in values:
        marker = json.dumps(item, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def merge_document_facts(context, extracted_facts: dict):
    document_facts = ensure_document_facts(context)
    for key, value in (extracted_facts or {}).items():
        if key not in DOCUMENT_FACT_KEYS:
            continue
        if value is None or value == "" or value == [] or value == {}:
            continue
        if key in LIST_FACT_KEYS:
            existing = document_facts.get(key) or []
            incoming = value if isinstance(value, list) else [value]
            document_facts[key] = _dedupe_list(existing + incoming)
            continue
        if key in DICT_FACT_KEYS:
            existing = document_facts.get(key) or {}
            incoming = value if isinstance(value, dict) else {"value": value}
            document_facts[key] = {**existing, **incoming}
            continue
        document_facts[key] = value


def extract_document_facts(current_state, latest_user_message: str, context) -> dict:
    client = genai.Client()
    prompt = f"""
Return ONLY valid JSON.

Extract procurement document facts from the current workflow context.

Only return fields that are explicitly supported by the conversation or current state.
Do not invent facts.
Do not overwrite unknown values with null.
If a value is not known, return null or omit it.

Allowed output keys:
{json.dumps(sorted(DOCUMENT_FACT_KEYS))}

Current workflow state:
{current_state}

Latest user message:
{latest_user_message}

Procurement request:
{context.request.model_dump_json(exclude_none=True) if context.request else "{}"}

Product recommendations:
{json.dumps(context.recommendations or [], ensure_ascii=False, default=str)}

Selected recommendation:
{json.dumps(context.selected_recommendation, ensure_ascii=False, default=str)}

Vendor recommendations:
{json.dumps(context.vendor_recommendations or [], ensure_ascii=False, default=str)}

Selected vendor:
{context.selected_vendor}

Existing document facts:
{json.dumps(ensure_document_facts(context), ensure_ascii=False, default=str)}
"""
    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=prompt,
    )
    return extract_json(response.text or "") or {}


def normalize_specifications(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [
            f"{key}: {val}"
            for key, val in value.items()
            if val not in (None, "", [], {})
        ]
    if isinstance(value, list):
        result = []
        for item in value:
            if item in (None, "", [], {}):
                continue
            if isinstance(item, dict):
                result.extend(normalize_specifications(item))
            else:
                result.append(str(item))
        return result
    return [str(value)]


def normalize_vendor_recommendations(value):
    vendors = value or []
    normalized = []
    for vendor in coerce_dict_list(value):
        if not isinstance(vendor, dict):
            continue
        name = vendor.get("vendor_name") or vendor.get("name")
        if not name:
            continue
        normalized.append({
            "vendor_name": name,
            "approval_status": str(vendor.get("approval_status") or "Unknown"),
            "policy_notes": vendor.get("policy_notes") or vendor.get("rationale") or [],
            "risk_level": vendor.get("risk_level"),
        })
    return normalized


def build_selected_option_from_facts(context):
    facts = ensure_document_facts(context)
    selected = coerce_dict(context.selected_recommendation) or {}
    title = (
        facts.get("selected_product_summary")
        or facts.get("product_model")
        or selected.get("title")
        or selected.get("model")
        or selected.get("product_title")
    )
    if not title:
        return None
    return {
        "option_id": str(
            selected.get("option_id")
            or selected.get("model")
            or facts.get("product_model")
            or "selected-product"
        ),
        "title": str(title),
        "source_urls": selected.get("source_urls") or selected.get("urls") or [],
        "pros": selected.get("pros") or [],
        "cons": selected.get("cons") or [],
        "fit_score": selected.get("fit_score"),
    }


@dataclass
class VendorIntent:
    wants_more_options: bool
    is_final_selection: bool
    confidence: float


def parse_money(value, currency="INR"):
    if isinstance(value, Money):
        return value
    if isinstance(value, dict):
        return Money(**value)
    text = str(value).lower().replace(",", "").strip()
    text = text.replace("inr", "").replace("₹", "").strip()
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith("l"):
        multiplier = 100000
        text = text[:-1]
    elif text.endswith("lac") or text.endswith("lakh"):
        multiplier = 100000
        text = text.replace("lac", "").replace("lakh", "")
    return Money(amount=float(text.strip()) * multiplier, currency=currency)


def coerce_total_budget(request):
    if isinstance(request.total_budget, Money):
        return request.total_budget
    if request.total_budget and str(request.total_budget).lower().strip() not in {
        "calculate",
        "calculate and find out",
        "find out",
    }:
        return parse_money(request.total_budget, request.currency)
    if request.quantity and request.budget_per_item:
        unit_budget = parse_money(request.budget_per_item, request.currency)
        return Money(
            amount=float(request.quantity) * unit_budget.amount,
            currency=unit_budget.currency,
        )
    return None


def build_procurement_document(context, final_summary: str | None = None):
    request = context.request
    facts = ensure_document_facts(context)
    return ProcurementDocument(
        unique_id=f"PROC-{uuid.uuid4().hex[:10].upper()}",
        created_at=datetime.now(timezone.utc).isoformat(),
        status="FINAL",
        item_name=request.item_name,
        category=facts.get("category") or request.category,
        business_purpose=facts.get("business_purpose") or request.business_purpose,
        mandatory_specifications=normalize_specifications(
            facts.get("product_specifications") or request.mandatory_specifications
        ),
        quantity=request.quantity,
        unit=request.unit,
        budget_per_item=(
            facts.get("normalized_budget_per_item") or request.budget_per_item
        ),
        total_budget=(
            facts.get("calculated_total_budget") or request.total_budget
        ),
        selected_option=build_selected_option_from_facts(context),
        vendor_recommendations=normalize_vendor_recommendations(
            context.vendor_recommendations or facts.get("shortlisted_vendors")
        ),
        selected_vendor=(
            facts.get("selected_vendor_summary") or context.selected_vendor
        ),
        delivery=request.delivery,
        compliance_information=context.policy_bundle or {},
        approval_requirements=facts.get("approval_requirements") or context.approval_requirements or {},
        procurement_method=facts.get("procurement_method") or context.metadata.get("procurement_method"),
        research_evidence=context.recommendations or [],
        final_confirmed_summary=(
            final_summary
            or facts.get("procurement_justification")
            or facts.get("vendor_comparison_summary")
            or facts.get("selected_product_summary")
        ),
    )


# ---------------------------------------------------------------------------
# Zone B: LLM extraction helpers
# These use Gemini to extract structured data from user input only.
# They do NOT return next_state. State transitions remain in Python.
# ---------------------------------------------------------------------------

def _extract_item_name(user_input: str) -> dict:
    """
    Zone B: Ask Gemini to extract the item name and validate it is a real
    procurement item. Returns {"item_name": str, "valid": bool, "response": str}.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement intake assistant.

The user has been asked: "What item would you like to procure?"

User Response:
{user_input}

Rules:
- valid = true ONLY if a clear, specific product or service is identified.
- Examples that are valid: "Laptop", "Dell Latitude 5450", "Office Chair", "100 safety helmets"
- Examples that are NOT valid: "Hello", "Continue", "Yes", "I need something", "Not sure yet"
- If valid, extract item_name and set response to ask how many units are needed.
- If not valid, explain what is missing and ask the user to specify the item.

Return ONLY valid JSON:
{{
  "valid": true or false,
  "item_name": "extracted item name or empty string",
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"valid": False, "item_name": "", "response": "Could you specify the item you need to procure?"}


def _extract_quantity(user_input: str, item_name: str) -> dict:
    """
    Zone B: Extract a numeric quantity from user input.
    Returns {"quantity": str, "valid": bool, "response": str}.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement intake assistant.

Item being procured: {item_name}
The user has been asked: "How many units do you need?"

User Response:
{user_input}

Rules:
- valid = true if a quantity can be reasonably inferred (exact number, or convertible word like "twenty").
- Examples that are valid: "65", "Twenty", "About 100", "a dozen"
- Examples that are NOT valid: "Many", "Some", "Whatever is needed", "Lots"
- If valid, extract quantity as a number string and ask for the budget per unit.
- If not valid, ask for a specific number.

Return ONLY valid JSON:
{{
  "valid": true or false,
  "quantity": "numeric string or empty string",
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"valid": False, "quantity": "", "response": "Could you provide a specific quantity?"}


def _extract_budget_per_item(user_input: str, item_name: str, quantity: str) -> dict:
    """
    Zone B: Extract per-unit budget from user input.
    Returns {"budget_per_item": str, "valid": bool, "response": str}.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement intake assistant.

Item: {item_name}
Quantity: {quantity}
The user has been asked: "What is your budget per unit?"

User Response:
{user_input}

Rules:
- valid = true if a monetary value can be identified. Accept INR, ₹, "k", "lac", "lakh" shorthand.
- Examples that are valid: "50000", "₹50k", "1.5 lac", "INR 75,000"
- Examples that are NOT valid: "Not sure", "Depends", "Whatever it costs"
- If valid, extract budget_per_item and ask for the total budget.
- If not valid, ask for a specific budget per unit.

Return ONLY valid JSON:
{{
  "valid": true or false,
  "budget_per_item": "amount string or empty string",
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"valid": False, "budget_per_item": "", "response": "Could you provide a budget per unit?"}


def _extract_total_budget(user_input: str, item_name: str, quantity: str, budget_per_item: str) -> dict:
    """
    Zone B: Extract total budget or auto-calculate instruction.
    Returns {"total_budget": str, "valid": bool, "response": str}.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement intake assistant.

Item: {item_name}
Quantity: {quantity}
Budget per item: {budget_per_item}
The user has been asked: "What is your total procurement budget?"

User Response:
{user_input}

Rules:
- valid = true if an explicit total budget is stated, OR the user says to calculate it.
- Examples that are valid: "5 lakh total", "calculate it", "derive from the above"
- Examples that are NOT valid: "Not decided", "Open budget"
- If the user says calculate/derive, set total_budget to "calculate".
- If not valid, ask for a total budget or confirm auto-calculation.

Return ONLY valid JSON:
{{
  "valid": true or false,
  "total_budget": "amount string, or 'calculate', or empty string",
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"valid": False, "total_budget": "", "response": "Could you provide a total budget or ask me to calculate it?"}


def _extract_budget_confirmation(user_input: str, item_name: str, quantity: str, budget_per_item: str, total_budget: str) -> dict:
    """
    Zone B: Classify whether user confirmed the budget summary or wants changes.
    Returns {"confirmed": bool, "budget_per_item": str, "total_budget": str, "response": str}.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement intake assistant.

The user has been shown a budget summary and asked to confirm:
- Item: {item_name}
- Quantity: {quantity}
- Budget per item: {budget_per_item}
- Total budget: {total_budget}

User Response:
{user_input}

Rules:
- confirmed = true if the user confirms (yes, correct, looks good, proceed, etc.).
- confirmed = false if the user wants to change figures.
- If confirmed = false, extract any updated values from their message.

Return ONLY valid JSON:
{{
  "confirmed": true or false,
  "budget_per_item": "updated amount or empty string",
  "total_budget": "updated amount or empty string",
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"confirmed": False, "budget_per_item": "", "total_budget": "", "response": "Could you confirm the budget details or specify what needs to change?"}


def _extract_specs(user_input: str, item_name: str, quantity: str) -> dict:
    """
    Zone B: Extract specifications, preferences, and constraints from user input.
    Returns {"valid": bool, "optional_preferences": list, "mandatory_specifications": list, "constraints": list, "response": str}.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement intake assistant.

Item: {item_name}
Quantity: {quantity}
The user has been asked for technical requirements, preferences, brands, and constraints.

User Response:
{user_input}

Rules:
- Extract any available: brands, specs, constraints, performance requirements.
- valid = true if any meaningful specification or preference is provided.
- Do not demand exhaustive details — even a brand preference is sufficient.
- If nothing useful is captured, ask for at least one specification or preference.

Return ONLY valid JSON:
{{
  "valid": true or false,
  "optional_preferences": ["list of preference strings"],
  "mandatory_specifications": ["list of spec strings"],
  "constraints": ["list of constraint strings"],
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"valid": False, "optional_preferences": [], "mandatory_specifications": [], "constraints": [], "response": "Could you share at least one specification or preference?"}


def _extract_delivery_timeline(user_input: str) -> dict:
    """
    Zone B: Extract delivery timeline from user input.
    Returns {"valid": bool, "delivery_timeline": str, "response": str}.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement assistant.

The user has been asked: "When do you need this delivered?"

User Response:
{user_input}

Rules:
- valid = true if a time reference can be understood: "10 days", "2 weeks", "before Diwali",
  "end of month", "ASAP", "within Q3".
- NOT valid: "don't know", "no preference", blank or meaningless input.
- If valid, extract delivery_timeline.
- If not valid, give examples and ask again.

Return ONLY valid JSON:
{{
  "valid": true or false,
  "delivery_timeline": "string or empty string",
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"valid": False, "delivery_timeline": "", "response": "Could you provide a delivery deadline? For example: '2 weeks', 'end of month', 'ASAP'."}


def _extract_address_field(user_input: str, field: str, current_state_name: str) -> dict:
    """
    Zone B: Extract a single address field from user input.
    Returns {"valid": bool, "value": str, "response": str}.
    """
    field_labels = {
        "address_line": "street address or building name",
        "city": "city",
        "state": "state or province",
        "country": "country",
        "postal_code": "postal code or PIN code",
    }
    label = field_labels.get(field, field)
    client = genai.Client()
    prompt = f"""
You are a procurement assistant collecting a delivery address.

The user has been asked to provide their {label}.

User Response:
{user_input}

Rules:
- valid = true if the user has provided a recognisable {label}.
- If valid, extract the value.
- If not valid, ask the user again for just the {label}.

Return ONLY valid JSON:
{{
  "valid": true or false,
  "value": "extracted {field} or empty string",
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"valid": False, "value": "", "response": f"Could you provide your {label}?"}


def _classify_selection_confirmation(user_input: str, selected_recommendation_json: str) -> dict:
    """
    Zone B: Classify user intent at SELECTION_CONFIRMATION.
    Returns {"decision": str, "response": str}.
    decision in {"confirmed", "change", "research"}
    """
    client = genai.Client()
    prompt = f"""
You are a procurement assistant.

The user has been shown a selected product and asked to confirm.

Selected Product:
{selected_recommendation_json}

User Response:
{user_input}

Classify the user's intent as ONE of:
- "confirmed" — user accepts the selected product
- "change"    — user wants a different product from the current recommendations
- "research"  — user wants to go back to fresh market research

Return ONLY valid JSON:
{{
  "decision": "confirmed" or "change" or "research",
  "response": "Your message to the user"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    return extract_json(r.text or "") or {"decision": "confirmed", "response": "Got it."}


# ---------------------------------------------------------------------------
# Zone A: Vendor intent classification — preserved original functions
# ---------------------------------------------------------------------------

def extract_vendor_intent(user_input: str, vendor_history: list) -> VendorIntent:
    """
    Preserved: Classifies user intent in VENDOR_REVIEW state.
    Returns VendorIntent with wants_more_options and is_final_selection flags.
    State transitions in VENDOR_REVIEW are driven by the result of this function,
    not by Gemini next_state fields.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement assistant analysing a user's response about vendor options.

Previously shown vendors:
{json.dumps(vendor_history or [], ensure_ascii=False)}

User Response:
{user_input}

Classify the user's intent:
- wants_more_options: true if the user is asking for additional vendors not yet shown
- is_final_selection: true if the user is committing to a specific vendor or requesting a quote

Return ONLY valid JSON:
{{
  "wants_more_options": true or false,
  "is_final_selection": true or false,
  "confidence": 0.0 to 1.0
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    raw = extract_json(r.text or "") or {}
    return VendorIntent(
        wants_more_options=bool(raw.get("wants_more_options", False)),
        is_final_selection=bool(raw.get("is_final_selection", False)),
        confidence=float(raw.get("confidence", 0.5)),
    )


def resolve_selected_vendor(user_input: str, vendor_history: list) -> str | None:
    """
    Preserved: Extracts the vendor name the user has selected from their input.
    Returns a string vendor name, or None if no clear selection was made.
    """
    client = genai.Client()
    prompt = f"""
You are a procurement assistant.

The user has selected a vendor. Extract the vendor name from their response.

Previously shown vendors:
{json.dumps(vendor_history or [], ensure_ascii=False)}

User Response:
{user_input}

Return ONLY valid JSON:
{{
  "selected_vendor": "vendor name or empty string"
}}
"""
    r = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
    raw = extract_json(r.text or "") or {}
    name = raw.get("selected_vendor") or ""
    return name.strip() or None


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

async def handle_state_input(text, context, runner):
    """
    Hybrid workflow engine entry point.

    Zone A states: Python controls all state transitions via context.state = WorkflowState.X
    Zone B states: LLM generates content, extracts data, reasons conversationally.
                   LLM never controls state transitions for Zone A states.

    Preserved: all runner event processing, document fact extraction,
               recommendation/vendor parsing, HIL flow, fallback summarisation.
    """
    global _ACTIVE_PROCUREMENT_CONTEXT
    _ACTIVE_PROCUREMENT_CONTEXT = context
    if context.request is None:
        context.request = ProcurementRequest()

    user_input = text
    current_state = context.state
    context.previous_state = current_state

    req = context.request
    request_json = req.model_dump_json(exclude_none=True) if req else "{}"

    content = None  # types.Content to send to the runner

    # ==========================================================================
    # ZONE A — STATIC DETERMINISTIC TRANSITIONS
    # Each block:
    #   1. Calls a Zone B LLM helper to extract data / validate input
    #   2. Applies extracted data to context
    #   3. Advances context.state in Python (never via next_state from Gemini)
    #   4. Builds the runner content for the next interaction
    # ==========================================================================

    # --------------------------------------------------------------------------
    # INTENT_ITEM
    # --------------------------------------------------------------------------
    if current_state == WorkflowState.INTENT_ITEM:
        result = _extract_item_name(user_input)
        if not result.get("valid"):
            print(result.get("response", "Please specify the item you want to procure."))
            return
        context.request.item_name = result["item_name"]
        context.state = WorkflowState.QUANTITY          # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=NEXT_QUESTION_PROMPT.format(
                    text=user_input,
                    current_state=context.state,
                    item_name=req.item_name,
                    quantity=req.quantity,
                    budget_per_item=req.budget_per_item,
                    total_budget=req.total_budget,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # QUANTITY
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.QUANTITY:
        result = _extract_quantity(user_input, req.item_name or "")
        if not result.get("valid"):
            print(result.get("response", "Please provide a specific quantity."))
            return
        context.request.quantity = result["quantity"]
        context.state = WorkflowState.BUDGET_PER_ITEM  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=NEXT_QUESTION_PROMPT.format(
                    text=user_input,
                    current_state=context.state,
                    item_name=req.item_name,
                    quantity=req.quantity,
                    budget_per_item=req.budget_per_item,
                    total_budget=req.total_budget,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # BUDGET_PER_ITEM
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.BUDGET_PER_ITEM:
        result = _extract_budget_per_item(
            user_input, req.item_name or "", str(req.quantity or "")
        )
        if not result.get("valid"):
            print(result.get("response", "Please provide a budget per unit."))
            return
        context.request.budget_per_item = result["budget_per_item"]
        context.state = WorkflowState.BUDGET_TOTAL     # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=NEXT_QUESTION_PROMPT.format(
                    text=user_input,
                    current_state=context.state,
                    item_name=req.item_name,
                    quantity=req.quantity,
                    budget_per_item=req.budget_per_item,
                    total_budget=req.total_budget,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # BUDGET_TOTAL
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.BUDGET_TOTAL:
        result = _extract_total_budget(
            user_input,
            req.item_name or "",
            str(req.quantity or ""),
            str(req.budget_per_item or ""),
        )
        if not result.get("valid"):
            print(result.get("response", "Please provide a total budget or ask me to calculate it."))
            return
        context.request.total_budget = result["total_budget"]
        context.state = WorkflowState.BUDGET_CONFIRMATION  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=NEXT_QUESTION_PROMPT.format(
                    text=user_input,
                    current_state=context.state,
                    item_name=req.item_name,
                    quantity=req.quantity,
                    budget_per_item=req.budget_per_item,
                    total_budget=req.total_budget,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # BUDGET_CONFIRMATION
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.BUDGET_CONFIRMATION:
        result = _extract_budget_confirmation(
            user_input,
            req.item_name or "",
            str(req.quantity or ""),
            str(req.budget_per_item or ""),
            str(req.total_budget or ""),
        )
        if result.get("budget_per_item"):
            context.request.budget_per_item = result["budget_per_item"]
        if result.get("total_budget"):
            context.request.total_budget = result["total_budget"]
        if not result.get("confirmed"):
            print(result.get("response", "Please confirm the budget details or let me know what needs to change."))
            return
        context.state = WorkflowState.INTENT_SPECS     # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=NEXT_QUESTION_PROMPT.format(
                    text=user_input,
                    current_state=context.state,
                    item_name=req.item_name,
                    quantity=req.quantity,
                    budget_per_item=req.budget_per_item,
                    total_budget=req.total_budget,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # INTENT_SPECS
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.INTENT_SPECS:
        result = _extract_specs(user_input, req.item_name or "", str(req.quantity or ""))
        if not result.get("valid"):
            print(result.get("response", "Please share at least one specification or preference."))
            return
        prefs = result.get("optional_preferences") or []
        if isinstance(prefs, list):
            context.request.optional_preferences.extend(prefs)
        specs = result.get("mandatory_specifications") or []
        if isinstance(specs, list):
            context.request.mandatory_specifications = (
                context.request.mandatory_specifications or []
            ) + specs
        constraints = result.get("constraints") or []
        if isinstance(constraints, list):
            context.request.constraints.extend(constraints)
        context.state = WorkflowState.MARKET_RESEARCH  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=MARKET_RESEARCH_PROMPT.format(
                    procurement_request=req.model_dump_json(exclude_none=True)
                )
            )],
        )

    # --------------------------------------------------------------------------
    # MARKET_RESEARCH  (agent state — always advances to RECOMMENDATION_REVIEW)
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.MARKET_RESEARCH:
        context.state = WorkflowState.RECOMMENDATION_REVIEW  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=f"{MARKET_RESEARCH_PROMPT.format(procurement_request=request_json)}\n\nUser follow-up: {user_input}"
            )],
        )

    # --------------------------------------------------------------------------
    # RECOMMENDATION_REVIEW  (LLM decides which branch; Python applies transition)
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.RECOMMENDATION_REVIEW:
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=RECOMMENDATION_REVIEW_PROMPT.format(
                    user_response=user_input,
                    procurement_request=request_json,
                    recommendations=json.dumps(
                        context.recommendations or [], ensure_ascii=False, default=str
                    ),
                )
            )],
        )
        # State transition happens inside the event loop below when the LLM
        # returns a decision (selection / refinement / budget_change).

    # --------------------------------------------------------------------------
    # RECOMMENDATION_REFINEMENT  (always loops back to MARKET_RESEARCH)
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.RECOMMENDATION_REFINEMENT:
        context.state = WorkflowState.MARKET_RESEARCH  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=MARKET_RESEARCH_PROMPT.format(
                    procurement_request=req.model_dump_json(exclude_none=True)
                )
            )],
        )

    # --------------------------------------------------------------------------
    # SELECTION_CONFIRMATION
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.SELECTION_CONFIRMATION:
        if context.selected_recommendation is None:
            context.state = WorkflowState.RECOMMENDATION_REVIEW  # Python transition
            content = types.Content(
                role="user",
                parts=[types.Part(
                    text=RECOMMENDATION_REVIEW_PROMPT.format(
                        user_response=user_input,
                        procurement_request=request_json,
                        recommendations=json.dumps(
                            context.recommendations or [], ensure_ascii=False, default=str
                        ),
                    )
                )],
            )
        else:
            result = _classify_selection_confirmation(
                user_input,
                json.dumps(context.selected_recommendation, ensure_ascii=False, default=str),
            )
            decision = result.get("decision", "confirmed")
            response_text = result.get("response", "")
            if decision == "confirmed":
                context.state = WorkflowState.DELIVERY_TIMELINE  # Python transition
                content = types.Content(
                    role="user",
                    parts=[types.Part(
                        text=DELIVERY_TIMELINE_PROMPT.format()
                    )],
                )
            elif decision == "change":
                context.state = WorkflowState.RECOMMENDATION_REVIEW  # Python transition
                content = types.Content(
                    role="user",
                    parts=[types.Part(
                        text=RECOMMENDATION_REVIEW_PROMPT.format(
                            user_response=user_input,
                            procurement_request=request_json,
                            recommendations=json.dumps(
                                context.recommendations or [], ensure_ascii=False, default=str
                            ),
                        )
                    )],
                )
            else:  # "research"
                context.state = WorkflowState.MARKET_RESEARCH  # Python transition
                context.recommendations = None
                context.selected_recommendation = None
                content = types.Content(
                    role="user",
                    parts=[types.Part(
                        text=MARKET_RESEARCH_PROMPT.format(procurement_request=request_json)
                    )],
                )
            if response_text:
                print(response_text)

    # --------------------------------------------------------------------------
    # DELIVERY_TIMELINE
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.DELIVERY_TIMELINE:
        result = _extract_delivery_timeline(user_input)
        if not result.get("valid"):
            print(result.get("response", "Please provide a delivery deadline."))
            return
        context.request.constraints.append(result["delivery_timeline"])
        context.state = WorkflowState.DELIVERY_ADDRESS  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=DELIVERY_LOCATION_PROMPT.format(
                    current_state=context.state,
                    address_line=req.delivery.address_line,
                    city=req.delivery.city,
                    state=req.delivery.state,
                    country=req.delivery.country,
                    postal_code=req.delivery.postal_code,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # DELIVERY_ADDRESS
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.DELIVERY_ADDRESS:
        result = _extract_address_field(user_input, "address_line", "DELIVERY_ADDRESS")
        if not result.get("valid"):
            print(result.get("response", "Please provide your street address."))
            return
        context.request.delivery.address_line = result["value"]
        context.state = WorkflowState.DELIVERY_CITY    # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=DELIVERY_LOCATION_PROMPT.format(
                    current_state=context.state,
                    address_line=req.delivery.address_line,
                    city=req.delivery.city,
                    state=req.delivery.state,
                    country=req.delivery.country,
                    postal_code=req.delivery.postal_code,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # DELIVERY_CITY
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.DELIVERY_CITY:
        result = _extract_address_field(user_input, "city", "DELIVERY_CITY")
        if not result.get("valid"):
            print(result.get("response", "Please provide your city."))
            return
        context.request.delivery.city = result["value"]
        context.state = WorkflowState.DELIVERY_STATE   # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=DELIVERY_LOCATION_PROMPT.format(
                    current_state=context.state,
                    address_line=req.delivery.address_line,
                    city=req.delivery.city,
                    state=req.delivery.state,
                    country=req.delivery.country,
                    postal_code=req.delivery.postal_code,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # DELIVERY_STATE
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.DELIVERY_STATE:
        result = _extract_address_field(user_input, "state", "DELIVERY_STATE")
        if not result.get("valid"):
            print(result.get("response", "Please provide your state or province."))
            return
        context.request.delivery.state = result["value"]
        context.state = WorkflowState.DELIVERY_COUNTRY  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=DELIVERY_LOCATION_PROMPT.format(
                    current_state=context.state,
                    address_line=req.delivery.address_line,
                    city=req.delivery.city,
                    state=req.delivery.state,
                    country=req.delivery.country,
                    postal_code=req.delivery.postal_code,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # DELIVERY_COUNTRY
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.DELIVERY_COUNTRY:
        result = _extract_address_field(user_input, "country", "DELIVERY_COUNTRY")
        if not result.get("valid"):
            print(result.get("response", "Please provide your country."))
            return
        context.request.delivery.country = result["value"]
        context.state = WorkflowState.DELIVERY_POSTAL_CODE  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=DELIVERY_LOCATION_PROMPT.format(
                    current_state=context.state,
                    address_line=req.delivery.address_line,
                    city=req.delivery.city,
                    state=req.delivery.state,
                    country=req.delivery.country,
                    postal_code=req.delivery.postal_code,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # DELIVERY_POSTAL_CODE
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.DELIVERY_POSTAL_CODE:
        result = _extract_address_field(user_input, "postal_code", "DELIVERY_POSTAL_CODE")
        if not result.get("valid"):
            print(result.get("response", "Please provide your postal or PIN code."))
            return
        context.request.delivery.postal_code = result["value"]
        context.state = WorkflowState.VENDOR_REVIEW  # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=VENDOR_SELECTION_PROMPT.format(
                    procurement_request=req.model_dump_json(exclude_none=True),
                    selected_recommendation=json.dumps(
                        context.selected_recommendation, ensure_ascii=False, default=str
                    ),
                    user_response=user_input,
                    vendor_history=json.dumps(
                        context.vendor_history or [], ensure_ascii=False, default=str
                    ),
                    force_fresh_vendor_discovery=True,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # VENDOR_POLICY_EVALUATION  (agent state — always advances to VENDOR_REVIEW)
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.VENDOR_POLICY_EVALUATION:
        context.state = WorkflowState.VENDOR_REVIEW    # Python transition
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=VENDOR_SELECTION_PROMPT.format(
                    procurement_request=request_json,
                    selected_recommendation=json.dumps(
                        context.selected_recommendation, ensure_ascii=False, default=str
                    ),
                    user_response=user_input,
                    vendor_history=json.dumps(
                        context.vendor_history or [], ensure_ascii=False, default=str
                    ),
                    force_fresh_vendor_discovery=True,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # VENDOR_REVIEW  (uses extract_vendor_intent + resolve_selected_vendor)
    # --------------------------------------------------------------------------
    # VENDOR_REVIEW — terminal Python state; root/vendor/negotiator own the flow
    elif current_state == WorkflowState.VENDOR_REVIEW:
        if not context.metadata.get("vendor_agent_engaged"):
            context.metadata["vendor_agent_engaged"] = True
            text = (
                "Procurement intake and delivery are complete. "
                "Transfer to vendor_selection_agent.\n\n"
                f"User: {user_input}"
            )
        else:
            text = user_input
        content = types.Content(
            role="user",
            parts=[types.Part(text=user_input)],
        )

    # --------------------------------------------------------------------------
    # VENDOR_EXPANSION  (agent state — always returns to VENDOR_REVIEW)
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.VENDOR_EXPANSION:
        context.state = WorkflowState.VENDOR_REVIEW    # Python transition
        context.metadata["force_fresh_vendor_discovery"] = False
        content = types.Content(
            role="user",
            parts=[types.Part(
                text=VENDOR_SELECTION_PROMPT.format(
                    procurement_request=request_json,
                    selected_recommendation=json.dumps(
                        context.selected_recommendation, ensure_ascii=False, default=str
                    ),
                    user_response=user_input,
                    vendor_history=json.dumps(
                        context.vendor_history or [], ensure_ascii=False, default=str
                    ),
                    force_fresh_vendor_discovery=True,
                )
            )],
        )

    # --------------------------------------------------------------------------
    # QUOTE_REQUEST  (always advances to FINAL_DOCUMENT_DRAFT)
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.QUOTE_REQUEST:
        context.state = WorkflowState.FINAL_DOCUMENT_DRAFT  # Python transition
        handle_final_document_draft(context)
        return

    # --------------------------------------------------------------------------
    # FINAL_DOCUMENT_DRAFT  (handled by handle_final_document_draft)
    # --------------------------------------------------------------------------
    elif current_state == WorkflowState.FINAL_DOCUMENT_DRAFT:
        handle_final_document_draft(context)
        return

    # --------------------------------------------------------------------------
    # FINAL_CONFIRMATION / COMPLETE  (handled by handle_complete)
    # --------------------------------------------------------------------------
    elif current_state in {WorkflowState.FINAL_CONFIRMATION, WorkflowState.COMPLETE}:
        handle_complete(text, context)
        if context.state == WorkflowState.NEGOTIATION_COMPLETE:
            await handle_negotiation_complete(text, context, runner)
            return

        return
        
        

    else:
        print("Workflow is in an unrecognised state. Please restart.")
        return

    if content is None:
        print("Workflow is in an unrecognised state. Please restart.")
        return

    # ==========================================================================
    # Run the ADK agent and process events (unchanged from original)
    # ==========================================================================
    # Re-read live state after any transitions above.
    effective_state = context.state

    events = runner.run_async(
        user_id=get_user_id(),
        session_id=get_session_id(),
        new_message=content,
    )

    internal_outputs = []
    latest_plain_text = None

    async for event in events:
        if not event.content:
            continue
        for part in event.content.parts:
            part_text = getattr(part, "text", None)
            if not part_text:
                continue
            raw = extract_json(part_text)

            if raw is not None:
                internal_outputs.append(part_text)

                if effective_state == WorkflowState.RECOMMENDATION_REVIEW and isinstance(raw, dict):
                    decision = raw.get("decision")

                    if decision == "budget_change":
                        updated_budget_per_item = raw.get("updated_budget_per_item")
                        updated_total_budget = raw.get("updated_total_budget")
                        refinement_notes = raw.get("refinement_notes") or raw.get("reason")
                        if updated_budget_per_item:
                            context.request.budget_per_item = parse_money(updated_budget_per_item)
                        if updated_total_budget:
                            context.request.total_budget = parse_money(updated_total_budget)
                        context.request.optional_preferences.append(refinement_notes)
                        context.selection_history.append(refinement_notes)
                        context.recommendations = None
                        context.selected_recommendation = None
                        context.state = WorkflowState.RECOMMENDATION_REFINEMENT  # Python transition
                        continue

                    if decision == "refinement":
                        refinement_notes = raw.get("refinement_notes") or raw.get("reason")
                        if refinement_notes:
                            context.request.optional_preferences.append(refinement_notes)
                            context.selection_history.append(refinement_notes)
                        context.selected_recommendation = None
                        context.state = WorkflowState.RECOMMENDATION_REFINEMENT  # Python transition
                        continue

                    if decision == "selection":
                        selected = raw.get("selected_recommendation")
                        if selected is None:
                            refinement_notes = raw.get("reason") or raw.get("refinement_notes")
                            if refinement_notes:
                                context.request.optional_preferences.append(refinement_notes)
                                context.selection_history.append(refinement_notes)
                            context.selected_recommendation = None
                            context.state = WorkflowState.RECOMMENDATION_REFINEMENT  # Python transition
                            continue
                        context.selected_recommendation = selected
                        context.selection_history.append(part_text)
                        context.state = WorkflowState.SELECTION_CONFIRMATION  # Python transition
                        continue

                if effective_state in {
                    WorkflowState.INTENT_SPECS,
                    WorkflowState.MARKET_RESEARCH,
                    WorkflowState.RECOMMENDATION_REFINEMENT,
                }:
                    if isinstance(raw, dict) and "recommendations" in raw:
                        context.recommendations = raw["recommendations"]
                        continue
                    if isinstance(raw, dict) and "products" in raw:
                        context.recommendations = raw["products"]
                        continue

                if effective_state in {
                    WorkflowState.VENDOR_POLICY_EVALUATION,
                    WorkflowState.VENDOR_EXPANSION,
                    WorkflowState.QUOTE_REQUEST,
                    WorkflowState.VENDOR_REVIEW,
                }:
                    vendor_items = (
                        raw if isinstance(raw, list)
                        else raw.get("recommended_vendors", [])
                    )
                    for vendor in vendor_items or []:
                        if not isinstance(vendor, dict):
                            continue
                        name = vendor.get("vendor_name") or vendor.get("name")
                        if name and name not in context.vendor_history:
                            context.vendor_history.append(name)
                    context.vendor_recommendations = (
                        vendor_items or context.vendor_recommendations
                    )
                    continue

                try:
                    if not isinstance(raw, dict):
                        continue
                    request_update = ProcurementRequest(**raw)
                    update_data = request_update.model_dump(exclude_unset=True, exclude_none=True)
                    context.request = context.request.model_copy(update=update_data)
                except Exception as exc:
                    context.errors.append(str(exc))
                continue

            latest_plain_text = part_text

    # Extract and merge document facts (unchanged)
    extracted_facts = extract_document_facts(
        current_state=current_state,
        latest_user_message=user_input,
        context=context,
    )
    merge_document_facts(context, extracted_facts)

    if latest_plain_text:
        print(latest_plain_text)
        return

    # Fallback summarisation (unchanged)
    if internal_outputs:
        summary_content = types.Content(
            role="user",
            parts=[types.Part(text=f"""
Convert this internal procurement output into a short plain-English response for the user.
Do not show JSON.
Do not mention internal agents or tools.
Ask only one question if information is missing.
Internal output:
{internal_outputs[-1]}
""")],
        )
        summary_events = runner.run_async(
            user_id=get_user_id(),
            session_id=get_session_id(),
            new_message=summary_content,
        )
        latest_summary_text = None
        async for event in summary_events:
            if not event.content:
                continue
            for part in event.content.parts:
                reply = getattr(part, "text", None)
                if not reply:
                    continue
                if extract_json(reply) is not None:
                    continue
                latest_summary_text = reply
        if latest_summary_text:
            print(latest_summary_text)


# ---------------------------------------------------------------------------
# Business-logic handlers (unchanged)
# ---------------------------------------------------------------------------

def handle_feasibility_assessment(context):
    req = context.request
    context.document = None
    context.state = WorkflowState.FEASIBILITY_REVIEW
    print("Document created:", context.document.unique_id)


def handle_vendor_policy_evaluation(context):
    request = context.request
    selected = context.selected_recommendation
    vendors = get_vendor_rules(request.category)
    context.vendor_recommendations = vendors
    print("Vendor policy evaluation complete:", vendors)
    context.state = WorkflowState.VENDOR_REVIEW


def handle_final_document_draft(context):
    extracted_facts = extract_document_facts(
        current_state=WorkflowState.FINAL_DOCUMENT_DRAFT,
        latest_user_message="",
        context=context,
    )
    merge_document_facts(context, extracted_facts)

    context.document = build_procurement_document(
        context,
        final_summary=f"Vendor locked: {context.selected_vendor}",
    )
    result = write_procurement_pdf(context.document.model_dump(mode="json"))

    context.document_path = result["document_path"]
    context.document_download_url = result.get("download_url")

    context.metadata["document_result"] = {
        "status": result["status"],
        "document_path": result["document_path"],
        "document_id": result["document_id"],
        "download_url": context.document_download_url,
    }
    context.metadata["hil_review_payload"] = {
        "document_id": result["document_id"],
        "document_path": result["document_path"],
        "download_url": context.document_download_url,
        "document": context.document.model_dump(mode="json"),
    }
    context.metadata.setdefault("hil", {})
    context.metadata["hil"].update({
        "status": "pending",
        "review_started_at": datetime.now(timezone.utc).isoformat(),
        "review_decision": None,
        "reviewer_input": None,
        "approved": False,
        "rejection_reason": None,
    })

    context.state = WorkflowState.COMPLETE   # Python transition
    print("Procurement document generated:", context.document_path)
    print("Document path:", context.document_path)
    print("Download URL:", context.document_download_url)
    print("Please review the generated procurement document.")
    print("Document ID:", result["document_id"])
    print("Document path:", context.document_path)
    print("Reply APPROVE to finalize, or REJECT: <reason> to return to recommendation review.")


def handle_complete(text, context):
    if not context.document_path:
        context.state = WorkflowState.FINAL_DOCUMENT_DRAFT
        print("Procurement document is not generated yet.")
        return

    hil = context.metadata.setdefault("hil", {})
    review_payload = context.metadata.get("hil_review_payload") or {}
    decision = (text or "").strip().lower()

    if hil.get("status") not in {"pending", "approved"}:
        hil.update({
            "status": "pending",
            "review_started_at": datetime.now(timezone.utc).isoformat(),
            "approved": False,
        })

    print("Generated procurement document is ready for human review.")
    print("Document ID:", review_payload.get("document_id"))
    print("Document path:", review_payload.get("document_path") or context.document_path)
    print("Download URL:", review_payload.get("download_url") or context.document_download_url)
    print("Reply with 'approve' to finalize, or 'reject: <reason>' to send it back to recommendation review.")

    if decision in {"approve", "approved"}:
        hil.update({
            "status": "approved",
            "review_completed_at": datetime.now(timezone.utc).isoformat(),
            "review_decision": "approved",
            "reviewer_input": text,
            "approved": True,
        })
        context.metadata["procurement_approved"] = True
        context.state = WorkflowState.NEGOTIATION_COMPLETE
        print("Procurement approved and finalized.")
        print("Final document path:", context.document_path)
        print("Download URL:", context.document_download_url)
        return

    if decision.startswith("reject"):
        reason = text.split(":", 1)[1].strip() if ":" in text else text
        hil.update({
            "status": "rejected",
            "review_completed_at": datetime.now(timezone.utc).isoformat(),
            "review_decision": "rejected",
            "reviewer_input": text,
            "approved": False,
            "rejection_reason": reason,
        })
        context.metadata["procurement_approved"] = False
        context.metadata["document_rejection_reason"] = reason
        context.state = WorkflowState.RECOMMENDATION_REVIEW  # Python transition
        print("Procurement document rejected.")
        print("Returning to recommendation review.")
        return

    print("Human approval is still pending.")

async def handle_negotiation_complete(text, context, runner):
    hil = (context.metadata or {}).get("hil") or {}

    if (
        not context.document_path
        or context.metadata.get("procurement_approved") is not True
        or hil.get("approved") is not True
    ):
        print("Procurement document must be generated and approved before negotiation.")
        return

    print("Starting negotiation workflow...")
