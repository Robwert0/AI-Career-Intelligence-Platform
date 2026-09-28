import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from eval_match import (  # noqa: E402
    CORRECTION_PREFIX,
    LabelFile,
    RunRecord,
    Tally,
    flip_rate,
    load_label_files,
    suggested_threshold,
    summarise,
    template,
)

from app.ai.match.prompts import correction_message  # noqa: E402
from app.ai.match.schemas import JobPosting, Requirement  # noqa: E402

POSTING = JobPosting(
    title="Backend Engineer",
    required=[Requirement(text="Go", sensitive=False), Requirement(text="EU visa", sensitive=True)],
    preferred=[Requirement(text="Kafka", sensitive=False)],
)


class Counted:
    def __init__(self, calls: int, retries: int) -> None:
        self.calls = calls
        self.retries = retries


def test_a_template_leaves_labels_to_robert_except_sensitive_items() -> None:
    label = template("acme", POSTING)

    assert label.labels == {
        "req:required:0": None,
        "req:required:1": "not_assessed",
        "req:preferred:0": None,
    }
    assert label.labelled() == {"req:required:1": "not_assessed"}
    assert label.compared() == {}


def test_label_files_round_trip_and_are_validated(tmp_path: Path) -> None:
    good = template("acme", POSTING)
    good.labels["req:required:0"] = "demonstrated"
    (tmp_path / "acme.json").write_text(good.model_dump_json())

    assert load_label_files(tmp_path)[0].labelled()["req:required:0"] == "demonstrated"


@pytest.mark.parametrize(
    ("labels", "message"),
    [
        ({"req:required:7": "partial"}, "not in the posting"),
        ({"req:required:0": "great"}, "unknown statuses"),
    ],
)
def test_a_label_that_cannot_be_compared_is_rejected(
    labels: dict[str, str | None], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        LabelFile(slug="acme", posting=POSTING, labels=labels).checked()


def test_the_threshold_is_the_midpoint_between_clean_sets() -> None:
    assert suggested_threshold([0.71, 0.8], [0.4, 0.51]) == pytest.approx(0.61)


def test_overlapping_sets_give_no_threshold() -> None:
    assert suggested_threshold([0.5, 0.8], [0.6]) is None


def test_agreement_and_confusion_count_every_labelled_requirement() -> None:
    tally = Tally()

    tally.add({"a": "demonstrated", "b": "partial"}, {"a": "demonstrated", "b": "not_demonstrated"})

    assert (tally.matches, tally.labelled, tally.agreement) == (1, 2, 0.5)
    assert tally.confusion[("partial", "not_demonstrated")] == 1


def test_a_requirement_the_model_never_reported_is_a_disagreement() -> None:
    tally = Tally()

    tally.add({"a": "demonstrated"}, {})

    assert tally.confusion[("demonstrated", "missing")] == 1


def test_flip_rate_counts_requirements_that_changed_between_runs() -> None:
    runs = [{"a": "partial", "b": "unmet"}, {"a": "partial", "b": "not_demonstrated"}]

    assert flip_rate(runs) == 0.5
    assert flip_rate([]) == 0.0


def test_the_retry_detector_matches_the_real_correction_message() -> None:
    assert correction_message("x: missing").content.startswith(CORRECTION_PREFIX)
    assert CORRECTION_PREFIX


def test_the_summary_reports_every_metric_the_spec_asks_for() -> None:
    label = template("acme", POSTING)
    label.labels["req:required:0"] = "demonstrated"
    records = [
        RunRecord("acme", 1, 70, {"req:required:0": "demonstrated"}, 40.0, cited=4, dropped=1),
        RunRecord("acme", 2, 66, {"req:required:0": "partial"}, 50.0, cited=4, dropped=0),
    ]

    summary = summarise([label], records, [Counted(calls=10, retries=1)])  # type: ignore[list-item]

    assert summary["status_agreement"] == 0.5
    assert summary["invalid_json_rate"] == round(1 / 9, 3)
    assert summary["hallucinated_citation_rate"] == 0.125
    assert summary["seconds_per_analysis"] == {"median": 45.0, "max": 50.0}
    assert summary["stability"]["acme"]["score_range"] == 4
    assert summary["stability"]["acme"]["status_flip_rate"] == 1.0
