from pathlib import Path

import pytest

from services.verification import ResultVerifier, VerificationError
from workers.analysis import AnalysisPipeline

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"


def test_verifier_rejects_invalid_evidence_reference():
    result = AnalysisPipeline().run(FIXTURE, "Add RETURNED after SHIPPED and process a refund.")
    broken = result.model_copy(deep=True)
    broken.risks[0].evidence = ["missing-evidence"]
    from services.repository_analysis import RepositoryAnalyzer, SnapshotService

    snapshot = SnapshotService().from_local(FIXTURE)
    index = RepositoryAnalyzer().scan(FIXTURE, snapshot.id, snapshot.commit_sha)
    with pytest.raises(VerificationError, match="nonexistent evidence"):
        ResultVerifier().verify(broken, index)


def test_verifier_rejects_unknown_test_gap_component():
    result = AnalysisPipeline().run(FIXTURE, "Add RETURNED after SHIPPED and process a refund.")
    broken = result.model_copy(deep=True)
    broken.test_gaps[0].affected_components.append("missing-component")
    from services.repository_analysis import RepositoryAnalyzer, SnapshotService

    snapshot = SnapshotService().from_local(FIXTURE)
    index = RepositoryAnalyzer().scan(FIXTURE, snapshot.id, snapshot.commit_sha)
    with pytest.raises(VerificationError, match="unknown component"):
        ResultVerifier().verify(broken, index)
