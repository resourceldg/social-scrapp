"""
Tests for Fase 3 components:
  - ContactEnricher (web scraper — zero cost, no API keys)
  - ABTestRunner
  - SemanticRelevanceScorer (fallback when sentence-transformers absent)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models import Lead
from scoring.ab_test import ABTestReport, ABTestRunner, VariantResult
from scoring.semantic_relevance import semantic_boost
from scoring.weights_config import RankingMode
from utils.contact_enricher import (
    ContactEnricher,
    EnrichmentResult,
    _extract_emails,
    _extract_phones,
    _extract_social_links,
    _generate_email_patterns,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _lead(
    bio: str = "",
    lead_type: str = "",
    platform: str = "instagram",
    followers: str = "",
    website: str = "",
    email: str = "",
    profile_url: str = "https://instagram.com/test",
) -> Lead:
    return Lead(
        source_platform=platform,
        search_term="test",
        name="Test Lead",
        bio=bio,
        lead_type=lead_type,
        followers=followers,
        website=website,
        email=email,
        profile_url=profile_url,
    )


def _mock_fetch(enricher: ContactEnricher, pages: dict[str, str]):
    """
    Patch _fetch_text_and_links to return canned text per URL.
    Keys are matched by checking if the URL ends with the key (exact path match).
    """
    def _fake_fetch(url: str):
        url_stripped = url.rstrip("/")
        for pattern, body in pages.items():
            pat_stripped = pattern.rstrip("/")
            if url_stripped == pat_stripped or url_stripped.endswith("/" + pat_stripped.lstrip("/")):
                return body, []
        return "", []
    enricher._fetch_text_and_links = _fake_fetch


# ── ContactEnricher ────────────────────────────────────────────────────────────

class TestContactEnricher:
    def test_enrich_result_dataclass_defaults(self):
        r = EnrichmentResult()
        assert r.email == ""
        assert r.confidence == 0
        assert r.source == "none"
        assert r.emails == []
        assert r.phones == []
        assert r.social_links == []

    def test_no_domain_returns_empty(self):
        enricher = ContactEnricher()
        result = enricher.enrich(domain="")
        assert result.email == ""
        assert result.source == "none"

    def test_email_found_on_homepage(self):
        enricher = ContactEnricher(delay=0, max_pages=0)  # max_pages=0 → only homepage
        _mock_fetch(enricher, {
            "https://studiogomez.com": "Welcome to Studio Gomez. Contact us: carlos@studiogomez.com",
        })
        result = enricher.enrich(domain="studiogomez.com")
        assert result.email == "carlos@studiogomez.com"
        assert result.confidence == 70
        assert result.source == "homepage"

    def test_contact_page_email_higher_confidence(self):
        enricher = ContactEnricher(delay=0, max_pages=3)
        pages = {
            "https://studiogomez.com": "Welcome to our studio",
            "https://studiogomez.com/contact": "Email us at hello@studiogomez.com",
        }
        _mock_fetch(enricher, pages)
        result = enricher.enrich(domain="studiogomez.com")
        assert result.email == "hello@studiogomez.com"
        assert result.confidence == 100

    def test_own_domain_email_preferred(self):
        """Emails on the lead's own domain are ranked first."""
        enricher = ContactEnricher(delay=0, max_pages=0)
        _mock_fetch(enricher, {
            "https://studio.com": "Contact us via info@studio.com or reply@mailchimp.com",
        })
        result = enricher.enrich(domain="studio.com")
        assert result.email == "info@studio.com"

    def test_noreply_excluded(self):
        enricher = ContactEnricher(delay=0, max_pages=0)
        _mock_fetch(enricher, {
            "https://studio.com": "noreply@studio.com is system, contact@studio.com for humans",
        })
        result = enricher.enrich(domain="studio.com")
        assert result.email == "contact@studio.com"

    def test_no_email_found_returns_empty(self):
        enricher = ContactEnricher(delay=0, max_pages=1)
        _mock_fetch(enricher, {"https://studio.com": "No contact info here."})
        with patch("utils.contact_enricher._domain_has_mx", return_value=False):
            result = enricher.enrich(domain="studio.com", full_name="")
        assert result.email == ""

    def test_pattern_generation_fallback(self):
        """When no email scraped, generates patterns if MX record exists."""
        enricher = ContactEnricher(delay=0, max_pages=1)
        _mock_fetch(enricher, {"https://studio.com": "No email here."})
        with patch("utils.contact_enricher._domain_has_mx", return_value=True):
            result = enricher.enrich(domain="studio.com", full_name="Carlos Gomez")
        assert result.email != ""
        assert result.confidence == 40
        assert result.source == "pattern_generated"
        assert "carlos" in result.email

    def test_phones_extracted(self):
        enricher = ContactEnricher(delay=0, max_pages=0)
        _mock_fetch(enricher, {"https://studio.com": "Call us: +54 11 4567-8901"})
        result = enricher.enrich(domain="studio.com")
        assert len(result.phones) > 0

    def test_domain_search_returns_list(self):
        enricher = ContactEnricher(delay=0, max_pages=0)
        _mock_fetch(enricher, {"https://studio.com": "info@studio.com | press@studio.com"})
        results = enricher.domain_search("studio.com")
        assert isinstance(results, list)
        assert any(r["email"] == "info@studio.com" for r in results)

    def test_fetch_error_handled_gracefully(self):
        enricher = ContactEnricher(delay=0)
        with patch.object(enricher, "_fetch_text_and_links", side_effect=Exception("timeout")):
            # Should not raise
            result = enricher.enrich_from_website("https://studio.com")
        assert result.email == ""


# ── Utility functions ──────────────────────────────────────────────────────────

class TestContactEnricherUtils:
    def test_extract_emails_basic(self):
        emails = _extract_emails("Contact: info@studiodesign.com", "studiodesign.com")
        assert "info@studiodesign.com" in emails

    def test_extract_emails_own_domain_first(self):
        emails = _extract_emails(
            "other@third.com and info@studio.com", "studio.com"
        )
        assert emails[0] == "info@studio.com"

    def test_extract_emails_excludes_noreply(self):
        emails = _extract_emails("noreply@studio.com and info@studio.com", "studio.com")
        assert "noreply@studio.com" not in emails

    def test_extract_phones(self):
        phones = _extract_phones("Llámanos: +34 91 234 5678")
        assert len(phones) > 0

    def test_generate_email_patterns(self):
        patterns = _generate_email_patterns("Carlos Gomez", "studiogomez.com")
        assert "carlos@studiogomez.com" in patterns
        assert "info@studiogomez.com" in patterns
        assert len(patterns) <= 6

    def test_generate_email_patterns_no_last_name(self):
        patterns = _generate_email_patterns("Studio", "studio.com")
        assert any("studio.com" in p for p in patterns)

    def test_extract_social_links(self):
        links = [
            "https://www.instagram.com/studiodesign",
            "https://linkedin.com/company/studio",
            "https://example.com/about",
        ]
        socials = _extract_social_links(links, "https://studio.com")
        assert "https://www.instagram.com/studiodesign" in socials
        assert "https://linkedin.com/company/studio" in socials
        assert "https://example.com/about" not in socials


# ── ABTestRunner ───────────────────────────────────────────────────────────────

class TestABTestRunner:
    def _make_leads(self, n: int = 5) -> list[Lead]:
        return [
            _lead(
                bio="luxury interior design studio contemporary art collector",
                lead_type="interior_designer",
                platform="instagram",
                followers="15K",
                profile_url=f"https://instagram.com/lead{i}",
            )
            for i in range(n)
        ]

    def test_run_produces_report(self):
        runner = ABTestRunner(
            variants=[RankingMode.OUTREACH_PRIORITY, RankingMode.SPECIFIER_NETWORK]
        )
        leads = self._make_leads(3)
        report = runner.run(leads)

        assert report.n_leads == 3
        assert set(report.variants) == {
            RankingMode.OUTREACH_PRIORITY.value,
            RankingMode.SPECIFIER_NETWORK.value,
        }
        assert len(report.avg_score) == 2
        for mode in report.variants:
            assert 0 <= report.avg_score[mode] <= 100
            assert report.score_std[mode] >= 0

    def test_report_has_all_keys(self):
        runner = ABTestRunner(variants=[RankingMode.OUTREACH_PRIORITY])
        report = runner.run(self._make_leads(2))
        mode = RankingMode.OUTREACH_PRIORITY.value
        assert mode in report.avg_score
        assert mode in report.avg_opportunity
        assert mode in report.high_opp_count
        assert mode in report.avg_confidence
        assert mode in report.score_std

    def test_precision_computed_with_converted_urls(self):
        runner = ABTestRunner(
            variants=[RankingMode.OUTREACH_PRIORITY],
            top_pct=0.5,
        )
        leads = self._make_leads(4)
        converted = {leads[0].profile_url}
        report = runner.run(leads, converted_urls=converted)
        mode = RankingMode.OUTREACH_PRIORITY.value
        assert mode in report.precision
        assert 0.0 <= report.precision[mode] <= 1.0

    def test_no_precision_without_converted_urls(self):
        runner = ABTestRunner(variants=[RankingMode.OUTREACH_PRIORITY])
        report = runner.run(self._make_leads(2))
        assert report.precision == {}

    def test_assign_variant_is_deterministic(self):
        runner = ABTestRunner(
            variants=[RankingMode.OUTREACH_PRIORITY, RankingMode.SPECIFIER_NETWORK]
        )
        url = "https://instagram.com/studiodesign"
        v1 = runner.assign_variant(url)
        v2 = runner.assign_variant(url)
        assert v1 == v2

    def test_assign_variant_distributes(self):
        runner = ABTestRunner(
            variants=[RankingMode.OUTREACH_PRIORITY, RankingMode.SPECIFIER_NETWORK]
        )
        urls = [f"https://instagram.com/lead{i}" for i in range(100)]
        assignments = [runner.assign_variant(u) for u in urls]
        # Both variants should appear with roughly 50% each (hash distribution)
        counts = {v: assignments.count(v) for v in runner.variants}
        for v in runner.variants:
            assert 20 <= counts[v] <= 80, f"Variant {v} appears {counts[v]} times"

    def test_summary_text(self):
        runner = ABTestRunner(variants=[RankingMode.OUTREACH_PRIORITY])
        report = runner.run(self._make_leads(2))
        summary = report.summary()
        assert "outreach_priority" in summary
        assert "leads" in summary.lower()

    def test_recommended_mode_returns_string(self):
        runner = ABTestRunner(
            variants=[RankingMode.OUTREACH_PRIORITY, RankingMode.SPECIFIER_NETWORK]
        )
        report = runner.run(self._make_leads(3))
        rec = report.recommended_mode()
        assert isinstance(rec, str)
        assert rec in report.variants

    def test_empty_leads_handled(self):
        runner = ABTestRunner(variants=[RankingMode.OUTREACH_PRIORITY])
        report = runner.run([])
        assert report.n_leads == 0

    def test_ab_report_precision_at_top(self):
        """When all top leads are converted, precision should be 1.0."""
        runner = ABTestRunner(
            variants=[RankingMode.OUTREACH_PRIORITY],
            top_pct=1.0,  # entire list is "top"
        )
        leads = self._make_leads(3)
        converted = {l.profile_url for l in leads}
        report = runner.run(leads, converted_urls=converted)
        mode = RankingMode.OUTREACH_PRIORITY.value
        assert report.precision[mode] == 1.0


# ── SemanticRelevanceScorer ────────────────────────────────────────────────────

class TestSemanticRelevance:
    def test_semantic_boost_returns_zero_without_library(self):
        """When sentence-transformers is not installed, semantic_boost returns 0."""
        import sys

        # Force the module to re-initialize by clearing the singleton
        import scoring.semantic_relevance as sr_module
        original_instance = sr_module._instance
        original_warned = sr_module._warned_unavailable
        sr_module._instance = None
        sr_module._warned_unavailable = False

        # Block the import of sentence_transformers
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            boost, reason = semantic_boost("luxury interior design studio")

        # Restore state
        sr_module._instance = original_instance
        sr_module._warned_unavailable = original_warned

        assert boost == 0.0
        assert reason == ""

    def test_semantic_boost_empty_text(self):
        boost, reason = semantic_boost("")
        assert boost == 0.0
        assert reason == ""

    def test_semantic_boost_whitespace_only(self):
        boost, reason = semantic_boost("   ")
        assert boost == 0.0

    def _make_mock_st_module(self, similarity: float):
        """Return a mock sentence_transformers module returning a fixed similarity."""

        class _FakeTensor:
            """Minimal tensor-like with .max() and .shape."""
            def __init__(self, data: list):
                self._data = data  # list of floats

            def max(self) -> float:
                return max(self._data)

            @property
            def shape(self):
                return (1, len(self._data))

        class MockSentenceTransformer:
            def __init__(self, *a, **kw):
                pass

            def encode(self, texts, **kw):
                n = len(texts) if isinstance(texts, list) else 1
                return _FakeTensor([1.0] * 128)

        _sim = similarity

        class MockUtil:
            @staticmethod
            def cos_sim(a, b):
                # b.shape[1] == number of reference sentences
                n = b.shape[1] if hasattr(b, "shape") else 22
                return [_FakeTensor([_sim] * n)]

        mock_mod = MagicMock()
        mock_mod.SentenceTransformer = MockSentenceTransformer
        mock_mod.util = MockUtil
        return mock_mod

    def test_semantic_boost_with_mock_model(self):
        """Verify the scorer awards boost when cosine similarity is above threshold."""
        import sys
        import scoring.semantic_relevance as sr_module

        original = sr_module._instance
        sr_module._instance = None
        sr_module._warned_unavailable = False

        with patch.dict(sys.modules, {"sentence_transformers": self._make_mock_st_module(0.75)}):
            scorer = sr_module.SemanticRelevanceScorer(threshold=0.55, max_boost=20.0)
            boost, reason = scorer.compute_boost("luxury interior design studio Barcelona")

        sr_module._instance = original

        # (0.75 - 0.55) / (1.0 - 0.55) * 20.0 ≈ 8.9
        assert boost > 0.0
        assert boost <= 20.0
        assert "semantic similarity" in reason

    def test_boost_below_threshold_returns_zero(self):
        """Similarity below threshold → 0 boost."""
        import sys
        import scoring.semantic_relevance as sr_module

        original = sr_module._instance
        sr_module._instance = None

        with patch.dict(sys.modules, {"sentence_transformers": self._make_mock_st_module(0.30)}):
            scorer = sr_module.SemanticRelevanceScorer(threshold=0.55, max_boost=20.0)
            boost, reason = scorer.compute_boost("random unrelated text about nothing")

        sr_module._instance = original

        assert boost == 0.0
        assert reason == ""
