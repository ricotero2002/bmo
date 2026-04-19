from unittest.mock import patch

from src.core.llm import LLMFactory


class DummyModel:
    def __init__(self, model: str, **kwargs):
        self.model = model
        self.kwargs = kwargs
        self.fallbacks = None
        self.retry_kwargs = None

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def with_structured_output(self, response_format):
        self.response_format = response_format
        return self

    def with_fallbacks(self, fallbacks):
        self.fallbacks = fallbacks
        return self

    def with_retry(self, **kwargs):
        self.retry_kwargs = kwargs
        return self


@patch("src.core.llm.ChatOpenRouter", new=DummyModel)
def test_create_uses_heavy_primary_and_fallbacks():
    model = LLMFactory.create()

    assert model.model == LLMFactory.HEAVY_MODEL_NAMES[0]
    assert model.fallbacks is not None
    assert len(model.fallbacks) == len(LLMFactory.HEAVY_MODEL_NAMES) - 1
    assert model.retry_kwargs["stop_after_attempt"] == 3


@patch("src.core.llm.ChatOpenRouter", new=DummyModel)
def test_create_lite_uses_lite_primary():
    model = LLMFactory.create_lite()

    assert model.model == LLMFactory.LITE_MODEL_NAMES[0]
    assert model.fallbacks[0].model == LLMFactory.LITE_MODEL_NAMES[1]


@patch("src.core.llm.ChatOpenRouter", new=DummyModel)
def test_create_planner_prioritizes_thinking_model():
    model = LLMFactory.create_planner()

    assert model.model == LLMFactory.PLANNER_PRIMARY


@patch("src.core.llm.ChatOpenRouter", new=DummyModel)
def test_create_judge_prioritizes_judge_models():
    model = LLMFactory.create_judge()

    assert model.model == LLMFactory.JUDGE_PRIMARY
    assert model.fallbacks[0].model == LLMFactory.JUDGE_SECONDARY


@patch("src.core.llm.ChatOpenRouter", new=DummyModel)
def test_create_coder_prioritizes_qwen_coder():
    model = LLMFactory.create_coder()

    assert model.model == LLMFactory.CODER_PRIMARY
