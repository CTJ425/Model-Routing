"""Tests for routing_audit.py pricing: longest-prefix match and per-model cache reads."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "route", "scripts"))

import routing_audit  # noqa: E402

ONE_M_READS = {"out": 0, "in": 0, "cache_read": 1_000_000, "cw5": 0, "cw1h": 0}


def test_opus_5_5_has_its_own_key_and_cache_rate():
    assert routing_audit.price_entry("claude-opus-5-5")[0] == "claude-opus-5-5"
    assert routing_audit.rate("claude-opus-5-5") == (4.0, 20.0)
    # 0.05x of $4, not the default 0.1x.
    assert abs(routing_audit.cost("claude-opus-5-5", ONE_M_READS)["cache_read"] - 0.20) < 1e-9


def test_opus_5_falls_back_to_the_family_key():
    assert routing_audit.price_entry("claude-opus-5")[0] == "claude-opus-"
    assert abs(routing_audit.cost("claude-opus-5", ONE_M_READS)["cache_read"] - 0.50) < 1e-9


def test_sonnet_5_is_priced_at_list():
    assert routing_audit.price_entry("claude-sonnet-5")[0] == "claude-sonnet-5"
    assert routing_audit.rate("claude-sonnet-5") == (2.0, 10.0)
    assert routing_audit.rate("claude-sonnet-4-6") == (3.0, 15.0)
