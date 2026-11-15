"""Review B S1, S3 and the --limit refusal (proposed tests, not committed)."""
import json

import pytest

from RevenueChaser.core import rawstore, subscription_usage
from RevenueChaser.core.providers import grok
from RevenueChaser.module_relatedness import __main__ as cli

_FETCH_GROK = subscription_usage.fetch_grok          # the real reader, before the fixture replaces it


@pytest.mark.parametrize("body", [{}, {"error": "unauthorized"}, {"config": None}, []])
def test_a_billing_reply_without_config_is_no_reading(body):
    with pytest.raises(subscription_usage.SubscriptionUsageError):
        subscription_usage.parse_grok_billing(body)






def test_limit_is_refused_for_grok_naming(monkeypatch):
    monkeypatch.setattr(cli.engine, "run", lambda **k: pytest.fail("must not run"))
    with pytest.raises(SystemExit) as exit_:
        cli.main(["--name-themes", "--provider", "grok", "--limit", "20"])
    assert exit_.value.code == 2
