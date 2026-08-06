---
name: doc-write
description: Write or refactor project documentation — tutorials, how-to guides, reference pages, and explanation articles — using the Diátaxis framework. Enforces strict mode purity (a tutorial is not a how-to is not a reference is not an explanation), Orwell's six rules for clear prose, and a ladder-of-abstraction rhythm where concrete examples open and close each piece. Targets HUMAN readers — not agents — so emphasizes plain, everyday English over jargon. Use whenever the user asks to write, draft, refactor, edit, improve, or polish documentation — phrases like "write a tutorial", "draft a how-to", "turn this into a reference", "document this feature", "rewrite this doc", "improve the README", "add user docs", "document the API", "explain how X works for newcomers", or any task that produces user-facing prose for a software project. Triggers even when the user does not say "Diátaxis" explicitly — any doc-writing or doc-refactoring task gets this lens.
---

# Writing Project Documentation

## Who reads this — and who you are writing for

Project documentation is for **humans** — engineers, operators, users learning a system. Not for agents. That single distinction changes most decisions in this skill. Write the way a thoughtful colleague writes: warm, plain, useful. The reader sat down because they need something done or want to understand something. Serve that, and stop.

Agent-facing prose (CLAUDE.md, MCP tool descriptions, system prompts) is a different craft. If a task asks for agent-facing prose, this skill is not the right tool.

## The workflow

Every doc-writing task follows six steps:

1. **Pick the mode.** Diátaxis splits documentation into four modes — tutorial, how-to, reference, explanation. Each serves a different reader need. Pick before you write.
2. **Apply the mode's shape.** Every mode has a section template. Use it.
3. **Apply the prose rules.** Plain English, active voice, ladder of abstraction, Orwell's six.
4. **Verify every interface reference.** CLI flag, MCP signature, API endpoint, config key — read the source, don't infer.
5. **Cite the code for mechanism claims.** Internal-behaviour claims need an inline HTML tag pointing to the code that proves the claim.
6. **Run the editorial review.** Take off the writer's hat, put on the editor's, and read the page adversarially before declaring it done.

For **refactors**, add a step before #1: identify the mode the *existing* page should belong to, then check whether the current content stays in that mode. Content that fails the mode test moves to its right home — it does not get justified into staying.

## Step 1: Pick the mode

Two questions decide the mode:

1. Does this content tell the reader **what to do**, or **what to know**?
2. Is the reader **studying** (acquiring a skill) or **working** (applying a skill)?

|                  | Studying (acquisition)         | Working (application)          |
|------------------|-------------------------------|-------------------------------|
| **What to do**   | **Tutorial**                  | **How-to guide**              |
| **What to know** | **Explanation**               | **Reference**                 |

Plain-language gloss:

- **Tutorial** — "I want to learn how this works by doing something with it." Learn-by-doing toward a goal the reader can verify they reached.
- **How-to guide** — "I have a job to do; show me the steps." Recipe for one specific task; assumes the system is already installed.
- **Reference** — "I need to look up an answer." Succinct, exhaustive, product-led. No narrative.
- **Explanation** — "I want to understand the why." Concepts, trade-offs, design rationale.

### Mode purity rule

Each leaf page owns **one** mode. The decision matrix above is the test, not the page's heading. If a passage on a tutorial page is answering "what is X" rather than walking a hands-on step, it belongs on an explanation page — move it. If a how-to page sneaks in a design rationale paragraph, that paragraph moves to explanation. If a reference page narrates the history of a feature, the history moves out.

The cost of mixed modes is that no reader's intent is served. A tutorial reader gets stuck on theory; an explanation reader can't find the why under the steps; a reference reader can't find the entry under the prose.

A practical test: read the page imagining each of the four reader-intents above. If a reader of the "wrong" intent could mistake this page as written for them, the page has bled.

## Step 2: Apply the mode's shape

### Tutorial

Sections:

- **Prerequisites** — bullet list, one line each.
- **Steps** — numbered. Each step has one verb and ends with an expected output the reader can verify (a CLI line, a UI screenshot, a file appearing).
- **What you built** — one paragraph naming the result.
- **Next steps** — three to five links to closest neighbours.

A good tutorial ends with the reader having something they can show off (a working install, a first memory saved, a query that returned results). If the closing self-check fails, the reader knows the tutorial failed — and *that is the right behaviour*. Do not hide failure modes.

Length budget: 150–400 lines. Tutorials over 600 lines are a smell; split into two.

### How-to guide

Sections:

- **Prerequisites** — what the reader needs already installed or configured.
- **Procedure** — steps OR an option matrix (when the choice points matter more than the sequence).
- **Verification** — how the reader confirms the goal was met.
- **Troubleshooting** — the two or three things that go wrong most often, and what to do.

How-to guides are narrow on purpose. A how-to titled "Set up the server" is too broad. "Configure the server with TLS" is right. "Configure the server" without a qualifier is a tutorial in disguise.

Length budget: 80–250 lines. Over 300 lines is a smell; split, or convert to a tutorial if the goal is genuinely big enough to need study.

### Reference

Sections:

- **Index** — a table of every entry (every endpoint, every command, every key). The table IS the index; do not put prose between it and the per-entry details.
- **Per-entry detail** — same shape every time. For an API endpoint: signature, parameters, returns, errors, example. For a config key: type, default, env-var mapping, one-line description.

Reference pages are auto-generatable from code when the source has good docstrings, type hints, or Pydantic schemas. If the project supports it, prefer auto-generation with a CI drift guard over hand-writing — drift between code and reference docs is the single biggest source of stale docs in any project.

Length budget: unbounded. Reference is exhaustive on purpose.

### Explanation

Sections:

- **Context** — what this concept is part of. One paragraph.
- **Model** — a diagram or short narrative naming the moving parts.
- **Mechanism** — a worked example showing the concept in action.
- **Trade-offs / alternatives considered** — what was rejected and why.
- **Implications** — what the reader should now understand about adjacent decisions.

Explanation pages live at the top of the ladder of abstraction (see Step 3). Open concrete, climb to the principle, return concrete.

Length budget: 200–500 lines.

## Step 3: Apply the prose rules

### Plain English first

The reader is human. Write the way you would brief a smart colleague who has never seen this system.

- **Default to "you".** Second person, addressing the reader directly. Not "the user", not "one", not "we". (Exception: when a system component is the actor, name it — "the scheduler", "the server", "the linter".)
- **Active voice unless passive is clearer.** "Edit the config file" beats "the config file should be edited". When the *thing* matters more than the actor, passive is fine: "the file is saved to disk".
- **Short sentences.** One idea per sentence. Two clauses is plenty. If a sentence runs out of breath when you read it aloud, cut it in half.
- **Short words.** Replace long ones with short common ones whenever you can: *utilize → use; leverage → use; facilitate → help; in order to → to; due to the fact that → because; subsequently → then; commence → start; terminate → stop.*
- **Cut weasel words.** *Just, simply, easily, basically, obviously, it should be noted that.* They condescend or hedge. Delete them.
- **Cut filler.** *It is worth mentioning that, as you can see, in this case, generally speaking, in essence.* The reader can tell. Delete them.
- **Cut throat-clearing.** "Welcome! In this guide, we will be exploring how to…" → start with what the reader will do or know after reading.
- **Read it aloud.** If you stumble, rewrite. This is the single most effective edit you can make.

### Orwell's six (applied to docs)

George Orwell's six rules from *Politics and the English Language*, applied here:

1. **Never use a metaphor or simile you have seen in print.** *Low-hanging fruit, moving the needle, drinking from the firehose, source of truth (when there are many).* Out.
2. **Never use a long word where a short one will do.** See the plain-English list above.
3. **If it is possible to cut a word out, cut it out.**
4. **Never use the passive where you can use the active.**
5. **Never use a foreign phrase, scientific word, or jargon if you can think of an everyday English equivalent.** *Cohort, ideate, action (as a verb), bandwidth (as a metaphor for capacity).* Out.
6. **Break any of these rules sooner than say anything outright barbarous.**

Rule 6 is load-bearing. Sometimes a passive is clearer. Sometimes the technical word *is* the everyday word in the project's domain (*query*, *commit*, *deploy*). Apply rules 1–5 by default; break them when clarity needs it.

### Ladder of abstraction

The "ladder of abstraction" is how high or low your prose sits in concept space. The bottom rung is **concrete** — a specific command, a real bug, a named file. The top rung is **abstract** — the principle, the why, the model.

Good prose **alternates** rungs:

- Open at the bottom: a real scene. *"Last week the team shipped a deploy on Friday at 4pm. By 6pm everything was on fire."*
- Climb to the principle. *"Friday-afternoon deploys fail this often because the people who would catch the regression are already offline."*
- Return to the bottom. *"So when you're tempted to ship at 4pm, do this instead: ..."*

Tutorials live mostly at the bottom rung — concrete steps, concrete outputs. Explanations climb the most. How-to and reference stay near the bottom: concrete recipes, concrete signatures.

If the prose feels dry, you are probably stuck on one rung too long. Drop down (give an example) or climb up (state the principle the example illustrates).

## Step 4: Verify every interface reference

Every CLI command, every MCP tool signature, every API endpoint, every config key, every file path you write into the doc is a **contract with the reader**. They will paste your example and expect it to work. A single wrong flag in a how-to does not just break that paragraph — it teaches the reader that the rest of the doc is unreliable too. From then on they look up your claims elsewhere, and your work has done the opposite of its job.

So verify before you ship. The rule has no exceptions: **no interface reference goes into the doc without a check against the source code or a runnable `--help`.**

Where to check, by reference type (locate the source for the project at hand — the paths below are illustrative):

- **CLI examples** — read the command definition in the CLI source (or run `<cmd> --help` against a working install). Confirm: which parameters are positional arguments, which are options/flags, the exact flag name, the default value, whether the option is required.
- **RPC / tool examples** (MCP tools, RPC methods, SDK calls) — read the handler or decorator and its parameter typing. **A capability's RPC signature can differ from its CLI signature even when both expose the same underlying feature** — e.g. an MCP tool takes dict-shaped kwargs while a CLI distinguishes positional argument from option. Inferring one from the other is unreliable.
- **HTTP endpoint examples** — read the route handler in the web framework's source (FastAPI, Express, etc.).
- **Config keys** — read the config schema definition (Pydantic model, JSON schema, struct, etc.). Confirm: the field name, the type, the default, any validators that re-shape the value.
- **File paths** — confirm the path exists at the version you are documenting.

When shipped help text disagrees with the source code, trust the code and file the help-text bug as a follow-up. The doc reflects what the system *does*, not what some other doc says it does.

## Step 5: Cite the code for mechanism claims

When the doc claims something about **how the system behaves internally** — *"post-fusion reranked scores"*, *"caps history at 50 entries"*, *"falls back to embedding-similarity when the LLM budget is exceeded"* — the claim needs a citation pointing at the code that proves it. Without a citation the doc is the writer's memory of the design doc, not a verifiable assertion. The design doc itself is a moving summary of the code; pinning the claim to the code lets a reader (or a future doc maintainer) check whether the claim still holds.

Citations go in inline HTML tags so they survive markdown rendering and can be linted:

```html
<code-ref path="src/services/kv.py" lines="138-141" />
```

The tag carries the path and the line range. Line numbers drift over time; that is OK — they are accurate at write time, the linter can flag stale ones on docs build, and the reader still has a path-level anchor when lines have moved. The point is **grounding the claim in code that existed when the claim was made**, not pinning it forever.

One citation per mechanism claim, not per sentence. A worked-example block that ranges over five lines of behaviour gets a single citation at the block. A paragraph that asserts five distinct mechanisms gets five citations.

If you cannot find the code that proves a mechanism claim, the claim is wrong, vestigial, or scoped to a different page. Remove it or move it; do not ship an unverifiable internal claim.

## Step 6: Run the editorial review

The first reader of this page is **you**, with the writer's hat off and the editor's hat on. Before declaring the page done, walk it with four lenses. The reviewer's stance is adversarial: assume the writer (you) was hurried, imprecise, and over-pleased with their draft. Your job is to find the things the writer waved past.

**Readability.** Read every paragraph aloud. Where you stumble, rewrite. Where a sentence needs more than one re-read to land, the sentence is too long or the noun is unclear — fix it. Spot weasel verbs, throat-clearing intros, and tired metaphors that snuck in during drafting. (Re-apply Step 3 here with fresh eyes.)

**Correctness.** Every concrete claim — a CLI flag, a config default, a function name, an endpoint, a return shape — must be verifiable. If it's an interface reference, Step 4 already grounded it; confirm the citation is right. If it's a mechanism claim, Step 5 already cited it; confirm the cited code says what the doc says it says. Walk the page once more looking for unverified claims that slipped past.

**Conceptual clarity.** Imagine the reader has the context the *first paragraph* gave them, and no more. Can they follow each subsequent paragraph from what came before? Where a section assumes the reader already knows term X but X was never defined, either define X or move the section.

**Architectural correctness.** A doc can be readable, correct, and clear, and *still wrong about the system* — describing a deprecated path, conflating two subsystems, miscounting the layers, naming a component that no longer exists. Hold the page against the current design doc and the current code. If the doc disagrees with the design doc, one of them is stale; figure out which before publishing.

If you finish the review pass without flagging anything serious, you reviewed too gently — go again with a sharper question. Real drafts have real problems; finding none is a smell.

## Cross-link discipline

Every leaf doc ends with `See also` — at most **one** link per mode:

```markdown
## See also

- [Tutorial: Getting started](tutorials/getting-started.md)
- [How-to: Configure TLS](how-to/configure-tls.md)
- [Reference: server config](reference/server-config.md)
- [Explanation: how auth works](explanation/auth.md)
```

The constraint forces you to pick the *closest* neighbour in each mode, not every neighbour. Pages with fifteen links at the bottom are a smell — the writer didn't decide what mattered most.

## Common pitfalls

Patterns to spot in a draft and fix:

- **Mode bleed.** A tutorial that explains the design. An explanation with copy-pasteable config. A reference with narrative. Move the offending passage to its right home.
- **Passive voice for actions.** "The file should be edited" → "Edit the file."
- **Weasel verbs.** "You may want to consider running" → "Run" (or, if it really is optional, "Optional: run").
- **"The reader is referred to…"** — never start a sentence this way. Just put the link.
- **Narrative blocks in reference pages.** Reference is tables and entries, not prose. If a reference page has paragraphs longer than three sentences, ask whether they belong in an explanation page instead.
- **Tutorial that doesn't end in a verifiable result.** "You now understand X" is not a result. "Run `curl localhost:8000/health` and you'll see `{ok: true}`" is.
- **Diagrams as decoration.** A diagram in a how-to is usually wrong — how-to readers want the recipe, not the model. Diagrams belong in explanation. Reference avoids diagrams entirely.
- **Plain-text / ASCII diagrams.** Never. Use draw.io (preferred when its MCP is available) or Mermaid. See [Diagrams](#diagrams) under Output convention.
- **Multi-paragraph "Introduction" sections.** The first paragraph IS the introduction. If you need three paragraphs to introduce, your scope is wrong; split the page.
- **Front-matter "Welcome to…"** Cut. Start with what the reader will do or know.

## When refactoring an existing doc

1. **Identify the mode the page should belong to** (using the Step-1 matrix).
2. **Read the page and mark each section** with the mode it actually serves.
3. **Move mismatched sections** to their right home — or note them as candidates for a new sibling page.
4. **Rewrite the surviving content** with the shape from Step 2 and the prose rules from Step 3.

Don't keep mismatched content "because it's useful". It is useful — somewhere else.

## Output convention

Unless told otherwise:

- GitHub-flavoured Markdown.
- One H1 per page (the page title).
- Code fences carry a language hint (` ```bash`, ` ```python`).
- No emoji in body text unless the project convention allows them. (Mode-marker emoji in headings — ⚠ / 🚀 — are usually a smell; the heading text should be enough.)

### Diagrams

Architecture diagrams — and every other diagram in a doc — follow a strict ladder:

1. **If a draw.io MCP tool is available, use it.** Generate the diagram as draw.io XML, save it alongside the page, and reference it from the markdown. draw.io renders crisply at every zoom level, exports to SVG/PNG cleanly, and stays editable by humans without re-running an MCP.
2. **Otherwise, use Mermaid** in a fenced ` ```mermaid` block. Mermaid is the second-best option: GitHub renders it inline, it lives in the markdown itself, and it survives copy-paste.
3. **ASCII art and other plain-text diagrams are never allowed.** They look bad in every renderer, do not scale, and signal to the reader that the writer didn't care enough to use a real diagramming tool. If neither draw.io nor Mermaid will do (an extremely rare case — e.g. the diagram is genuinely a table), use a table; never reach for ASCII boxes-and-arrows.

The rule holds even for the smallest sketch. A two-box "A → B" relationship deserves a draw.io shape or a one-line `flowchart LR` — not `[A] --> [B]` rendered as a code block.

If the project has a `CONTRIBUTING.md`, `README.md`, or `AGENTS.md` that names additional rules (line length, header style, frontmatter, link style), follow those project rules first when they conflict with this skill.

## One last reminder

The reader is a person, not a parser. The shape (Diátaxis), the rhythm (ladder of abstraction), the rules (Orwell, plain English), the grounding (verified interfaces, cited mechanisms), and the review (editorial pass) all exist to serve that person's attention. When you have to choose between following a rule and writing something a real human will read with pleasure — write for the human. But never sacrifice grounding: an ungrounded claim is not warmth, it's a lie the writer hasn't checked yet.
