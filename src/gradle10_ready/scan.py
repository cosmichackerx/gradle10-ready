"""File discovery and the rule detectors."""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field

from .lexer import blank_comments, blank_strings, ignore_directives
from .rules import RULES

SKIP_DIRS = {".git", ".gradle", ".idea", "build", "out", "node_modules", ".kotlin", ".svn", "dist", "target"}

# Gradle core properties, each confirmed to raise the space-assignment deprecation on Gradle 8.14.3 (see tests/oracle).
# Lazy Property<T> types (archiveBaseName, mainClass, destinationDirectory, ...) have no generated method and are not listed.
CORE_PROPS = (
    "url name group version description applicationName sourceCompatibility targetCompatibility enabled ignoreFailures "
    "showViolations toolVersion allowInsecureProtocol destinationDir main ignoreExitValue maxParallelForks forkEvery "
    "followSymlinks username password maxHeapSize minHeapSize debug enableAssertions failFast showStandardStreams "
    "exceptionFormat encoding incremental failOnError zip64 duplicatesStrategy includeEmptyDirs dirMode standardOutput"
).split()
# Android Gradle Plugin DSL properties confirmed on AGP 8.13.2 / Gradle 8.14.3 (tests/oracle/android). Warning level: the list
# depends on the AGP version. compileSdk, minSdk, targetSdk, versionCode, versionName, applicationId, minifyEnabled, debuggable,
# storeFile and friends have explicit methods in AGP and are NOT deprecated, so they are not listed.
ANDROID_PROPS = (
    "namespace ndkVersion multiDexEnabled useSupportLibrary shrinkResources signingConfig coreLibraryDesugaringEnabled "
    "useLegacyPackaging enable universalApk buildConfig viewBinding dataBinding abortOnError checkReleaseBuilds "
    "warningsAsErrors ignoreWarnings checkDependencies htmlReport xmlReport sarifReport textReport showAll absolutePaths "
    "lintConfig baseline htmlOutput xmlOutput sarifOutput textOutput includeAndroidResources"
).split()
_CORE = "|".join(sorted(set(CORE_PROPS), key=len, reverse=True))
_ANDROID = "|".join(sorted(set(ANDROID_PROPS) - set(CORE_PROPS), key=len, reverse=True))
_SPACE = re.compile(r"(?:^|[{;])[ \t]*(?P<prefix>(?:[A-Za-z_]\w*\.)*)(?P<name>%s)(?P<ws>[ \t]+)(?=(?P<val>[\"'\w$\[!(-]))" , re.M)
_KEYWORDS = {"in", "as", "instanceof", "and", "or", "not", "is"}

_BLOCK_START = re.compile(r"[{;]")


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    col: int
    message: str
    snippet: str
    edit: tuple | None = None  # (start, end, replacement) in the original file text

    @property
    def url(self) -> str:
        return RULES[self.rule].url


@dataclass
class Result:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    fixed: int = 0
    pr: dict | None = None  # set in PR mode (--base): {base, existing, resolved}


def kind_of(name: str):
    if name.endswith(".gradle.kts"):
        return "kotlin"
    if name.endswith(".gradle"):
        return "groovy"
    if name == "gradle.properties":
        return "props"
    return None


def discover(root: str, ignore: list):
    root = os.path.abspath(root)
    if os.path.isfile(root):
        yield root, os.path.basename(root)
        return
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        for fn in sorted(fns):
            if kind_of(fn) is None:
                continue
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(fn, g) for g in ignore):
                continue
            yield full, rel


class Ctx:
    def __init__(self, rel: str, text: str, kind: str):
        self.rel, self.text, self.kind = rel, text, kind
        self.kotlin = kind == "kotlin"
        self.code = blank_comments(text, self.kotlin) if kind != "props" else text
        self.nostr = blank_strings(text, self.kotlin) if kind != "props" else text
        self.out: list = []

    def line(self, off: int) -> int:
        return self.text.count("\n", 0, off) + 1

    def snippet(self, off: int) -> str:
        s = self.text.rfind("\n", 0, off) + 1
        e = self.text.find("\n", off)
        return self.text[s:e if e >= 0 else len(self.text)].strip()[:160]

    def add(self, rule: str, off: int, message: str | None = None, edit=None):
        r = RULES[rule]
        ln = self.line(off)
        col = off - (self.text.rfind("\n", 0, off) + 1) + 1
        self.out.append(Finding(rule, r.severity, self.rel, ln, col, message or r.summary, self.snippet(off), edit))


# ---------------------------------------------------------------- detectors

def space_assignment(c: Ctx):
    if c.kind != "groovy":
        return
    for rule, names in (("space-assignment", _CORE), ("space-assignment-android", _ANDROID)):
        if not names:
            continue
        pat = re.compile(_SPACE.pattern.replace("%s", names), re.M)
        for m in pat.finditer(c.nostr):
            name, prefix = m.group("name"), m.group("prefix")
            # `id 'x' version '1'` style: the property name must start the statement, which the regex enforces.
            rest = c.nostr[m.end("ws"):m.end("ws") + 12]
            word = re.match(r"[A-Za-z_]+", rest)
            if word and word.group(0) in _KEYWORDS:
                continue
            if name == "enable" and not re.match(r"(?:true|false|\()", rest):
                continue  # lint { enable 'Issue' } is a real method, abi { enable true } is the property
            start = m.start("prefix")
            ws_s, ws_e = m.start("ws"), m.end("ws")
            c.add(rule, start, f"`{prefix}{name} ...` is Gradle's generated space-assignment; write `{prefix}{name} = ...`.",
                  edit=(ws_s, ws_e, " = "))


_DEP_CONF = re.compile(r"(?<![\w.])(?P<conf>[A-Za-z_]\w*)[ \t]*\(?[ \t]*(?=(?:group|name)\b[ \t]*(?::|=)(?!=))")


def _split_args(s: str):
    """Split `a: 'x', b: y` on top-level commas, stopping at the end of the argument list."""
    parts, depth, cur, i = [], 0, "", 0
    q = None
    after_comma = False
    while i < len(s):
        ch = s[i]
        if q:
            cur += ch
            if ch == "\\":
                cur += s[i + 1:i + 2]
                i += 1
            elif ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch in "([{":
            depth += 1
            cur += ch
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
            cur += ch
        elif ch == "\n" and depth == 0:
            # a newline ends the list unless it directly follows a comma
            if after_comma:
                cur += ch
            else:
                break
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
            after_comma = True
            i += 1
            continue
        else:
            cur += ch
        if not ch.isspace():
            after_comma = False
        i += 1
    if cur.strip():
        parts.append(cur)
    return parts, i


def multi_string(c: Ctx):
    sep = r"=" if c.kotlin else r":"
    for m in _DEP_CONF.finditer(c.code):
        conf = m.group("conf")
        if conf in {"exclude", "project", "files", "fileTree", "module", "mapOf", "listOf", "dependencySubstitution", "substitute", "force", "capabilities"} and conf != "module":
            continue
        args_start = m.end()
        parts, used = _split_args(c.code[args_start:])
        kv = {}
        for p in parts:
            mm = re.match(r"\s*(\w+)\s*" + sep + r"(?!=)\s*(.+?)\s*$", p, re.S)
            if not mm:
                kv = None
                break
            kv[mm.group(1)] = mm.group(2)
        if not kv or "group" not in kv or "name" not in kv:
            continue
        if conf == "module" and not c.kotlin:
            pass
        end = args_start + used
        edit = None
        coords = _coords(kv, c.kotlin)
        if coords is not None:
            has_paren = c.code[m.start("conf") + len(conf):args_start].strip().startswith("(") or c.code[args_start - 1:args_start] == "("
            # replace only the argument text; keep the configuration name and an existing parenthesis
            edit = (args_start, end, coords)
        c.add("multi-string-dependency", m.start("conf"),
              f"`{conf}` uses named/map dependency notation; use the single string `group:name:version`." + ("" if edit else " (not auto-fixable: values are not plain literals)"),
              edit=edit)


_STR = re.compile(r"""^(["'])(.*)\1$""", re.S)
_EXPR = re.compile(r"^[A-Za-z_][\w.]*$")


def _coords(kv: dict, kotlin: bool):
    allowed = {"group", "name", "version", "classifier", "ext"}
    if not set(kv) <= allowed:
        return None
    parts, dynamic = {}, False
    for k, v in kv.items():
        v = v.strip()
        sm = _STR.match(v)
        if sm:
            body = sm.group(2)
            if sm.group(1) == '"' and "$" in body:
                dynamic = True
            if "\n" in body or "\\" in body or ((sm.group(1) == "'" or not kotlin) and False):
                return None
            parts[k] = body
        elif _EXPR.match(v):
            parts[k] = "${" + v + "}"
            dynamic = True
        else:
            return None
    if "version" not in parts and ("classifier" in parts or "ext" in parts):
        return None
    s = parts["group"] + ":" + parts["name"]
    if "version" in parts:
        s += ":" + parts["version"]
    if "classifier" in parts:
        s += ":" + parts["classifier"]
    if "ext" in parts:
        s += "@" + parts["ext"]
    if dynamic or kotlin:
        if '"' in s.replace("${", ""):
            return None
        return '"' + s + '"'
    if "'" in s:
        return None
    return "'" + s + "'"


_CONTAINER_METHOD = {"registering": "register", "creating": "create", "existing": "named", "getting": "getByName"}
_VAL_BEFORE = re.compile(r"^(?P<indent>[ \t]*)(?:(?:private|internal|public)[ \t]+)?val[ \t]+(?P<name>\w+)(?:[ \t]*:[ \t]*(?P<type>[\w.]+(?:<[\w.<>, ?]*>)?\??))?[ \t]+$")
_TYPE_ARG = re.compile(r"[ \t]*\([ \t]*(?P<t>[A-Za-z_][\w.]*)::class[ \t]*\)")


def _delegate_fix(c: Ctx, by: int, kind: str, recv: str, end: int):
    """(start, end, replacement) for `val x [: T] by <delegate>` when the rewrite from the Gradle upgrade guide is mechanical, else None.
    `by` is the offset of the keyword, `end` the end of the delegate name; only single-line `val` declarations are rewritten."""
    ls = c.text.rfind("\n", 0, by) + 1
    m = _VAL_BEFORE.match(c.code[ls:by])
    if not m:
        return None
    name, typ = m.group("name"), m.group("type")
    if kind in _CONTAINER_METHOD:
        if typ or not recv:
            return None  # a type annotation or an implicit receiver: leave it to a human
        if kind == "creating" and recv.split(".")[-1] == "tasks":
            return None  # TaskContainer.create(name, Action) is itself deprecated in Gradle 9 (Kotlin compiler warning); register vs create is a human decision
        t = _TYPE_ARG.match(c.code, end)
        targ = ""
        if t:
            targ, end = "<%s>" % t.group("t"), t.end()
        return (by, end, '= %s.%s%s("%s")' % (recv, _CONTAINER_METHOD[kind], targ, name))
    nxt = c.code[end:end + 1]
    if kind == "project" and not recv and typ and nxt not in ("(", "."):
        call = "findProperty" if typ.endswith("?") else "property"
        return (by, end, '= project.%s("%s") as %s' % (call, name, typ))
    if kind == "extra":
        access = (recv + "." if recv else "") + "extra"
        if typ and nxt not in ("(", "{", "."):
            return (by, end, '= %s["%s"] as %s' % (access, name, typ))
        if not typ and nxt == "(":
            close, depth = None, 0
            for i in range(end, len(c.code)):
                ch = c.code[i]
                if ch == "\n":
                    break
                depth += ch == "("
                depth -= ch == ")"
                if depth == 0:
                    close = i
                    break
            rest_end = c.code.find("\n", close if close else 0)
            rest = c.code[(close or 0) + 1:rest_end if rest_end >= 0 else len(c.code)]
            expr = c.text[end + 1:close].strip() if close else ""
            if close and expr and not rest.strip():
                return (ls + len(m.group("indent")), close + 1,
                        'val %s = %s\n%s%s["%s"] = %s' % (name, expr, m.group("indent"), access, name, name))
    return None


def kotlin_delegates(c: Ctx):
    if not c.kotlin:
        return
    pats = [
        (r"\bby\s+(?P<recv>(?:[\w]+\.)*?)(?P<kind>registering|creating|existing|getting)\b", "container"),
        (r"\bby\s+(?:(?:rootProject|parent)\.)?(?P<kind>project|settings|extensions)\b", "property"),
        (r"\bby\s+(?P<recv>(?:[\w]+\.)*?)(?P<kind>extra)\b", "extra"),
    ]
    seen = set()
    for pat, _ in pats:
        for m in re.finditer(pat, c.nostr):
            if m.start() in seen:
                continue
            seen.add(m.start())
            word = m.group("kind")
            recv = (m.groupdict().get("recv") or "").rstrip(".")
            edit = None
            if not (word in ("project", "settings", "extensions") and re.match(r"by\s+(?:rootProject|parent)\.", m.group(0))):
                edit = _delegate_fix(c, m.start(), word, recv, m.end())
            c.add("kotlin-dsl-delegate", m.start(), f"Kotlin DSL delegate `by {word}` is removed in Gradle 10; use the explicit API.", edit=edit)


def simple_patterns(c: Ctx):
    if c.kind == "props":
        return
    N, K = c.nostr, c.code
    def each(pattern, text, rule, msg=None):
        for m in re.finditer(pattern, text):
            c.add(rule, m.start(), msg)
    each(r"(?<![\w.])(?:project|rootProject|getProject\(\))\s*\.\s*(?:properties\b|getProperties\s*\()", N, "project-properties")
    if not c.kotlin:
        each(r"(?<![\w$.])(?:beforeTest|afterTest|beforeSuite|afterSuite|onOutput)\s*(?:\(\s*)?\{", N, "test-closure-methods")
    each(r"\bflatDir\s*\(?\s*(?:\[\s*)?dirs\s*:", K, "flatdir-map")
    each(r"\bmavenCentral\s*\(\s*(?:artifactUrls|name)\s*:", K, "flatdir-map")
    each(r"\bartifactUrls\b", N, "artifact-urls")
    each(r"\bartifacts\s*\{[^{}]*?\barchives\b", K, "archives-configuration")
    each(r"\bartifacts\s*\.\s*add\s*\(\s*[\"']archives[\"']", K, "archives-configuration")
    for m in re.finditer(r"\b(buildNeeded|buildDependents)\b", K):
        c.add("build-needed-dependents", m.start(), f"`{m.group(1)}` is removed in Gradle 10.")
    each(r"\bsetAllJvmArgs\b|\ballJvmArgs\s*=(?!=)", N, "set-all-jvm-args")
    each(r"(?<![\w.])(?:project|getProject\(\))\s*\.\s*container\s*\(", N, "project-container")
    each(r"\b(?:tasks|configurations|sourceSets|repositories|components)\s*\.\s*findAll\b", N, "find-all-closure")
    each(r"\bstartParameter\s*\.\s*(?:buildCacheEnabled\s*=(?!=)|setBuildCacheEnabled\s*\()", N, "start-parameter-build-cache")
    each(r"\breporting\s*\.\s*file\s*\(", N, "reporting-extension")
    each(r"(?<![\w.])(?:targetJdk|setTargetJdk)\b", N, "pmd-target-jdk")
    each(r"\borg\.gradle\.internal\.impldep\b", N, "impldep-import")
    # precompiled script plugins live in src/main/{kotlin,groovy}
    if re.search(r"/src/main/(?:kotlin|groovy)/", "/" + c.rel):
        each(r"(?<![\w.])apply\s+false\b|\.apply\s*\(\s*false\s*\)", N, "apply-false-precompiled")
    # Develocity / Gradle Enterprise plugin before 4.0, literal versions only
    for m in re.finditer(r"""["']com\.gradle\.(?:develocity|enterprise)["']\s*\)?\s*version\s*\(?\s*["'](\d+)\.""", K):
        if int(m.group(1)) < 4:
            c.add("develocity-plugin-old", m.start())


def properties_file(c: Ctx):
    if c.kind != "props":
        return
    lines = c.text.split("\n")
    keys = {}
    off = 0
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith(("#", "!")):
            m = re.match(r"([^=:\s]+)\s*[=:]\s*(.*)$", s)
            if m:
                keys[m.group(1)] = (m.group(2).strip(), off + ln.index(m.group(1)))
        off += len(ln) + 1
    for k, (v, o) in keys.items():
        if k.startswith("org.gradle.unsafe.isolated-projects"):
            new = k.replace(".unsafe", "", 1)
            c.add("isolated-projects-unsafe-names", o, f"`{k}` is deprecated; use `{new}`.", edit=(o, o + len(k), new))
    if keys.get("org.gradle.parallel", ("", 0))[0].lower() == "true" and "org.gradle.tooling.parallel" not in keys:
        c.add("tooling-parallel-implicit", keys["org.gradle.parallel"][1])


DETECTORS = [space_assignment, multi_string, kotlin_delegates, simple_patterns, properties_file]


def scan_text(rel: str, text: str, kind: str, disabled=frozenset(), only=frozenset()):
    c = Ctx(rel, text, kind)
    for d in DETECTORS:
        d(c)
    ign = ignore_directives(text, c.kotlin) if kind != "props" else {}
    res = []
    for f in c.out:
        if f.rule in disabled or (only and f.rule not in only):
            continue
        s = ign.get(f.line, set())
        if "*" in s or f.rule in s:
            continue
        res.append(f)
    res.sort(key=lambda f: (f.line, f.col, f.rule))
    # one finding per (rule, position)
    seen, uniq = set(), []
    for f in res:
        k = (f.rule, f.line, f.col)
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def scan(root: str, ignore=(), disabled=(), only=()) -> Result:
    r = Result()
    for full, rel in discover(root, list(ignore)):
        try:
            with open(full, encoding="utf-8", errors="replace", newline="") as fh:
                text = fh.read()
        except OSError:
            continue
        r.files_scanned += 1
        r.findings += scan_text(rel, text, kind_of(os.path.basename(full)), frozenset(disabled), frozenset(only))
    return r


def apply_fixes(root: str, ignore=(), disabled=(), only=()) -> tuple:
    """Rewrite files in place. Returns (files_changed, edits_applied)."""
    files = edits = 0
    for full, rel in discover(root, list(ignore)):
        with open(full, encoding="utf-8", errors="replace", newline="") as fh:
            text = fh.read()
        fs = [f for f in scan_text(rel, text, kind_of(os.path.basename(full)), frozenset(disabled), frozenset(only)) if f.edit]
        if not fs:
            continue
        spans = sorted({f.edit for f in fs}, reverse=True)
        last = None
        n = 0
        for s, e, rep in spans:
            if last is not None and e > last:
                continue  # overlapping edits: leave for the next run
            text = text[:s] + rep + text[e:]
            last = s
            n += 1
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        files += 1
        edits += n
    return files, edits
