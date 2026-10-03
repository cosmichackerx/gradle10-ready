# gradle10-ready

**Find what Gradle 10 removes in your build scripts, without running Gradle.** A zero-dependency static scanner (Python 3.9+) for
`build.gradle`, `build.gradle.kts`, `settings.gradle(.kts)` and `gradle.properties`: Groovy *space-assignment* (`url "..."`, `namespace "..."`),
multi-string / map dependency notation (`group: 'x', name: 'y'`), Kotlin DSL *delegated properties* (`val x by extra`, `by tasks.getting`),
`project.properties`, Closure-based test listeners and more. It can **rewrite the mechanical ones for you** (`--fix`), emits **SARIF** and
GitHub annotations, and ships as a **GitHub Action**.

[![CI](https://github.com/cosmichackerx/gradle10-ready/actions/workflows/ci.yml/badge.svg)](https://github.com/cosmichackerx/gradle10-ready/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cosmichackerx/gradle10-ready?sort=semver)](https://github.com/cosmichackerx/gradle10-ready/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Why a static scanner? Gradle already warns about these things when you run `./gradlew --warning-mode all`, but only for code that your
build actually executes, only on a build that still works, and only on the Gradle version you run. This reads the files and finds the
constructs the Gradle 9.x upgrade guide lists as *deprecated, will be removed in Gradle 10*. Most rules are checked against real Gradle in CI
(see [How it is verified](#how-it-is-verified)).

> **Status of Gradle 10:** as of 2026-10-03 the current release I found is Gradle 9.8.0 and there is **no release date for Gradle 10 that I
> could confirm**. This tool tells you how much work the documented removals are; it does not predict when they land.

## At a glance

|  | Lite (try it in a minute) | Full (keep it in CI) |
|---|---|---|
| How | `pipx install git+https://github.com/cosmichackerx/gradle10-ready` then `gradle10-ready .` (read-only; `--fix` is opt-in) | the [GitHub Action](#github-action), the [pre-commit](#pre-commit) hook, [PR mode](#pr-mode-only-what-a-pull-request-introduces) and the weekly [deprecation watch](#deprecation-watch-keeps-the-rule-table-honest) |

### Validation / results

Every number below is from this repository's own tests or scripts (see the linked sections). "Not proven" is as important as "Result".

| What is claimed | Checked against | Size | Result | Not proven |
|---|---|---|---|---|
| It reports the same lines Gradle warns about | Real Gradle: Groovy DSL and Kotlin DSL on 9.8.0, Android on 8.14.3 + AGP 8.13.2 (CI) | Groovy 22 pairs, Kotlin DSL 11 lines, Android 32 pairs | 22/22, 11/11 and 32/32 identical lines (2026-10-03) | Only what I wrote into the three oracle projects; rules marked **docs** are not covered |
| `--fix` stops the warnings | `--fix-check` on the Groovy and Android projects | 2 projects | Gradle no longer warns about fixed lines and the build still succeeds | Mechanical rewrites only |
| Precision on real projects | 100 public Android repositories ([docs/precision.md](docs/precision.md)) | 99 with Gradle files, 64 with a finding; 40 random findings read by hand | all 40 were genuine uses of the flagged construct | The sample was read by the author; popular repositories, not random Gradle builds |
| Recall | - | - | **Not measured** | How many Gradle 10 breakages a real build has that the tool misses |
| Rule logic | Unit tests on Linux, Windows, macOS | 148 tests | green | - |

**Releases:** 4 releases, v0.1.0 to v0.2.2, all published on 2026-10-03 (days old). See [CHANGELOG.md](CHANGELOG.md) and the [Releases page](https://github.com/cosmichackerx/gradle10-ready/releases); the weekly deprecation watch opens an issue when Gradle's deprecation list changes.

## Install and run

```
pipx install git+https://github.com/cosmichackerx/gradle10-ready      # or: pip install git+https://github.com/cosmichackerx/gradle10-ready
gradle10-ready .                    # scan the current project
gradle10-ready . --fix              # apply the mechanical fixes, then report what is left
gradle10-ready . -f sarif -o g10.sarif --fail-on never
```

From a checkout without installing: `PYTHONPATH=src python -m gradle10_ready .`

## Example output

`tests/fixtures/legacy-app` is a small Android project written the way many still are. Real output:

```
app/build.gradle
      6  warning space-assignment-android   `namespace ...` is Gradle's generated space-assignment; write `namespace = ...`.
         > namespace "com.example.app"
     19  warning space-assignment-android   `shrinkResources ...` is Gradle's generated space-assignment; write `shrinkResources = ...`.
         > shrinkResources true
     25  error   multi-string-dependency    `implementation` uses named/map dependency notation; use the single string `group:name:version`.
         > implementation group: 'com.squareup.okhttp3', name: 'okhttp', version: '4.12.0'
     26  error   multi-string-dependency    `implementation` uses named/map dependency notation; use the single string `group:name:version`.
         > implementation(group: 'com.google.guava', name: 'guava', version: '33.0.0-android')
     31  error   space-assignment           `maxHeapSize ...` is Gradle's generated space-assignment; write `maxHeapSize = ...`.
         > maxHeapSize "1g"
     32  error   test-closure-methods       Test task methods taking a Groovy Closure (beforeTest, afterTest, beforeSuite, afterSuite, onOutput) are removed in Gradle 10
         > afterSuite { desc, result -> println "${desc.name}: ${result.resultType}" }
     35  error   project-properties         Project.getProperties() / project.properties is removed in Gradle 10
         > def signing = project.properties['releaseKeyPassword']

build.gradle
      4  error   space-assignment           `url ...` is Gradle's generated space-assignment; write `url = ...`.
         > maven { url "https://jitpack.io" }
      9  error   space-assignment           `group ...` is Gradle's generated space-assignment; write `group = ...`.
         > group 'com.example'
     10  error   space-assignment           `version ...` is Gradle's generated space-assignment; write `version = ...`.
         > version '1.0'

gradle.properties
      2  warning tooling-parallel-implicit  org.gradle.parallel=true without org.gradle.tooling.parallel: the implicit link is an error in Gradle 10 during IDE model building
         > org.gradle.parallel=true
      3  warning isolated-projects-unsafe-names `org.gradle.unsafe.isolated-projects` is deprecated; use `org.gradle.isolated-projects`.
         > org.gradle.unsafe.isolated-projects=false

4 Gradle file(s) scanned. 8 error, 4 warning; 9 auto-fixable with --fix.
```

`--fix` rewrites the 9 fixable places (space-assignment, multi-string notation, renamed `gradle.properties` keys), leaves the rest for a human,
and a re-run then reports `2 error, 1 warning`:

```diff
-    namespace "com.example.app"
+    namespace = "com.example.app"
...
-    implementation group: 'com.squareup.okhttp3', name: 'okhttp', version: '4.12.0'
-    implementation(group: 'com.google.guava', name: 'guava', version: '33.0.0-android')
+    implementation 'com.squareup.okhttp3:okhttp:4.12.0'
+    implementation('com.google.guava:guava:33.0.0-android')
...
-    maxHeapSize "1g"
+    maxHeapSize = "1g"
```

Exit code is `1` when an `error` is found (`--fail-on error`, the default), so it works as a CI gate. `--fail-on warning` also fails on
warnings, `--fail-on never` only reports.

## Rules (21)

`oracle` = reproduced and compared with real Gradle in CI. `docs` = taken from the Gradle upgrade guide and pattern-tested only (Gradle
does not print the warning for a plain `gradle help`, or it only matters in an IDE sync).

| Rule | Severity | Fix | Checked | What Gradle 10 changes |
|---|---|---|---|---|
| `space-assignment` | error | yes | oracle | Groovy `propName value` for Gradle core properties (`url`, `name`, `group`, `version`, `description`, `sourceCompatibility`, `maxHeapSize`, ...) |
| `space-assignment-android` | warning | yes | oracle (AGP 8.13.2) | the same for Android Gradle Plugin properties (`namespace`, `viewBinding`, `abortOnError`, `shrinkResources`, `signingConfig`, ...). `compileSdk`, `minSdk`, `targetSdk`, `versionCode`, `versionName`, `applicationId`, `minifyEnabled` have explicit methods in AGP and are **not** reported |
| `multi-string-dependency` | error | yes | oracle | `implementation group: 'a', name: 'b', version: 'c'` |
| `kotlin-dsl-delegate` | error | partly | oracle | `by extra`, `by project`, `by settings`, `by tasks.getting / registering / creating / existing` (see [Kotlin delegate fixes](#kotlin-delegate-fixes)) |
| `project-properties` | error | no | oracle | `project.properties` / `getProperties()` |
| `test-closure-methods` | error | no | oracle | `beforeTest { }`, `afterTest { }`, `beforeSuite { }`, `afterSuite { }`, `onOutput { }` on Test tasks |
| `flatdir-map` | error | no | oracle | `flatDir dirs: 'libs'`, `mavenCentral(name: ...)` |
| `artifact-urls` | error | no | oracle | `maven { artifactUrls ... }` |
| `archives-configuration` | warning | no | oracle | `artifacts { archives ... }` |
| `set-all-jvm-args` | error | no | oracle | `setAllJvmArgs(...)` / `allJvmArgs = ...` |
| `start-parameter-build-cache` | error | no | oracle | `gradle.startParameter.buildCacheEnabled = true` (assignments only) |
| `reporting-extension` | error | no | oracle | `reporting.file('x')` |
| `pmd-target-jdk` | error | no | oracle | `targetJdk` in the PMD plugin |
| `find-all-closure` | warning | no | oracle | `tasks.findAll { }` on Gradle collections |
| `build-needed-dependents` | warning | no | docs | the `buildNeeded` / `buildDependents` tasks |
| `project-container` | warning | no | docs | `project.container(...)` |
| `apply-false-precompiled` | error | no | docs | `apply false` in a precompiled script plugin |
| `develocity-plugin-old` | warning | no | docs | `com.gradle.develocity` / `com.gradle.enterprise` plugin before 4.0 |
| `impldep-import` | error | no | docs | `import org.gradle.internal.impldep.*` in Kotlin DSL scripts |
| `tooling-parallel-implicit` | warning | no | docs | `org.gradle.parallel=true` without `org.gradle.tooling.parallel` (matters during IDE sync) |
| `isolated-projects-unsafe-names` | warning | yes | docs | `org.gradle.unsafe.isolated-projects*` property names |

`gradle10-ready --list-rules` prints the same list. Each finding links to the Gradle documentation section for the change.

**Suppressing:** a comment `// gradle10-ready: ignore space-assignment` on the line or the line above (no rule name = every rule);
`--disable RULE`, `--only RULE`, `--ignore 'GLOB'` (repeatable).

## PR mode: only what a pull request introduces

A legacy build can have hundreds of findings; failing every PR on them is not useful. `--base REF` scans the Gradle files at the merge base of `REF` and `HEAD`, scans the working tree, and reports only the difference. Findings are matched by rule, file and source line text, so inserting lines above old code or renaming a file does not make old findings look new.

```
gradle10-ready . --base origin/main
# 1 Gradle file(s) scanned. 1 error, 0 warning introduced since origin/main; 1 auto-fixable with --fix. Not shown: 3 that were already there; 0 resolved.
```

Needs git history (`actions/checkout` with `fetch-depth: 0`); exit code 2 with a hint if the base is missing. Cannot be combined with `--fix`.

## pre-commit

```yaml
repos:
  - repo: https://github.com/cosmichackerx/gradle10-ready
    rev: v0.2.2
    hooks:
      - id: gradle10-ready          # reports; add args: ["--fail-on", "warning"] to be stricter
      # - id: gradle10-ready-fix    # or: rewrite the mechanical fixes (pre-commit then fails once so you can review the diff)
```

The hook runs on `*.gradle`, `*.gradle.kts` and `gradle.properties` files only. Several files on the command line are scanned together and keep the path they were given.

## Kotlin delegate fixes

`--fix` rewrites the single-line `val` declarations whose replacement the [Gradle upgrade guide](https://docs.gradle.org/current/userguide/upgrading_version_9.html#kotlin_dsl_delegated_properties) gives mechanically, and keeps declared types:

| before | after |
|---|---|
| `val jar by tasks.getting` | `val jar = tasks.getByName("jar")` |
| `val h by tasks.registering { }` | `val h = tasks.register("h") { }` |
| `val c by tasks.getting(JavaCompile::class) { ... }` | `val c = tasks.getByName<JavaCompile>("c") { ... }` |
| `val t by tasks.existing` | `val t = tasks.named("t")` |
| `val p: String? by project` | `val p: String? = project.findProperty("p") as String?` |
| `val g: String by extra` | `val g: String = extra["g"] as String` |
| `val v by extra("x")` | `val v = "x"` and a line `extra["v"] = v` |

Left alone (reported only): `by tasks.creating` (`TaskContainer.create` is itself deprecated in Gradle 9; whether you want `register` is your call), implicit receivers, annotated container delegates, `by settings` (Gradle property or extra?), `var`, lambda and multi-line forms, `by project` without a type. Checked with `--fix-check` against real Gradle 9.8.0: the Kotlin compiler's deprecation warnings go from 11 to the 2 that are reported-only, and the build still succeeds.

## GitHub Action

```yaml
- uses: actions/checkout@v4
- uses: cosmichackerx/gradle10-ready@v0.2.2
  with:
    fail-on: error            # error | warning | never
    # path: .                 # project directory or one build file
    # disable: "find-all-closure"
    # ignore: "legacy/**"
    # sarif-file: g10.sarif   # then upload with github/codeql-action/upload-sarif
```

Pull requests only, reporting what the PR introduces and keeping one comment up to date (needs `fetch-depth: 0` and `pull-requests: write`; the comment is skipped for fork PRs, whose token is read-only, and a missing permission never fails the job):

```yaml
permissions: { contents: read, pull-requests: write }
steps:
  - uses: actions/checkout@v4
    with: { fetch-depth: 0 }
  - uses: cosmichackerx/gradle10-ready@v0.2.2
    with:
      pr-mode: "true"      # base = the pull request base commit; or pass `base:`
      comment: "true"
```

Findings become annotations on the lines, and a Markdown table goes to the job summary. `action.yml` has the metadata the Marketplace
asks for (name, description, branding, inputs). Publishing to the Marketplace is a manual tick box on the release page; I have not
checked that the name is free there.

## Deprecation watch (keeps the rule table honest)

`.github/workflows/gradle-watch.yml` runs every Monday (and on demand). `scripts/watch/watch_upgrade_guide.py` reads the *Deprecations* sections of the
[Gradle 9 upgrade guide](https://docs.gradle.org/current/userguide/upgrading_version_9.html), and compares every item against the anchors cited by the rules and
`scripts/watch/triaged.txt`. It opens **one issue** (label `gradle-watch`, deduplicated by a key in the title) when

- the guide lists a deprecation that no rule or triage entry covers,
- a rule cites an anchor that no longer exists in the guide (Gradle's own `archives` message links to a dead anchor), or
- `upgrading_version_10.html` or a `10.x` entry in `services.gradle.org/versions/all` appears.

```
$ python scripts/watch/watch_upgrade_guide.py
deprecation items: 54; cited by a rule: 18; triaged: 36; new: 0
```

Limits: heading titles are only a proxy for "removed in the next major", and the 36 baseline entries in `triaged.txt` mean *known when the watcher started*, not *reviewed*.

## How it is verified

* **Against real Gradle, in CI.** `tests/oracle/` holds three small projects (Groovy DSL, Kotlin DSL, Android with AGP 8.13.2) with the deprecated
  constructs one per line, plus negative cases. CI downloads the Gradle distribution (checksum pinned), runs it with `--warning-mode all`,
  reads the file, line and documentation anchor Gradle prints (for Kotlin DSL the Kotlin compiler's `w: ...build.gradle.kts:N:M ... is deprecated`
  lines) and fails if gradle10-ready reports a different set of lines. `--fix-check` applies `--fix` to a copy and checks that Gradle stops
  warning and the build still succeeds. Today: Gradle 9.8.0 (Groovy, Kotlin DSL) and Gradle 8.14.3 + AGP 8.13.2 (Android).
* **Unit tests:** about 100 cases (positive and negative for every rule, fixes on CRLF files, idempotence, CLI exit codes, output formats) on
  Linux, Windows and macOS with Python 3.9, 3.11 and 3.13.
* **On real projects:** see [docs/precision.md](docs/precision.md): 100 public Android repositories, 64 with at least one finding;
  40 random findings read by hand.

## How it relates to other tools

* `./gradlew --warning-mode all` and Build Scans are authoritative for what *your* build executes with *your* plugins. gradle10-ready
  needs no working build, looks at every file including code paths that do not run, and is a cheap CI gate. Use both.
* [OpenRewrite](https://docs.openrewrite.org/recipes/gradle/useassignmentforpropertysyntax) has a recipe for space-assignment; it runs through a Gradle
  plugin and needs a working build. gradle10-ready covers more rule families in one pass and needs only Python; OpenRewrite has far more
  general refactoring power.

## Limitations (read these)

* Pattern based, no Groovy/Kotlin parser, no type information. The space-assignment lists are **explicit allow-lists** of property names
  confirmed against real Gradle/AGP; anything not on the list is not reported, so recall is limited by design. Android property names depend on the AGP version.
* Third-party plugin DSLs (Kotlin Gradle Plugin, Spotless, publishing plugins, ...) are not covered, and neither is the `propName(value)`
  call form. Build logic written as classes (`buildSrc`, included builds) is not scanned, only scripts.
* Behavioural changes (implicit property lookup in parent projects, execution-time `Task.project` access, configuration-cache
  incompatibilities, most other Gradle 10 changes) are **not detected**.
* `--fix` only does mechanical text replacement; review the diff anyway.

## Roadmap

See the [open issues](https://github.com/cosmichackerx/gradle10-ready/issues): PR mode (only new findings), more rules, Kotlin DSL delegate fixes, version-catalog and settings checks.

## Related tools

Small, independent tools by the same author, for build and CI hygiene and for migrations with a deadline. Each works on its own; none requires another.

**Gradle and Android migrations**

* [gradle-version-catalog-lint](https://github.com/cosmichackerx/gradle-version-catalog-lint): Lints `libs.versions.toml`: unused libraries, plugins and versions, dynamic or SNAPSHOT versions, hard-coded dependencies.
* [agp9-ready](https://github.com/cosmichackerx/agp9-ready): Static scan of Gradle files for what Android Gradle Plugin 9 and 10 break (built-in Kotlin, legacy variant API, opt-outs), including `buildSrc`. `--fix`, PR mode.
* [kotlin24-ready](https://github.com/cosmichackerx/kotlin24-ready): Static scan of Gradle build scripts for what Kotlin 2.4 removes in the Kotlin Gradle plugin (language version 1.9, KMP `targetHierarchy`, Compose options, ABI validation). `--fix`, PR mode.
* [android-target-ready](https://github.com/cosmichackerx/android-target-ready): Static scanner for the targetSdk 36 / 37 migration in app code and manifests (edge-to-edge, predictive back, large screens).
* [android-target-lint](https://github.com/cosmichackerx/android-target-lint): The same targetSdk migration checks as real Android Lint rules (a lint jar with type resolution).

**CI and repository hygiene**

* [node24-ready](https://github.com/cosmichackerx/node24-ready): Finds GitHub Actions still on the removed Node 20 runtime, also inside composite actions and reusable workflows, and the smallest node24 upgrade.
* [dependabot-gaps](https://github.com/cosmichackerx/dependabot-gaps): Finds manifests your `dependabot.yml` does not cover, and dead or overlapping entries.
* [sha256-ready](https://github.com/cosmichackerx/sha256-ready): Finds code that assumes 40-character Git hashes before Git 3.0 makes SHA-256 repositories the default.
* [agent-context-diff](https://github.com/cosmichackerx/agent-context-diff): Diffs `AGENTS.md`, `CLAUDE.md`, Cursor rules and MCP configs between git refs (new servers, widened permissions, hidden Unicode).

## License

MIT
