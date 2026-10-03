# Changelog

## 0.2.0 - 2026-10-03

* **pre-commit hooks** `gradle10-ready` and `gradle10-ready-fix` (`.pre-commit-hooks.yaml`); the command line accepts several paths. CI runs `pre-commit try-repo` against both hooks.
* **PR mode:** `--base REF` reports only findings new compared to the merge base (matched by rule, file and line text; renames followed). Action inputs `pr-mode`, `base`.
* **Sticky pull request comment:** Action input `comment: true` (`python -m gradle10_ready.comment`); one comment updated in place, skipped for forks and missing permissions. CI proves one comment after two runs.
* `--fix` for `kotlin-dsl-delegate`: container delegates (`registering`, `creating`, `existing`, `getting`, with optional `(Type::class)`), `val x: T by project`, `val x: T by extra` and `val x by extra(expr)`. Verified with `--fix-check` on real Gradle 9.8.0 (now also run for the Kotlin DSL project in CI).

## 0.1.0 - 2026-10-03

First release.

* 21 rules for what the Gradle 9.8 upgrade guide lists as deprecated and removed in Gradle 10: Groovy space-assignment (Gradle core and Android Gradle Plugin properties), multi-string dependency notation, Kotlin DSL delegated properties, `project.properties`, Closure-based test listeners, `flatDir(Map)`, `artifactUrls`, the `archives` configuration, `setAllJvmArgs`, `startParameter.buildCacheEnabled`, `reporting.file`, PMD `targetJdk`, `findAll(Closure)`, `buildNeeded`/`buildDependents`, `project.container`, `apply false` in precompiled scripts, Develocity plugin < 4, `impldep` imports, `gradle.properties` checks.
* `--fix` for space-assignment, multi-string notation and renamed `gradle.properties` keys.
* Text, Markdown, JSON, GitHub annotation and SARIF 2.1.0 output; `--fail-on`, `--disable`, `--only`, `--ignore`, inline `gradle10-ready: ignore`.
* GitHub Action (composite).
* Checked against real Gradle 9.8.0 and Gradle 8.14.3 + AGP 8.13.2 by the `oracle` CI job.
