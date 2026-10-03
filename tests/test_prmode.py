import json
import os
import shutil
import subprocess

import pytest

from gradle10_ready.cli import main
from gradle10_ready.diffmode import GitError, scan_against_base

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, env={**os.environ, **ENV}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "build.gradle").write_text("plugins { id 'java' }\ngroup 'old'\nrepositories {\n    maven { url 'https://old' }\n}\n")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle").write_text("version '1'\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "branch", "base")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    return tmp_path


def commit(repo, msg="change"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def new(repo, **kw):
    r = scan_against_base(str(repo), "base", **kw)
    return [(f.rule, f.file, f.snippet) for f in r.findings], r.pr


def test_unchanged_branch_has_no_new_findings(repo):
    f, pr = new(repo)
    assert f == [] and pr == {"base": "base", "existing": 3, "resolved": 0}


def test_only_the_introduced_finding_is_reported(repo):
    with open(repo / "build.gradle", "a") as fh:
        fh.write("sourceCompatibility '17'\n")
    commit(repo)
    f, pr = new(repo)
    assert f == [("space-assignment", "build.gradle", "sourceCompatibility '17'")]
    assert pr["existing"] == 3


def test_inserting_lines_above_an_old_finding_does_not_make_it_new(repo):
    src = (repo / "build.gradle").read_text()
    (repo / "build.gradle").write_text("// header\n// more\n" + src)
    commit(repo)
    assert new(repo)[0] == []


def test_uncommitted_working_tree_changes_count(repo):
    (repo / "app" / "build.gradle").write_text("version '1'\ndescription 'x'\n")
    f, _ = new(repo)
    assert f == [("space-assignment", "app/build.gradle", "description 'x'")]


def test_resolved_findings_are_counted_and_renames_are_followed(repo):
    git(repo, "mv", "app/build.gradle", "app/build-renamed.gradle")
    (repo / "build.gradle").write_text("plugins { id 'java' }\ngroup = 'old'\n")
    commit(repo)
    f, pr = new(repo)
    assert f == []
    assert pr["resolved"] == 2 and pr["existing"] == 1  # group and url fixed; the renamed file's finding is the same one


def test_a_new_file_is_entirely_new_and_a_subdirectory_can_be_scanned(repo):
    (repo / "lib").mkdir()
    (repo / "lib" / "build.gradle").write_text("group 'x'\nname 'y'\n")
    commit(repo)
    f, _ = new(repo)
    assert [x[1] for x in f] == ["lib/build.gradle", "lib/build.gradle"]
    sub, _ = new(repo / "app")
    assert sub == []


def test_cli_exit_codes_and_json(repo, capsys):
    assert main([str(repo), "--base", "base"]) == 0
    with open(repo / "build.gradle", "a") as fh:
        fh.write("description 'new'\n")
    commit(repo)
    assert main([str(repo), "--base", "base", "-f", "json"]) == 1
    capsys.readouterr()
    assert main([str(repo), "--base", "base", "--fail-on", "never", "-f", "json"]) == 0
    out = capsys.readouterr().out
    d = json.loads(out[out.rindex('{\n  "tool"'):])
    assert d["pullRequest"] == {"base": "base", "existing": 3, "resolved": 0} and len(d["findings"]) == 1


def test_unknown_base_and_not_a_repo(tmp_path, repo, capsys):
    assert main([str(repo), "--base", "nope"]) == 2
    assert "fetch-depth: 0" in capsys.readouterr().err
    other = tmp_path.parent / (tmp_path.name + "-nogit")
    other.mkdir()
    (other / "build.gradle").write_text("group 'x'\n")
    try:
        with pytest.raises(GitError):
            scan_against_base(str(other), "main")
    finally:
        shutil.rmtree(other)


def test_base_and_fix_cannot_be_combined(repo):
    assert main([str(repo), "--base", "base", "--fix"]) == 2
