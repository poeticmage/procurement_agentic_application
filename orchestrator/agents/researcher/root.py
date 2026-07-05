from google.adk.agents import Agent
from google.genai import Client
from google.genai import types
from ...prompts.root_agent_instructions import  ROOT_AGENT_STATIC_INSTRUCTION
from ...tools.writer_tools import vendor_rules_tool, procurement_method_tool, approval_policy_tool, complete_policy_bundle_tool
from ...tools.search_tool import search_agent_tool
from ...tools.remote_a2a_planner_tool import planner_agent_a2a_tool
from ...tools.search_queries_agent_tool import search_queries_agent_tool
from .scrapper_agent import scraper_agent
from .vendor_agent import vendor_agent
from .negotiator_agent import negotiator_agent
from google.adk.apps.app import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import Gemini
from .suggested_search_query_agent import search_queries_agent
from google.adk.plugins import BasePlugin
from google.adk.agents.context_cache_config import ContextCacheConfig

from google.adk.plugins import DebugLoggingPlugin


root_agent = Agent(
    name="procurement_root_agent",
    model="gemini-flash-lite-latest",
    description="Main conversational procurement agent.",
    static_instruction=ROOT_AGENT_STATIC_INSTRUCTION,
    
    sub_agents=[
         vendor_agent
    ],
    tools=[planner_agent_a2a_tool,
    search_agent_tool,
    search_queries_agent_tool, 
    vendor_rules_tool, 
    procurement_method_tool, 
    approval_policy_tool, 
    complete_policy_bundle_tool,
    ]
)

summarization_llm = Gemini(model="gemini-flash-latest")

my_summarizer = LlmEventSummarizer(llm=summarization_llm)

class ToolUsagePlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="tool_usage")
    async def before_tool_callback(
        self,
        *,
        tool,
        tool_args,
        tool_context,
        **kwargs
    ):
        print("\n========== TOOL USED ==========")
        print(f"Tool Type : {type(tool).__name__}")
        if hasattr(tool, "name"):
            print(f"Tool Name : {tool.name}")
        print(f"Tool Args : {tool_args}")
        print("================================\n")
        return None


class TokenUsagePlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="token_usage")

    async def after_model_callback(self, *, callback_context, llm_response):
        usage = llm_response.usage_metadata
        if not usage:
            return None

        print(f"Agent: {callback_context.agent_name}")
        print(f"Prompt tokens: {usage.prompt_token_count or 0}")
        print(f"Completion tokens: {usage.candidates_token_count or 0}")
        print(f"Total tokens: {usage.total_token_count or 0}")

        return None

app=App(
    name="procurement_agent",
    root_agent=root_agent,
    context_cache_config=ContextCacheConfig(
        min_tokens=2048,    # Minimum tokens to trigger caching
        ttl_seconds=3600,    # Store for up to 60 minutes
        cache_intervals=20,  # Refresh after 20 uses
    ),
    plugins=[TokenUsagePlugin(),ToolUsagePlugin()],
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=100,
        overlap_size=1,
        summarizer=my_summarizer,
    )
)

