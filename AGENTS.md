# AGENTS.md

Every rule below is mandatory for any LLM agent working in this repository.

1. Use a mature, maintained library instead of writing your own implementation.
2. Fix the root cause, never the symptom.
3. Verify facts against primary sources (documentation, source code, package registries), never against your training memory.
4. State every assumption that changes the behavior of your solution.
5. Report what you verified and what you could not verify.
6. When you find an implicit state machine, report it and propose a design with an explicit state; do not implement it unless asked.
7. Do not change behavior in a refactoring task.
8. Do not add a lint, type or coverage suppression; if it is unavoidable, use the narrowest code and a one-line reason.
9. Test each production unit in exactly one test file at the mirrored path, and assert once per test.
10. Run `make check` and fix every failure before declaring the work done.
11. Regenerate lock files with the project tooling, never edit them by hand.
12. Do only what the task asks; report related findings instead of fixing them.
13. Give test functions a descriptive name and no docstring; the name describes the test.
