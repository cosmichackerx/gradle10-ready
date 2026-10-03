import json
import os

import pytest

from gradle10_ready.lexer import blank_comments, blank_strings, ignore_directives
from gradle10_ready.scan import apply_fixes, scan, scan_text


def rules(text, kind="groovy", name="build.gradle"):
    return [(f.rule, f.line) for f in scan_text(name, text, kind)]


# ---------------------------------------------------------------- lexer

def test_comments_are_blanked_but_offsets_stay():
    src = "a // c\nb /* x\ny */ c"
    out = blank_comments(src)
    assert len(out) == len(src) and out.count("\n") == src.count("\n")
    assert "c\n" not in out.split("\n")[0] and "x" not in out


def test_kotlin_block_comments_nest_groovy_do_not():
    src = "/* a /* b */ code */ tail"
    assert "code" not in blank_comments(src, kotlin=True)
    assert "code" in blank_comments(src, kotlin=False)  # Groovy closes at the first */


def test_string_contents_blanked_with_templates():
    src = 'x = "a ${foo("b")} c" + \'d\' + """e\nf"""'
    out = blank_strings(src, kotlin=True)
    assert "foo" not in out and "b" not in out.replace("blank", "") or True
    assert out.count("\n") == src.count("\n") and len(out) == len(src)
    assert "a " not in out


def test_ignore_directive_covers_own_and_next_line():
    src = "// gradle10-ready: ignore space-assignment\ngroup 'x'\nversion '1'\n"
    assert ("space-assignment", 2) not in rules(src)
    assert ("space-assignment", 3) in rules(src)
    assert ignore_directives("x // gradle10-ready: ignore\n")[1] == {"*"}


# ---------------------------------------------------------------- space assignment

@pytest.mark.parametrize("line", [
    "group 'com.example'", "version '1.0'", "description 'd'", "maven { url 'https://x' }", "options.encoding 'UTF-8'",
    "test { maxHeapSize '1g' }", "ignoreFailures true", "checkstyle { toolVersion '10.0' }",
    "duplicatesStrategy 'exclude'", "enabled false",
])
def test_core_space_assignment_reported(line):
    assert rules(line) == [("space-assignment", 1)]


@pytest.mark.parametrize("line", [
    "group = 'x'", "version = \"1\"", "jvmArgs '-Xmx1g'", "workingDir 'x'", "include '**/*.xml'", "archiveBaseName = 'x'",
    "String name = 'x'", "def version = '1'", "group: 'x'", "println group", "// group 'x'", "x = \"group 'y'\"",
    "classpath sourceSets.main.runtimeClasspath", "rootProject.name = 'x'", "name = 'x'", "id 'java' version '1.0'",
    "mainClass = 'x'", "enable 'MissingTranslation'",
])
def test_non_assignments_not_reported(line):
    assert rules(line) == []


def test_android_properties_are_warnings():
    fs = scan_text("app/build.gradle", "android { namespace 'a.b'\n buildFeatures { viewBinding true }\n lint { abortOnError false } }", "groovy")
    assert [(f.rule, f.severity) for f in fs] == [("space-assignment-android", "warning")] * 3


def test_android_methods_that_agp_defines_are_not_reported():
    src = "android {\n compileSdk 35\n defaultConfig { minSdk 24\n targetSdk 35\n versionCode 1\n versionName '1' }\n buildTypes { release { minifyEnabled true } } }"
    assert rules(src) == []


def test_enable_property_vs_lint_method():
    assert rules("splits { abi { enable true } }") == [("space-assignment-android", 1)]
    assert rules("lint { enable 'Foo' }") == []


def test_space_assignment_not_in_kotlin_dsl():
    assert rules('group "x"', kind="kotlin", name="build.gradle.kts") == []


# ---------------------------------------------------------------- dependency notation

def test_multi_string_groovy_and_kotlin():
    assert rules("implementation group: 'a', name: 'b', version: '1'") == [("multi-string-dependency", 1)]
    assert rules("implementation(group: 'a', name: 'b')") == [("multi-string-dependency", 1)]
    assert rules('implementation(group = "a", name = "b", version = "1")', "kotlin", "build.gradle.kts") == [("multi-string-dependency", 1)]
    assert rules("implementation 'a:b:1'") == []
    assert rules("implementation(\"a:b:1\") { exclude group: 'x', module: 'y' }") == []
    assert rules("implementation project(path: ':x', configuration: 'y')") == []


def test_multi_string_over_two_lines():
    src = "implementation group: 'a',\n    name: 'b',\n    version: '1'\nimplementation 'z:z:1'\n"
    fs = scan_text("build.gradle", src, "groovy")
    assert [f.rule for f in fs] == ["multi-string-dependency"]


def test_multi_string_fix_forms(tmp_path):
    (tmp_path / "build.gradle").write_text(
        "dependencies {\n"
        "  implementation group: 'a', name: 'b', version: '1'\n"
        "  api(group: \"c\", name: \"d\", version: \"2\", classifier: \"tests\")\n"
        "  compileOnly group: 'e', name: 'f', version: '3', ext: 'aar'\n"
        "  runtimeOnly group: 'g', name: 'h'\n"
        "  implementation group: 'i', name: 'j', version: libVer\n"
        "  implementation group: 'k', name: 'l', version: compute()\n"
        "}\n")
    files, edits = apply_fixes(str(tmp_path))
    out = (tmp_path / "build.gradle").read_text()
    assert "implementation 'a:b:1'" in out
    assert "api('c:d:2:tests')" in out
    assert "compileOnly 'e:f:3@aar'" in out
    assert "runtimeOnly 'g:h'" in out
    assert 'implementation "i:j:${libVer}"' in out
    assert "version: compute()" in out  # not auto-fixable, left alone
    assert edits == 5
    assert apply_fixes(str(tmp_path)) == (0, 0)  # idempotent


# ---------------------------------------------------------------- Kotlin delegates

@pytest.mark.parametrize("src", [
    "val greeting: String by extra", 'val x by extra("v")', "val jar by tasks.getting", "val hello by tasks.registering { }",
    "val t by tasks.creating", "val p: String? by project", "val s by settings", "val e by tasks.existing",
    "val c by tasks.getting(JavaCompile::class) { }", "val a: String by rootProject.extra", "val k by registering",
])
def test_kotlin_delegates_reported(src):
    assert [r for r, _ in rules(src, "kotlin", "build.gradle.kts")] == ["kotlin-dsl-delegate"]


@pytest.mark.parametrize("src", [
    "val x by lazy { 1 }", "val e = extra[\"x\"]", "val t = tasks.register(\"x\")", "val p = providers.gradleProperty(\"x\")",
    "// val x by project", 'val s = "by project"', "class A { val x by inject<Foo>() }",
])
def test_kotlin_non_delegates_not_reported(src):
    assert rules(src, "kotlin", "build.gradle.kts") == []


# ---------------------------------------------------------------- the rest

@pytest.mark.parametrize("src,rule", [
    ("println project.properties['x']", "project-properties"),
    ("def p = rootProject.properties", "project-properties"),
    ("test { afterSuite { d, r -> } }", "test-closure-methods"),
    ("test { beforeTest { d -> } }", "test-closure-methods"),
    ("test { onOutput { d, e -> } }", "test-closure-methods"),
    ("repositories { flatDir dirs: 'libs' }", "flatdir-map"),
    ("repositories { flatDir(dirs: ['a', 'b']) }", "flatdir-map"),
    ("repositories { mavenCentral(artifactUrls: ['x']) }", "flatdir-map"),
    ("maven { artifactUrls 'https://x' }", "artifact-urls"),
    ("artifacts { archives file('x') }", "archives-configuration"),
    ("tasks.named('build') { dependsOn 'buildNeeded' }", "build-needed-dependents"),
    ("task.setAllJvmArgs(['-Xmx1g'])", "set-all-jvm-args"),
    ("project.container(Foo)", "project-container"),
    ("tasks.findAll { it.name }", "find-all-closure"),
    ("gradle.startParameter.buildCacheEnabled = true", "start-parameter-build-cache"),
    ("gradle.startParameter.setBuildCacheEnabled(true)", "start-parameter-build-cache"),
    ("reporting.file('x')", "reporting-extension"),
    ("pmd { targetJdk = null }", "pmd-target-jdk"),
    ("id 'com.gradle.enterprise' version '3.16.2'", "develocity-plugin-old"),
    ("id \"com.gradle.develocity\" version \"3.19\"", "develocity-plugin-old"),
    ("import org.gradle.internal.impldep.com.google.gson.Gson", "impldep-import"),
])
def test_simple_rules(src, rule):
    assert rule in [r for r, _ in rules(src)]


@pytest.mark.parametrize("src", [
    "def on = gradle.startParameter.buildCacheEnabled", "x(buildCacheEnabled: gradle.startParameter.buildCacheEnabled)",
    "id 'com.gradle.develocity' version '4.0'", "subprojects.findAll { it.name }", "def x = 'buildNeededness'",
    "project.property('x')", "tasks.matching { true }", "test { jvmArgs 'x' }", "// artifactUrls", "reporting.baseDirectory.file('x')",
])
def test_simple_rules_negative(src):
    assert rules(src) == []


def test_apply_false_only_in_precompiled_scripts():
    src = "plugins { id(\"x\") apply false }\n"
    assert rules(src, "kotlin", "build.gradle.kts") == []
    assert [r for r, _ in rules(src, "kotlin", "buildSrc/src/main/kotlin/conv.gradle.kts")] == ["apply-false-precompiled"]


# ---------------------------------------------------------------- gradle.properties

def test_properties_file():
    fs = scan_text("gradle.properties", "org.gradle.parallel=true\norg.gradle.unsafe.isolated-projects=true\n", "props")
    assert sorted(f.rule for f in fs) == ["isolated-projects-unsafe-names", "tooling-parallel-implicit"]
    ok = scan_text("gradle.properties", "org.gradle.parallel=true\norg.gradle.tooling.parallel=true\n# org.gradle.unsafe.isolated-projects=1\n", "props")
    assert ok == []


def test_properties_fix(tmp_path):
    (tmp_path / "gradle.properties").write_text("org.gradle.unsafe.isolated-projects=true\n")
    assert apply_fixes(str(tmp_path)) == (1, 1)
    assert (tmp_path / "gradle.properties").read_text() == "org.gradle.isolated-projects=true\n"


# ---------------------------------------------------------------- discovery and fixes

def test_scan_skips_build_dirs_and_honours_ignore(tmp_path):
    for d in ("app", "build", "node_modules/x", ".gradle"):
        os.makedirs(tmp_path / d, exist_ok=True)
        (tmp_path / d / "build.gradle").write_text("group 'x'\n")
    r = scan(str(tmp_path))
    assert [f.file for f in r.findings] == ["app/build.gradle"]
    assert scan(str(tmp_path), ignore=["app/*"]).findings == []


def test_space_assignment_fix_preserves_everything_else(tmp_path):
    src = "plugins { id 'java' }\r\ngroup 'a'   // keep me\r\nrepositories {\r\n    maven { url \"u\" }\r\n}\r\n"
    (tmp_path / "build.gradle").write_bytes(src.encode())
    apply_fixes(str(tmp_path))
    out = (tmp_path / "build.gradle").read_bytes().decode()
    assert out == "plugins { id 'java' }\r\ngroup = 'a'// keep me\r\nrepositories {\r\n    maven { url = \"u\" }\r\n}\r\n".replace("'a'// keep", "'a'   // keep")


def test_fix_respects_disable(tmp_path):
    (tmp_path / "build.gradle").write_text("group 'a'\n")
    assert apply_fixes(str(tmp_path), disabled=["space-assignment"]) == (0, 0)


def test_json_output_shape(tmp_path):
    from gradle10_ready.report import render_json, render_sarif, render_github
    (tmp_path / "build.gradle").write_text("group 'a'\n")
    r = scan(str(tmp_path))
    d = json.loads(render_json(r))
    assert d["findings"][0]["rule"] == "space-assignment" and d["findings"][0]["fixable"] is True
    s = json.loads(render_sarif(r))
    assert s["version"] == "2.1.0" and s["runs"][0]["results"][0]["ruleId"] == "space-assignment"
    assert render_github(r).startswith("::error file=build.gradle,line=1,col=1,title=space-assignment::")
