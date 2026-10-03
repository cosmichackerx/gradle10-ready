#!/usr/bin/env python3
"""Run real Gradle on an oracle project and compare its deprecation warnings with gradle10-ready.

usage: run_oracle.py PROJECT_DIR BUILD_FILE [--gradle gradle]

Gradle prints `Build file '...': line N`, the message and a link ending in `#anchor`. gradle10-ready's rules cite the same
anchors. The check passes when, for every anchor that gradle10-ready knows, the set of (line, anchor) pairs is identical:
nothing Gradle warns about is missed, and nothing is reported that Gradle does not warn about.
"""
import os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
from gradle10_ready.scan import scan  # noqa: E402


def gradle_warnings(project, build_file, gradle):
    out = subprocess.run([gradle, "help", "--warning-mode", "all", "--no-daemon", "--console=plain"], cwd=project,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600).stdout
    got, line = set(), None
    for ln in out.splitlines():
        m = re.match(r"Build file '.*?%s': line (\d+)" % re.escape(os.path.basename(build_file)), ln)
        if m:
            line = int(m.group(1))
            continue
        a = re.search(r"upgrading_version_\d+\.html#(\S+)", ln)
        if a and line:
            got.add((line, a.group(1)))
            line = None
    return got, out


KOTLIN_RULES = {"kotlin-dsl-delegate", "multi-string-dependency", "project-properties"}


def kotlin_main(project, build_file, gradle):
    """Kotlin DSL: the Kotlin compiler prints `w: file://.../build.gradle.kts:LINE:COL: ... is deprecated` for the same constructs."""
    import tempfile
    # a fresh Gradle user home forces the script to be compiled again, which is when the Kotlin compiler prints its warnings
    home = tempfile.mkdtemp(prefix="g10-home-")
    out = subprocess.run([gradle, "help", "--warning-mode", "all", "--no-daemon", "--console=plain"], cwd=project,
                         env=dict(os.environ, GRADLE_USER_HOME=home), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600).stdout
    shutil.rmtree(home, ignore_errors=True)
    got = {int(m.group(1)) for m in re.finditer(r"^w: file://\S*?%s:(\d+):\d+: .*is deprecated" % re.escape(os.path.basename(build_file)), out, re.M)}
    res = scan(os.path.join(project, build_file), only=KOTLIN_RULES)
    ours = {f.line for f in res.findings}
    print(f"kotlin compiler warned on {len(got)} line(s), gradle10-ready reported {len(ours)}")
    for l in sorted(got - ours):
        print(f"  MISSED   line {l}")
    for l in sorted(ours - got):
        print(f"  EXTRA    line {l}")
    return 1 if got != ours else 0


def fix_check(project, build_file, gradle):
    """Copy the project, run --fix, and check that real Gradle no longer warns about what was fixed and the build still works."""
    import tempfile
    from gradle10_ready.scan import apply_fixes
    from gradle10_ready.rules import RULES
    tmp = tempfile.mkdtemp(prefix="g10-fix-")
    work = os.path.join(tmp, "p")
    shutil.copytree(project, work, ignore=shutil.ignore_patterns(".gradle", "build"))
    files, edits = apply_fixes(work)
    fixable = {r.url.split("#")[1] for r in RULES.values() if r.fixable and r.oracle}
    before, _ = gradle_warnings(project, build_file, gradle)
    after, out = gradle_warnings(work, build_file, gradle)
    left = sorted((l, a) for l, a in after if a in fixable)
    print(f"--fix changed {edits} place(s) in {files} file(s); Gradle warnings on fixable anchors: {len([1 for _, a in before if a in fixable])} before, {len(left)} after")
    for l, a in left:
        print(f"  STILL WARNS  line {l}: {a}")
    ok = "BUILD SUCCESSFUL" in out
    if not ok:
        print("  build no longer succeeds after --fix")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok and not left else 1


def main():
    project, build_file = sys.argv[1], sys.argv[2]
    gradle = sys.argv[sys.argv.index("--gradle") + 1] if "--gradle" in sys.argv else "gradle"
    if "--fix-check" in sys.argv:
        return fix_check(project, build_file, gradle)
    if build_file.endswith(".kts"):
        return kotlin_main(project, build_file, gradle)
    res = scan(os.path.join(project, build_file))
    ours = {(f.line, f.url.split("#")[1]) for f in res.findings} 
    got, out = gradle_warnings(project, build_file, gradle)
    got = {(l, a) for l, a in got if a in KNOWN_ANCHORS}
    ours = {(l, a) for l, a in ours if a in KNOWN_ANCHORS}
    missed, extra = sorted(got - ours), sorted(ours - got)
    print(f"gradle warned {len(got)} (line, anchor) pairs, gradle10-ready reported {len(ours)}")
    for l, a in missed:
        print(f"  MISSED   line {l}: {a}")
    for l, a in extra:
        print(f"  EXTRA    line {l}: {a}")
    return 1 if missed or extra else 0


def _anchors():
    from gradle10_ready.rules import RULES
    return {r.url.split("#")[1] for r in RULES.values() if r.oracle}


KNOWN_ANCHORS = _anchors()

if __name__ == "__main__":
    raise SystemExit(main())
