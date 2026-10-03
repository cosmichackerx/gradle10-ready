# What was measured, and what was not

## 1. Against real Gradle (oracle)

`tests/oracle/run_oracle.py` runs Gradle on three projects and compares line by line with gradle10-ready (see the README). Result on 2026-10-03:

| project | Gradle | pairs Gradle warned about | reported by gradle10-ready |
|---|---|---|---|
| Groovy DSL (`tests/oracle/groovy`) | 9.8.0 | 22 | 22 (identical lines and documentation anchors) |
| Kotlin DSL (`tests/oracle/kotlin`) | 9.8.0 | 11 lines (Kotlin compiler warnings) | 11 (identical lines) |
| Android (`tests/oracle/android`) | 8.14.3 + AGP 8.13.2 | 32 | 32 |

`--fix-check` (Groovy and Android projects): after `--fix`, Gradle no longer warns about the fixed lines and the build is still successful.

This also corrected my own first draft: I had put `compileSdk`, `minSdk`, `targetSdk`, `versionCode`, `versionName`, `applicationId`, `minifyEnabled` and the signing `storeFile`/`keyAlias` family on the Android list because they appear in migration pull requests. Running AGP showed they have explicit methods and **do not** warn. They were removed and are pinned by a negative test.
Rules marked `docs` in the README are not covered by this check.

## 2. On 100 public Android repositories

`scripts/corpus/run.py` over 100 shallow clones (the same corpus I use for [android-target-ready](https://github.com/cosmichackerx/android-target-ready); chosen as popular and recently active Android/Kotlin repositories, not a random sample of all Gradle builds).

| | |
|---|---|
| repositories with Gradle files | 99 |
| repositories with at least one finding | 64 |
| `space-assignment` | 423 findings in 31 repos |
| `space-assignment-android` | 330 findings in 29 repos |
| `kotlin-dsl-delegate` | 314 findings in 21 repos |
| `project-properties` | 71 findings in 7 repos |
| `tooling-parallel-implicit` | 34 findings in 24 repos |
| `multi-string-dependency` | 6 findings in 2 repos |
| other rules | 1-2 findings each |

**Hand check:** 40 findings drawn at random (seed 11, from the build-script rules) were read in context: all 40 were genuine uses of the flagged construct. An earlier sample (before the AGP check above) found real false positives in the Android list; and one false positive in `start-parameter-build-cache` (a *read* of `startParameter.buildCacheEnabled`, which Gradle does not deprecate), now restricted to writes. A reading by the author is not an independent review, and "genuine use of the construct" is not the same as "Gradle 10 would break this build": for example a `project.properties` read on a repository that already moved to Gradle 10 would behave as documented, which I did not test on those repositories.

## Not measured

* Recall: how many of the Gradle 10 breakages in a real build the tool finds. The oracle projects only contain what I wrote into them.
* Behaviour on Gradle versions other than the ones above, and on AGP versions other than 8.13.2.
