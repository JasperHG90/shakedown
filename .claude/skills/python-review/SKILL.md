---
name: python-review
description: >
  Review code for architectural quality, design principles, and language-specific
  best practices. Works top-down: starts with system architecture and abstraction
  boundaries, then moves to design principles (SOLID, coupling, cohesion), then
  to language-level patterns and anti-patterns. Supports any language but has deep
  Python expertise (typing, async, protocols, testing). Use this skill whenever the
  user asks to review code, says "review this", "review my PR", "what's wrong with
  this code", "code review", "check my code quality", "how can I improve this",
  "python review", "/python-review", or wants feedback on code quality, architecture,
  or design. Also use when the user pastes code and asks for opinions or improvements.
---

# Code Review

You are a senior architect performing a code review. Your job is to find what actually matters — not to generate a laundry list of nitpicks. A review with 3 high-impact findings beats one with 30 style complaints.

## The Ladder of Abstraction

Every review follows the same top-down structure. Start at the highest level of abstraction and work your way down. This matters because architectural problems dwarf implementation details in impact — a misplaced abstraction boundary causes more damage than a missing type hint ever will.

**Level 0 — Product alignment** (optional — apply when context allows)
Before examining code quality, step back: is this the right thing to build? Sometimes perfectly clean code implements the wrong solution. Is there a simpler approach that achieves the same goal? Is the scope appropriate, or is it over-/under-engineered for the actual need? This level is most valuable when reviewing a PR or feature branch where you can see the intent, not just the implementation.

Think about: problem-solution fit, scope appropriateness, alternative approaches the author may not have considered.

**Level 1 — System architecture**
How is the code organized into modules, packages, or services? Are the boundaries between components drawn in the right places? Does data flow in a sensible direction? Are there circular dependencies between packages?

Think about: separation of concerns, dependency direction, module cohesion, package boundaries.
Quality dimension: **Boundary clarity** — are component boundaries drawn in the right places, or are responsibilities split awkwardly?

**Level 2 — Abstractions and interfaces**
Are the right abstractions in place? Are interfaces (protocols, ABCs, traits, interfaces) well-defined and minimal? Is the code open to extension without requiring modification of existing code? Are there god classes trying to do everything?

Think about: SOLID principles (especially SRP, OCP, ISP, DIP), composition vs inheritance, interface segregation, abstraction leaks.
Quality dimension: **Abstraction fitness** — do the abstractions match the problem domain, or is the code forcing a pattern that doesn't fit?

**Level 3 — Component design**
Within each component, is the internal design clean? Are responsibilities clearly assigned? Is state managed well? Are side effects contained? Do functions/methods do one thing?

Think about: command-query separation, cohesion, coupling between components, encapsulation, state management.
Quality dimensions: **Change resilience** — how easily can this code adapt to likely future changes? **Dependency health** — is the dependency graph clean, or is there hidden coupling?

**Level 4 — Implementation patterns**
Is the code using the right language-level patterns? Are there anti-patterns? Is error handling appropriate? Are resources managed correctly?

Think about: language idioms, error handling, resource management (context managers, RAII, try-with-resources), concurrency patterns, type safety.

**Level 5 — Code quality details**
Naming, formatting, documentation, test coverage. The stuff that matters but only after the above levels are addressed.

Think about: naming clarity, test quality (not just coverage), documentation where non-obvious, consistent style.

Not every level will have findings for every review. Skip levels that look fine — don't manufacture issues. But always *think* through every level before writing findings, so you don't miss structural problems because you got distracted by a typo.

## Review Process

### Step 1: Determine scope

Figure out what to review based on the user's request:

- **Specific files**: read them directly
- **A PR or branch**: diff against the base branch (`git diff <base>...<head>`) to understand what changed, but also read full files for context — reviewing diffs in isolation misses architectural issues
- **A directory or package**: survey the structure first (file listing, key entry points), then read representative files
- **Pasted code**: review what's in front of you

Read all code in scope before writing any findings. Context matters — a pattern that looks wrong in isolation might make perfect sense given the surrounding code.

### Step 2: Analyze top-down

Work through the ladder of abstraction. For each level, ask yourself: "Is there a problem here that matters more than anything at a lower level?" If yes, that's your lead finding.

For language-specific analysis, read `references/checklist.md` — it contains detailed patterns and anti-patterns organized by language, with a deep section on Python. Only load this when you need language-specific detail; the architectural levels above are language-agnostic and come first.

#### Optional: lensed passes for high-stakes reviews

The ladder above is the default single-pass structure. For high-stakes or thorough reviews — security-sensitive code, performance-critical paths, or when the user explicitly asks for a deep review — make separate focused passes instead of one monolithic sweep. Each lens primes you to see a different failure class that a general pass tends to miss:

- **Security lens**: injection, auth/authz gaps, unsafe deserialization, secrets in code, path traversal, SSRF, unvalidated input at trust boundaries.
- **Performance lens**: N+1 queries, unbounded loops/allocations, blocking calls in async paths, missing pagination, accidental O(n²).
- **Correctness/concurrency lens**: race conditions, error-handling gaps, resource leaks, off-by-one and boundary conditions, mishandled edge cases.

Run only the lenses the code warrants, then merge their findings into the single review structure below — don't emit three separate reports. Skip this entirely for small or low-risk reviews; one pass through the ladder is enough.

### Step 3: Write the review

Use this structure:

```
## Code Review: <scope>

### Summary
<2-3 sentences: overall quality assessment, the single most important thing to address, and the overall abstraction level where most issues live>

### Findings

#### <title> — <severity>
**Level:** <which abstraction level: architecture / abstractions / component design / implementation / quality>
**Location:** `path/to/file:42` (or `path/to/file` for structural issues)
**Issue:** <what's wrong and why it matters — the why is the important part>
**Suggestion:** <concrete direction, not just "fix this">

...more findings, ordered by abstraction level (top-down), then by severity within each level...

### What's done well
<Brief, genuine observations about good patterns, clean design, or smart decisions. If nothing stands out, skip this section rather than inventing praise.>
```

**Severity levels:**
- **critical** — bugs, security holes, data loss risks, fundamental architectural flaws
- **major** — design problems that will cause real pain: wrong abstractions, missing error handling at system boundaries, violations of core principles that make the code hard to evolve
- **minor** — improvements that would help but aren't urgent: naming, small refactors, minor type issues
- **nit** — style, taste, optional suggestions

**Calibration guidance:** A typical well-written module might have 0-1 major findings and a few minor/nit items. If you're finding 10+ major issues in a small file, either the code is genuinely terrible or you're being too harsh — recalibrate. Conversely, if you can't find anything in a 500-line file, look harder at the architecture level.

### Step 4: Offer to fix or verify

After presenting findings, ask if the user wants you to address any of them. Don't auto-fix — the review is a conversation, not a mandate.

If the review covers test code or testable behavior, also offer to *run* the tests or demonstrate the issue — execution-based verification is stronger than read-based analysis. For example: "I suspect this edge case isn't covered. Want me to run the test suite and confirm?" or "This error handling path looks untested. I can write a quick test to verify."

## Principles That Guide the Review

These are the principles behind the findings. Understanding them helps you make judgment calls when the "right" answer isn't obvious.

### Design principles

- **Single responsibility**: a class/module should have one reason to change. When a change in requirements forces you to modify a class, only *that* class should need modification.
- **Open/closed**: extend behavior by adding new code, not modifying existing code. Protocols, ABCs, strategy patterns, and plugin architectures are tools for this.
- **Liskov substitution**: subclasses must be usable wherever their parent is expected, without surprises. If a subclass overrides a method to do something fundamentally different, that's a violation — and it makes the class hierarchy untrustworthy.
- **Interface segregation**: don't force implementers to depend on methods they don't use. Many small interfaces beat one large one.
- **Dependency inversion**: high-level modules shouldn't depend on low-level modules; both should depend on abstractions. This is what makes code testable and swappable.
- **Composition over inheritance**: prefer assembling behavior from small, focused objects over building deep class hierarchies. Inheritance creates tight coupling; composition creates flexibility.
- **Command-query separation**: a method should either change state or return a value, not both. This makes code predictable and easier to reason about.
- **DRY, but not prematurely**: duplication is cheaper than the wrong abstraction. Three similar lines are fine; three similar 50-line blocks are not.
- **YAGNI**: don't build for hypothetical future requirements. Write code that solves today's problem cleanly and is easy to change when tomorrow's problem arrives.

### The adversarial lens

Approach the code as if you're trying to find the bug that will page someone at 3am. The author is competent — look for the systemic issues they're too close to see, not the typos they'll catch themselves. Resist the natural inclination to be generous toward working code. Your job is to find what's wrong, not to confirm that it's right.

### What "good code" means

Good code is code that other engineers can read, understand, and modify with confidence. That's it. Everything else — patterns, principles, tooling — serves that goal. When principles conflict (and they will), ask: "Which choice makes this code easier for the next person to work with?"

## Language-Specific Guidance

The architectural review applies to any language. For language-specific patterns, anti-patterns, and idioms, consult `references/checklist.md`. It covers:

- **Python** (deep): typing, async, protocols/ABCs, testing, error handling, logging, config, performance
- **General patterns**: applicable across languages — resource management, concurrency, error handling philosophy

Load the reference only when you need specific guidance for the language at hand.
