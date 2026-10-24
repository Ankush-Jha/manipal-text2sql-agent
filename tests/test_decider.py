import math
import pytest
from agent import decider


class FakeResp:
    def __init__(self, top):
        self.top = top
    def raise_for_status(self): pass
    def json(self):
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": [{"token": t, "logprob": math.log(p)} for t, p in self.top]}]}}]}


def run(monkeypatch, top, options=("yes", "no", "ambiguous")):
    monkeypatch.setattr(decider.httpx, "post", lambda *a, **k: FakeResp(top))
    return decider.decide_local("http://x", "q?", list(options))


def test_article_a_does_not_overwrite_letter_a(monkeypatch):
    # "a" and " A" are other spellings in the top-20; the real letter A must keep its mass
    p = run(monkeypatch, [("A", 0.90), ("B", 0.05), ("a", 1e-5), (" a", 1e-6), ("C", 0.04)])
    assert p["yes"] > 0.89 and abs(sum(p.values()) - 1) < 1e-9


def test_spellings_of_one_letter_are_summed(monkeypatch):
    p = run(monkeypatch, [("B", 0.3), (" B", 0.3), ("A", 0.4)])
    assert p["no"] == pytest.approx(0.6) and p["yes"] == pytest.approx(0.4)


def test_missing_letters_fail_loudly(monkeypatch):
    with pytest.raises(decider.DeciderError):
        run(monkeypatch, [("The", 0.9), ("Answer", 0.1)])
