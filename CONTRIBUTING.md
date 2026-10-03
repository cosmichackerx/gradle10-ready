# Contributing

    python -m venv .venv && . .venv/bin/activate
    pip install -e . pytest
    pytest -q

* A new rule needs an entry in `src/gradle10_ready/rules.py` with the link Gradle itself prints (or its upgrade-guide section), a detector in `scan.py`, and a unit test with positive and negative cases.
* Rules must be checked against real Gradle. Add the construct to the matching project under `tests/oracle/` and run `python tests/oracle/run_oracle.py tests/oracle/groovy build.gradle` with Gradle on the `PATH` (see `.github/workflows/ci.yml` for the versions). If Gradle cannot reproduce the warning with `gradle help`, mark the rule `oracle=False` and say so in the README.
* Fixes (`--fix`) must be safe: add the case to `tests/test_rules.py` and make sure `--fix-check` still passes.
* Keep the project dependency-free (standard library only) and compatible with Python 3.9.
