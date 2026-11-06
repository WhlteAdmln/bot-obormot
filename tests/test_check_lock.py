from pathlib import Path

from scripts.check_lock import check_lock


def test_check_lock_accepts_satisfied_constraints(tmp_path: Path):
    requirements = tmp_path / "requirements.txt"
    lock = tmp_path / "requirements-lock.txt"
    requirements.write_text("Example_Package[extra]>=1.2,<2.0\nother~=3.1\n")
    lock.write_text("example-package==1.5.0\nother==3.1.4\n")

    assert check_lock(requirements, lock) == []


def test_check_lock_reports_missing_direct_dependency(tmp_path: Path):
    requirements = tmp_path / "requirements.txt"
    lock = tmp_path / "requirements-lock.txt"
    requirements.write_text("missing-package>=1\n")
    lock.write_text("present-package==1.0\n")

    assert check_lock(requirements, lock) == ["Missing from lock file: missing-package"]


def test_check_lock_reports_out_of_range_version(tmp_path: Path):
    requirements = tmp_path / "requirements.txt"
    lock = tmp_path / "requirements-lock.txt"
    requirements.write_text("example-package>=2,<3\n")
    lock.write_text("example-package==1.9\n")

    assert check_lock(requirements, lock) == [
        "Locked example-package==1.9 does not satisfy <3,>=2"
    ]
