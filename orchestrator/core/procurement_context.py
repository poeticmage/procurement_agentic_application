from .workflow_state import WorkflowState

class ProcurementContext:
    """
    Runtime procurement workflow context.

    Holds session identity, workflow state, draft request,
    feasibility results, market research artifacts, vendor evaluation,
    final document, and conversation control metadata.
    """

    def __init__(self):
        self.state = WorkflowState.INTENT_ITEM
        self.previous_state = None
        self.last_question = None
        self.awaiting_confirmation = False

        self.user_id = None
        self.session_id = None
        self.app_name = None

        self.request = None
        self.feasibility = None
        self.search_queries = None
        self.search_results = None
        self.extracted_products = None
        self.recommendations = None
        self.selected_recommendation = None
        self.selection_history = []

        self.vendor_recommendations = None
        self.vendor_history = []
        self.selected_vendor=None
        self.policy_bundle = None
        self.approval_requirements = None

        self.document = None
        self.document_path=None
        self.errors = []
        self.retry_count_by_state = {}
        self.metadata = {
            "document_facts": {
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
            },
            "hil": {
                "status": "not_started",
                "review_started_at": None,
                "review_completed_at": None,
                "review_decision": None,
                "reviewer_input": None,
                "approved": False,
                "rejection_reason": None,
            },
            "negotiation": {},
        }
        self.document_s3_key = None
        self.document_download_url = None
        