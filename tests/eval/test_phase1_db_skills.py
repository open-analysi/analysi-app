"""Eval test: runbook matching composition path with DB-backed skills.

Runs the full run_phase1 graph with:
- Real LLM calls (requires ANTHROPIC_API_KEY)
- DatabaseResourceStore backed by PostgreSQL
- Skills seeded in the database (not filesystem)

This proves end-to-end that the composition path works when skills
are loaded from the database by name (not cy_name).

Run with: pytest -m eval tests/eval/test_phase1_db_skills.py -v
"""

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from langchain_anthropic import ChatAnthropic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysi.agentic_orchestration.langgraph.kea.phase1.graph import run_phase1
from analysi.agentic_orchestration.langgraph.skills.db_store import (
    DatabaseResourceStore,
)
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

# =============================================================================
# Test Data
# =============================================================================

# Novel alert that won't match any seeded runbook → forces composition path
ALERT_NOVEL = {
    "title": "Cryptocurrency Mining Process Detected on Production Server",
    "detection_rule": "EDR-CryptoMiner-Process",
    "alert_type": "Malware",
    "subcategory": "Cryptomining",
    "source_category": "EDR",
    "severity": "high",
    "description": (
        "Unauthorized cryptocurrency mining process detected on production "
        "web server. Process xmrig consuming 95% CPU. Outbound connections "
        "to known mining pool stratum+tcp://pool.minexmr.com:4444."
    ),
    "mitre_tactics": ["TA0040", "TA0011"],
}

TENANT_ID = f"eval-phase1-db-{uuid4().hex[:8]}"


# =============================================================================
# Result Container
# =============================================================================


@dataclass
class Phase1DBResult:
    """Container for runbook matching result and DB verification data."""

    result: dict[str, Any]
    alert_name: str
    # Pre-fetched DB data for verification (avoids cross-event-loop issues)
    db_runbook_content: str | None = None
    db_index_data: list | None = None


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def composition_result(anthropic_api_key):
    """Run runbook matching composition path with DB skills (cached for module).

    Seeds skills in DB, then runs run_phase1() with a novel alert that
    forces the composition path.

    Creates its own engine inline (can't depend on function-scoped fixtures).
    """

    async def run():
        from sqlalchemy.ext.asyncio import create_async_engine

        from analysi.db.base import Base
        from tests.test_config import IntegrationTestConfig

        database_url = IntegrationTestConfig.get_database_url()
        engine = create_async_engine(database_url, echo=False, pool_size=3)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Seed skills in DB
        async with session_factory() as session:
            km_repo = KnowledgeModuleRepository(session)
            ku_repo = KnowledgeUnitRepository(session)

            skill = await km_repo.create_skill(
                TENANT_ID,
                {
                    "name": "runbooks-manager",
                    "description": "Build, match, and manage security investigation runbooks",
                    "cy_name": f"runbooks_manager_{uuid4().hex[:6]}",
                },
            )
            ns = f"/{skill.component.cy_name}/"

            # SKILL.md
            doc = await ku_repo.create_document_ku(
                TENANT_ID,
                {
                    "name": "SKILL.md",
                    "doc_format": "markdown",
                    "markdown_content": (
                        "# runbooks-manager\n\n"
                        "Build, match, and manage security investigation runbooks.\n\n"
                        "## References\n"
                        "- `references/matching/composition-guide.md` - How to compose runbooks\n"
                        "- `references/building/format-specification.md` - Runbook format spec\n\n"
                        "## Repository\n"
                        "- `repository/sql-injection.md` - SQL injection runbook\n"
                        "- `repository/phishing.md` - Phishing runbook"
                    ),
                    "content": None,
                },
                namespace=ns,
            )
            await km_repo.add_document_to_skill(
                TENANT_ID, skill.component_id, doc.component_id, "SKILL.md"
            )

            # references/matching/composition-guide.md
            doc_guide = await ku_repo.create_document_ku(
                TENANT_ID,
                {
                    "name": "composition-guide.md",
                    "doc_format": "markdown",
                    "markdown_content": (
                        "# Composition Guide\n\n"
                        "## Strategies\n"
                        "1. **same_attack_family_adaptation** - Adapt a similar runbook\n"
                        "2. **multi_source_blending** - Blend multiple runbooks\n"
                        "3. **category_based_assembly** - Assemble from category patterns\n"
                        "4. **minimal_scaffold** - Create minimal scaffold for novel alerts\n"
                    ),
                    "content": None,
                },
                namespace=ns,
            )
            await km_repo.add_document_to_skill(
                TENANT_ID,
                skill.component_id,
                doc_guide.component_id,
                "references/matching/composition-guide.md",
            )

            # references/building/format-specification.md
            doc_format = await ku_repo.create_document_ku(
                TENANT_ID,
                {
                    "name": "format-specification.md",
                    "doc_format": "markdown",
                    "markdown_content": (
                        "# Runbook Format Specification\n\n"
                        "## Required Sections\n"
                        "- Title\n"
                        "- Overview\n"
                        "- Investigation Steps (with ★ for critical steps)\n"
                        "- Containment Actions\n"
                        "- Recovery Steps"
                    ),
                    "content": None,
                },
                namespace=ns,
            )
            await km_repo.add_document_to_skill(
                TENANT_ID,
                skill.component_id,
                doc_format.component_id,
                "references/building/format-specification.md",
            )

            # repository/sql-injection.md
            doc_sqli = await ku_repo.create_document_ku(
                TENANT_ID,
                {
                    "name": "sql-injection.md",
                    "doc_format": "markdown",
                    "markdown_content": (
                        "# SQL Injection Detection Runbook\n\n"
                        "## Overview\n"
                        "Investigation steps for SQL injection attacks.\n\n"
                        "## Investigation Steps\n"
                        "1. ★ Review WAF logs for injection patterns\n"
                        "2. Check database query logs\n"
                        "3. Identify affected endpoints"
                    ),
                    "content": None,
                },
                namespace=ns,
            )
            await km_repo.add_document_to_skill(
                TENANT_ID,
                skill.component_id,
                doc_sqli.component_id,
                "repository/sql-injection.md",
            )

            # index/all_runbooks KUTable — needed for composed runbook storage
            index_content = [
                {
                    "filename": "sql-injection.md",
                    "title": "SQL Injection Detection Runbook",
                    "alert_type": "Intrusion",
                    "source_category": "WAF",
                },
                {
                    "filename": "phishing.md",
                    "title": "Phishing Email Investigation Runbook",
                    "alert_type": "Phishing",
                    "source_category": "Email",
                },
            ]
            index_table = await ku_repo.create_table_ku(
                TENANT_ID,
                {
                    "name": "all_runbooks",
                    "content": index_content,
                    "schema": {},
                    "row_count": len(index_content),
                    "column_count": 0,
                },
                namespace=ns,
            )
            await km_repo.add_document_to_skill(
                TENANT_ID,
                skill.component_id,
                index_table.component_id,
                "index/all_runbooks",
            )

            # repository/phishing.md
            doc_phish = await ku_repo.create_document_ku(
                TENANT_ID,
                {
                    "name": "phishing.md",
                    "doc_format": "markdown",
                    "markdown_content": (
                        "# Phishing Email Investigation Runbook\n\n"
                        "## Overview\n"
                        "Investigation for phishing emails.\n\n"
                        "## Investigation Steps\n"
                        "1. ★ Analyze email headers\n"
                        "2. Check sender reputation\n"
                        "3. Examine attachments in sandbox"
                    ),
                    "content": None,
                },
                namespace=ns,
            )
            await km_repo.add_document_to_skill(
                TENANT_ID,
                skill.component_id,
                doc_phish.component_id,
                "repository/phishing.md",
            )

        # Create store and LLM
        store = DatabaseResourceStore(
            session_factory=session_factory,
            tenant_id=TENANT_ID,
        )
        llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=str(anthropic_api_key),
            max_tokens=4096,
        )

        # Run runbook matching — novel alert forces composition path
        # repository_path doesn't matter for DB-backed skills, but matcher needs it
        # Use a non-existent path so matcher finds no filesystem runbooks
        import tempfile

        empty_repo = tempfile.mkdtemp(prefix="eval-empty-repo-")

        result = await run_phase1(
            alert=ALERT_NOVEL,
            llm=llm,
            store=store,
            repository_path=empty_repo,
        )

        await asyncio.sleep(0.5)

        # Read back from DB for verification (same event loop as store)
        db_runbook_content = None
        db_index_data = None
        filename = result.get("matching_report", {}).get("composed_runbook")
        if filename:
            db_runbook_content = await store.read_async(
                "runbooks-manager", f"repository/{filename}"
            )
            db_index_data = await store.read_table_async(
                "runbooks-manager", "index/all_runbooks"
            )

        await engine.dispose()
        return result, db_runbook_content, db_index_data

    phase1_result, db_content, db_index = asyncio.run(run())

    return Phase1DBResult(
        result=phase1_result,
        alert_name="Cryptomining (Novel)",
        db_runbook_content=db_content,
        db_index_data=db_index,
    )


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.eval
def test_composition_produces_runbook(composition_result):
    """Runbook matching produces a runbook via composition path."""
    result = composition_result.result
    assert result["runbook"] is not None, "Expected composed runbook"
    assert len(result["runbook"]) > 100, (
        f"Runbook too short ({len(result['runbook'])} chars)"
    )


@pytest.mark.eval
def test_composition_decision(composition_result):
    """Matching report indicates composition (not match)."""
    report = composition_result.result["matching_report"]
    assert report["decision"] == "composed", (
        f"Expected 'composed' decision, got '{report['decision']}'"
    )


@pytest.mark.eval
def test_composition_has_gaps(composition_result):
    """Composition path produces gap analysis."""
    result = composition_result.result
    # Novel alert should trigger gap analysis
    assert result["gaps"] is not None, "Expected gap analysis for novel alert"


@pytest.mark.eval
def test_composition_has_strategy(composition_result):
    """Composition path selects a strategy."""
    result = composition_result.result
    assert result["strategy"] is not None, "Expected composition strategy"


@pytest.mark.eval
def test_runbook_has_investigation_steps(composition_result):
    """Composed runbook contains investigation steps."""
    runbook = composition_result.result["runbook"]
    # Should have investigation content
    lower = runbook.lower()
    assert "investigation" in lower or "steps" in lower or "actions" in lower, (
        f"Runbook missing investigation content: {runbook[:200]}"
    )


@pytest.mark.eval
def test_matching_report_has_composed_runbook_filename(composition_result):
    """Matching report includes a generated filename (not default)."""
    report = composition_result.result["matching_report"]
    filename = report.get("composed_runbook", "")
    assert filename.endswith(".md"), f"Expected .md filename, got: {filename!r}"
    # Should be a generated slug, not the default placeholder
    assert filename != "composed-runbook.md", (
        "Expected generated filename, got default 'composed-runbook.md'"
    )


@pytest.mark.eval
def test_composed_runbook_persisted_in_db(composition_result):
    """Composed runbook is readable from the DB after run_phase1."""
    filename = composition_result.result["matching_report"].get("composed_runbook")
    assert filename, "No composed_runbook filename in matching report"

    content = composition_result.db_runbook_content
    assert content is not None, (
        f"Composed runbook 'repository/{filename}' not found in DB"
    )
    assert len(content) > 100, f"Persisted runbook too short ({len(content)} chars)"
    # Content should match what run_phase1 returned
    assert content == composition_result.result["runbook"], (
        "DB content doesn't match returned runbook"
    )


@pytest.mark.eval
def test_index_updated_with_composed_runbook(composition_result):
    """The runbook index KUTable includes the new composed entry."""
    filename = composition_result.result["matching_report"].get("composed_runbook")
    assert filename, "No composed_runbook filename in matching report"

    index = composition_result.db_index_data
    assert index is not None, "Index table not found in DB"
    assert isinstance(index, list), f"Expected list, got {type(index)}"

    # Find the composed entry
    composed_entries = [e for e in index if e.get("filename") == filename]
    assert len(composed_entries) == 1, (
        f"Expected 1 index entry for '{filename}', found {len(composed_entries)}. "
        f"Index filenames: {[e.get('filename') for e in index]}"
    )
    entry = composed_entries[0]
    assert entry.get("source") == "composed", (
        f"Expected source='composed', got '{entry.get('source')}'"
    )
