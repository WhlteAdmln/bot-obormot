# Development and Architecture Principles

These principles are a shared baseline for contributors to any project that adopts them.

They explain how we approach changes, architecture, testing, and maintenance, and why. They do not replace a repository's `CONTRIBUTING.md`, `AGENTS.md`, or architecture documentation: those documents hold the mandatory rules and commands. When a project-specific document defines a more specific command or constraint, follow that document.

## 1. Slow and steady wins the race

Russian: *“Тише едешь — дальше будешь.”*

Prefer small, reviewable changes over large batches of unrelated work. A pull request should normally represent one logical step and must not exceed **256 changed lines** (insertions plus deletions). Lock files, generated files, and translations of a document do not count towards the limit. If a task requires more, split it into independently reviewable pull requests. Do not split a genuinely inseparable change artificially; agree on such an exception with the maintainers before submitting it. A project may measure pull request size in report-only mode before it enforces the limit.

Keep issues concise but actionable. State the problem, the expected result, and the context needed to reproduce or understand it. Avoid turning an issue into a general wishlist.

## 2. Measure seven times, cut once

Russian: *“Семь раз отмерь, один раз отрежь.”*

Before changing code, read the relevant implementation, tests, and project documentation. Reproduce a bug when possible. Check the current behavior and identify the responsible component before choosing a solution. Verify external facts against primary sources such as official documentation, source code, or package metadata; do not rely on memory when the detail affects behavior.

An issue should include expected and actual behavior for a bug, steps to reproduce when applicable, the affected version or environment (without local paths, user names, or machine names), and sanitized logs or examples when useful.

## 3. If you chase two rabbits, you will catch neither

Russian: *“За двумя зайцами погонишься — ни одного не поймаешь.”*

One issue and one pull request should have one main purpose. Do not combine a feature, an unrelated refactoring, dependency cleanup, and formatting changes in the same patch. Keep commits and review discussions focused on that purpose. Mention the issue in the pull request and link it with GitHub's closing syntax, for example `Closes #42`.

## 4. An old friend is better than two new ones

Russian: *“Старый друг лучше новых двух.”*

Preserve existing behavior and public interfaces unless the task explicitly requires a behavior change. A refactoring task is not permission to redesign the feature, change defaults, or silently remove compatibility. When a behavior change is intentional, describe it, test it, and update the relevant documentation. Treat HTTP responses, configuration names, command-line interfaces, and persisted data as contracts that may have users outside the modified module.

## 5. Every cricket should know its own perch

Russian: *“Всяк сверчок знай свой шесток.”*

Keep each module responsible for one clear part of the system. Separate transport and framework code from application logic, business rules, persistence, and external-service clients. Put parsing and validation at clear boundaries; keep reusable domain logic independent of framework handlers, routes, and infrastructure details where practical.

When a system is split into separate services, keep them talking through their documented contracts rather than importing each other's internals.

## 6. The devil is in the details

Russian: *“Дьявол кроется в деталях.”*

Make important contracts and limits explicit. Define input and output shapes, error behavior, timeouts, size limits, concurrency limits, ownership of temporary files, and cleanup responsibilities. Avoid hidden work, unbounded queues, implicit downloads, and assumptions that external programs or model files are always available. A new integration should document what happens when its dependency is unavailable or returns invalid data.

## 7. Too many cooks spoil the broth

Russian: *“У семи нянек дитя без глазу.”*

Avoid unclear ownership and competing sources of truth. Do not create duplicate configuration paths, parallel implementations, or copied helper modules without a documented reason. Prefer explicit dependencies and lifecycle management over hidden global mutable state. Do not read environment variables or perform I/O as an import-time side effect; load and validate configuration at a deliberate application boundary.

For files intentionally shared by several repositories, name one repository as the source of truth. Change the file there first, copy it to the others, and check automatically that the copies are identical. Do not independently edit the copies.

## 8. Don't reinvent the wheel

Russian: *“Не изобретай велосипед.”*

Use mature, maintained libraries for established problems such as parsing, HTTP, cryptography, serialization, and platform integration. Before adding a dependency, check whether an existing project dependency already solves the problem, whether the new package is maintained, and whether its cost is justified. Avoid custom frameworks and utility layers that merely wrap a small part of a standard or well-supported library.

## 9. Better safe than sorry

Russian: *“Бережёного Бог бережёт.”*

Treat security as a design requirement, not a final review step. Never commit tokens, passwords, private keys, real user data, local `.env` files, or machine-specific state. Do not put secrets in logs, exception messages, screenshots, test fixtures, or pull-request examples. Keep authentication fail-closed by default; validate untrusted input and enforce resource limits before expensive processing. Use private temporary storage and reliably clean up uploaded or generated files.

Tests must use fake credentials and controlled fixtures. Never require real API keys, production accounts, or real user data to pass the normal test suite.

## 10. You reap what you sow

Russian: *“Что посеешь, то и пожнёшь.”*

A behavior change should come with tests that demonstrate the intended behavior. Cover the normal path and relevant failure cases, boundary values, and regressions. Keep unit tests deterministic and independent of network access, a GPU, external services, and machine-specific state. Put tests for real external integrations in the appropriate integration-test suite and make their prerequisites explicit.

When practical, keep the test layout recognizable from the production package layout. A test should make its scenario and expected outcome clear without relying on unrelated tests to establish hidden state.

## 11. Actions speak louder than words

Russian: *“Дела говорят громче слов.”*

Run the repository's required checks before requesting review. Use the repository's automatic fixes and its main quality gate as defined in its `CONTRIBUTING.md`. Run additional checks when the change touches their area, such as integration tests, installer tests, documentation checks, or container builds.

In the pull request, list the commands you actually ran and report their results honestly. Do not say that tests passed when they were skipped, unavailable, or not run.

## 12. You can't hide an awl in a sack

Russian: *“Шила в мешке не утаишь.”*

Do not silence a failing test, linter, type checker, or security check just to make the pipeline green. Do not add broad lint, type, or coverage suppressions. If a suppression is genuinely unavoidable, make it as narrow as possible and add a short explanation next to it. Prefer fixing the underlying defect.

## 13. There's no smoke without fire

Russian: *“Дыма без огня не бывает.”*

Fix root causes rather than hiding symptoms with retries, special cases, or broad exception handling. When a failure reveals an unclear state transition or an implicit state machine, name it: describe its states and allowed transitions and propose an explicit design as a separate change, instead of adding another flag or special case. Log enough context to diagnose failures, including correlation identifiers where the project supports them, but never log secrets or sensitive payloads.

## 14. Don't count your chickens before they hatch

Russian: *“Цыплят по осени считают.”*

Do not assume that an external service, native executable, model, optional package, file, or network connection is present just because it exists on a developer's machine. Check availability at the appropriate boundary and return a clear, safe error when a prerequisite is missing. Keep optional capabilities optional and make their status diagnosable.

## 15. Two heads are better than one

Russian: *“Одна голова хорошо, а две лучше.”*

Ask for review when the change is ready, and make the reviewer's job straightforward. Explain what changed, why it changed, how it was tested, and what risks or compatibility concerns remain. Respond to review comments with code or a reasoned explanation; do not treat review as a formality. If you discover adjacent problems outside the scope of the current change, report them separately instead of silently expanding the pull request.

## 16. A bird in the hand is worth two in the bush

Russian: *“Лучше синица в руках, чем журавль в небе.”*

Solve the requirement that exists, not a speculative future version of it. Avoid premature generalization, unnecessary abstractions, configuration switches with no concrete use case, and compatibility layers for hypothetical consumers. Introduce an abstraction when it removes real duplication, clarifies a boundary, or makes important behavior easier to test.

## 17. An agreement is worth more than money

Russian: *“Уговор дороже денег.”*

Documentation is an agreement with users, operators, and contributors. Keep documentation, examples, defaults, and architecture diagrams consistent with the implementation. When changing commands, configuration, API behavior, deployment, or supported formats, update the relevant README and documentation in the same change. Do not leave obsolete instructions that lead contributors or operators to a path the code no longer supports.
