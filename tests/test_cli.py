import json
from gradle10_ready.cli import main
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")


def run(*args, cwd=None):
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.run([sys.executable, "-m", "gradle10_ready", *args], cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True)


def test_exit_codes_and_fail_on(tmp_path):
    (tmp_path / "build.gradle").write_text("group 'a'\n")
    assert run(str(tmp_path)).returncode == 1
    assert run(str(tmp_path), "--fail-on", "never").returncode == 0
    (tmp_path / "build.gradle").write_text("android { namespace 'a' }\n")  # warning only
    assert run(str(tmp_path)).returncode == 0
    assert run(str(tmp_path), "--fail-on", "warning").returncode == 1


def test_clean_project(tmp_path):
    (tmp_path / "build.gradle").write_text("group = 'a'\n")
    p = run(str(tmp_path))
    assert p.returncode == 0 and "No Gradle 10 findings." in p.stdout


def test_fix_then_clean(tmp_path):
    (tmp_path / "build.gradle").write_text("group 'a'\nversion '1'\n")
    p = run(str(tmp_path), "--fix")
    assert p.returncode == 0 and "fixed 2 place(s) in 1 file(s)" in p.stderr
    assert (tmp_path / "build.gradle").read_text() == "group = 'a'\nversion = '1'\n"


def test_list_rules_and_version():
    p = run("--list-rules")
    assert p.returncode == 0 and "space-assignment" in p.stdout and "kotlin-dsl-delegate" in p.stdout
    assert run("--version").stdout.startswith("gradle10-ready ")


def test_unknown_rule_is_a_usage_error(tmp_path):
    assert run(str(tmp_path), "--disable", "nope").returncode == 2


def test_output_file(tmp_path):
    (tmp_path / "build.gradle").write_text("group 'a'\n")
    out = tmp_path / "r.sarif"
    run(str(tmp_path), "-f", "sarif", "-o", str(out), "--fail-on", "never")
    assert '"version": "2.1.0"' in out.read_text()


def test_several_files_keep_the_path_they_were_given(tmp_path, capsys):
    (tmp_path / "app").mkdir()
    (tmp_path / "build.gradle").write_text("group 'x'\n")
    (tmp_path / "app" / "build.gradle").write_text("version '1'\n")
    (tmp_path / "ok.gradle").write_text("group = 'x'\n")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert main(["build.gradle", "app/build.gradle", "ok.gradle", "-f", "json"]) == 1
    finally:
        os.chdir(cwd)
    d = json.loads(capsys.readouterr().out)
    assert sorted(f["file"] for f in d["findings"]) == ["app/build.gradle", "build.gradle"]
    assert d["filesScanned"] == 3


def test_fix_accepts_several_files(tmp_path):
    a, b = tmp_path / "a.gradle", tmp_path / "b.gradle"
    a.write_text("group 'x'\n")
    b.write_text("version '1'\n")
    assert main([str(a), str(b), "--fix"]) == 0
    assert a.read_text() == "group = 'x'\n" and b.read_text() == "version = '1'\n"
