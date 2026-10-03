import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("watch", os.path.join(ROOT, "scripts", "watch", "watch_upgrade_guide.py"))
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "guide", "upgrading_version_9.html")
HTML = open(FIXTURE, encoding="utf-8").read()


def test_parse_deprecations_only_under_deprecation_sections():
    items = watch.parse_deprecations(HTML)
    anchors = {i["anchor"] for i in items}
    assert len(items) == 54
    assert "deprecated_get_properties" in anchors
    assert "kotlin_2_4_10" not in anchors  # a "Potential breaking changes" item
    assert "dependency_resolution_ordering" not in anchors  # a "Feature previews" item
    by = {i["anchor"]: i for i in items}
    assert by["deprecated_get_properties"]["release"] == "9.6.0"
    assert by["deprecated_macos_amd64"]["release"] == "9.8.0"


def test_every_rule_anchor_exists_in_the_guide():
    assert watch.stale_anchors(HTML, watch.rule_anchors()) == []


def test_baseline_is_complete_so_first_run_opens_nothing():
    res = watch.run(HTML, 404, "[]")
    assert res["new"] == [] and res["signals"] == [] and res["title"] == ""
    assert res["total"] == res["covered_by_rules"] + res["triaged"]


def test_new_deprecation_is_reported_with_stable_key():
    html = HTML.replace("</body>", '<h3 id="v9_deprecations_9_9">Deprecations</h3>'
                        '<h4 id="deprecate_shiny">Deprecation of shiny()</h4></body>')
    res = watch.run(html, 404, "[]")
    assert [i["anchor"] for i in res["new"]] == ["deprecate_shiny"]
    assert "deprecate_shiny" in res["body"] and res["title"].startswith("Gradle upgrade guide: 1 new")
    again = watch.run(html, 404, "[]")
    assert again["title"] == res["title"]  # same input, same dedupe key


def test_triaging_an_anchor_silences_it(tmp_path):
    html = HTML.replace("</body>", '<h3 id="deprecations_10">Deprecations</h3>'
                        '<h4 id="deprecate_shiny">Deprecation of shiny()</h4></body>')
    t = tmp_path / "t.txt"
    t.write_text("deprecate_shiny  # no rule: purely internal\n# comment\n")
    res = watch.run(html, 404, "[]", triaged_path=str(t))
    assert all(i["anchor"] != "deprecate_shiny" for i in res["new"])


def test_stale_rule_anchor_is_a_signal():
    html = HTML.replace('id="deprecated_get_properties"', 'id="renamed_get_properties"')
    res = watch.run(html, 404, "[]")
    assert res["stale"] == ["deprecated_get_properties"]
    assert any("deprecated_get_properties" in s for s in res["signals"])
    assert any(i["anchor"] == "renamed_get_properties" for i in res["new"])


def test_gradle10_signals():
    assert watch.gradle10_signals(404, json.dumps([{"version": "9.8.0"}])) == []
    s = watch.gradle10_signals(200, json.dumps([{"version": "10.0-milestone-1"}, {"version": "9.8.0"}]))
    assert len(s) == 2 and "10.0-milestone-1" in s[1]
    assert watch.gradle10_signals(404, "not json") == []


def test_cli_exit_codes(tmp_path, capsys):
    assert watch.main(["--html", FIXTURE, "--offline"]) == 0
    empty = tmp_path / "e.html"
    empty.write_text("<html></html>")
    assert watch.main(["--html", str(empty), "--offline"]) == 2
    out = tmp_path / "o.json"
    html = tmp_path / "n.html"
    html.write_text(HTML.replace("</body>", '<h3 id="deprecations_30">Deprecations</h3><h4 id="zzz">Deprecation of zzz</h4></body>'))
    assert watch.main(["--html", str(html), "--offline", "--out", str(out)]) == 3
    assert json.loads(out.read_text())["new"][0]["anchor"] == "zzz"
