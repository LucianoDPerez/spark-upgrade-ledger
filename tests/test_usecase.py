import json
import unittest

from src.cache import TTLCache
from src.domain import ValidationError
from src.ratelimit import MinIntervalLimiter
from src.usecase import BuildChecklistUseCase, ChecklistRequest

SOURCE = (
    "URL: https://huggingface.co/XHToken/Spark-X2.6-4B/discussions/34\n"
    "cortiq 0.8.67 adds a native CUDA backend, and Spark-X2.6-4B is the first model it runs.\n"
    "Past 8192 tokens the Turbo far field takes over, on CUDA as well."
)

VALID = json.dumps(
    {
        "items": [
            {
                "id": "C1",
                "title": "cortiq 0.8.67 agrega backend CUDA nativo",
                "affects": "motor CUDA",
                "source_quote": "cortiq 0.8.67 adds a native CUDA backend",
                "breaking": False,
            }
        ]
    }
)


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self.responses.pop(0)


class UseCaseTests(unittest.TestCase):
    def make(self, llm):
        return BuildChecklistUseCase(
            llm=llm,
            cache=TTLCache(),
            limiter=MinIntervalLimiter(interval=0.0),
            auditor=None,
        )

    def test_generates_and_caches(self):
        llm = FakeLLM([VALID])
        usecase = self.make(llm)
        first = usecase.execute(ChecklistRequest(SOURCE))
        second = usecase.execute(ChecklistRequest(SOURCE))
        self.assertEqual(len(first.items), 1)
        self.assertEqual(first.items[0].line_start, 1)
        self.assertEqual(llm.calls, 1)
        self.assertEqual(first, second)

    def test_malformed_output_is_rejected_before_cache(self):
        llm = FakeLLM(["not json at all"])
        usecase = self.make(llm)
        with self.assertRaisesRegex(ValidationError, "not valid JSON"):
            usecase.execute(ChecklistRequest(SOURCE))
        self.assertEqual(llm.calls, 1)

    def test_invented_number_is_rejected(self):
        bad = VALID.replace("0.8.67 agrega", "7.7.7 agrega")
        usecase = self.make(FakeLLM([bad]))
        with self.assertRaisesRegex(ValidationError, "invented number"):
            usecase.execute(ChecklistRequest(SOURCE))

    def test_short_input_is_rejected_before_llm(self):
        llm = FakeLLM([VALID])
        usecase = self.make(llm)
        with self.assertRaisesRegex(ValidationError, "too short"):
            usecase.execute(ChecklistRequest("demo corto"))
        self.assertEqual(llm.calls, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
