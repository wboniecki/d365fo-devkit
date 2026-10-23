---
name: xpp-dev
description: Conventions for X++ / Dynamics 365 F&O development in any D365 F&O repo (repo-specific values in the repo's CLAUDE.md, section `xpp-dev config`). Use whenever writing or modifying X++ code or AOT objects (classes, tables, forms, EDTs, enums, queries, data entities), creating extensions, Chain of Command (CoC) wrappers, event handlers, SysOperation jobs, labels, starting a branch for a ticket, adding objects to a VS project, working with C# projects that build dlls for a model, or building a model. Also for querying or rebuilding the AOT metadata index (`/d365fo-devkit:xpp-dev index repo|aot create`, `/d365fo-devkit:xpp-dev index find …`).
---

# X++ development

## Configuration
Repo and machine values live in the repo's CLAUDE.md, section `## xpp-dev config`, as `KEY=value` lines.
Repo naming conventions (model prefixes, branch names, learned naming) live in CLAUDE.md too, not in this skill.
The conventions below are defaults: rules in the repo's CLAUDE.md override them.

| Variable | Scope | Used by |
|---|---|---|
| `XPPDEV_VCS` (`git` or `tfvc`) | core | branch, commit and staleness rules |
| `XPPDEV_D365PU_VERSION` (e.g. `10.0.45`) | core | platform rules, `index aot create` |
| `XPPDEV_DEFAULT_MODEL` | core | new objects |
| `XPPDEV_PACKAGES_DIR` | core | read-only standard code, label fallback, index |
| `XPPDEV_VSPROJECTS_DIR` | core | VS solutions |
| `XPPDEV_USER_LANG` (e.g. `en`) | core | language the user may write in; human-facing text |
| `XPPDEV_LABEL_LANGS` (default `en-US`) | core | required languages of new labels, indexed label languages |
| `XPPDEV_BASE_BRANCH` | git only | branch flow, moving work |
| `XPPDEV_BRANCH_PATTERN` | git only | branch flow |
| `XPPDEV_AOT_INDEX_DIR` | feature | AOT metadata index |
| `XPPDEV_PYTHON` | feature | fallback when plain `python` is not found |
| `XPPDEV_README_PATH` | feature | readme for people, any folder |
| `XPPDEV_PLUGIN_SRC` | feature | local source of this plugin, for rule changes |

Wizard:
- Each function checks only the variables it needs, not the whole config.
- A needed variable is missing: stop and ask in AskUserQuestion rounds. Propose values detected from the repo or machine
  (e.g. `.git` folder for `XPPDEV_VCS`, `XPPDEV_PACKAGES_DIR` contents for the version). Write the answers to
  `## xpp-dev config` in CLAUDE.md after the user approves.
- First init in a git repo: also propose deny rules `Edit(.gitignore)` and `Write(.gitignore)` in the repo's `.claude/settings.json`.
- Git-only rules below apply when `XPPDEV_VCS=git`. TFVC rules are added when the first TFVC repo comes up.

## Platform and what may be changed
- D365 F&O version: `XPPDEV_D365PU_VERSION`. The user announces upgrades; update the variable when they do.
- Allowed: new objects, event handlers, extensions (CoC `[ExtensionOf]`, table/form/EDT/enum/menu extensions) and new classes that derive from standard classes.
- Never overlayer or edit standard objects.
- `XPPDEV_PACKAGES_DIR` is a read/search-only reference. Repo models may be symlinked there: edit them only through the repo paths, and never write into `XPPDEV_PACKAGES_DIR` from a shell either.

## Model and naming
- Default model: `XPPDEV_DEFAULT_MODEL`, unless the user says otherwise.
- Object prefixes per model and confirmed naming patterns: see CLAUDE.md. For a model not listed there, assume the prefix is the model name; confirm when unsure.
- Extension names: the user gives them. After a pattern is confirmed, add it to the naming section in CLAUDE.md.

## Code style
- No ticket tags in code; ticket numbers go only in branch names, commits and PRs.
- Minimal English comments, only where the code isn't self-explanatory.
- Match the formatting of the surrounding code.

## Language and D365 terms
- Write everything Claude-facing in English: this skill, CLAUDE.md, memory, task notes.
- The user may describe tasks in `XPPDEV_USER_LANG`, often in detail for complex problems. Treat that as the full instruction; don't ask for an English version.
- The user names D365 objects by their technical names (tables, fields, classes, menu items), because translated UI terms are often misleading. If a translated UI term comes up and its mapping is unclear, ask for the technical name instead of guessing.
- Text for people (descriptions, reports) follows the rules in CLAUDE.md; by default it is in `XPPDEV_USER_LANG`.

## Labels
- No hard-coded user-facing text: info/warning/error/checkFailed messages, captions and help text all use labels.
- Reuse freely only `@SYS` labels or labels from the current model's own label file. Ask before reusing a label from any other label file.
- Never create labels on your own; the user says when new labels are added. Each new label needs text in every language of `XPPDEV_LABEL_LANGS`.
- Searching labels: first `aot_query.py label <text>` (see **AOT metadata index**; indexed languages only). Fallback: label texts live in `<XPPDEV_PACKAGES_DIR or repo>\<Package>\<Model>\AxLabelFile\LabelResources\<lang>\<LabelFile>.<lang>.label.txt`, one `ID=Text` per line (`;` lines are comments). Grep the en-US files for the text, then reference it as `@<LabelFile>:<ID>` (or `@SYSnnnn` for legacy SYS labels). Prefer an exact text match; show the user any near matches when unsure.

## Patterns
- Batch and processing jobs: **SysOperation** (controller, service, data contract).
- Hooking standard code: **CoC first**; event handlers only where CoC isn't possible.
- Always `select forUpdate` before `update()`; never update a buffer that wasn't selected for update.
- `ttsbegin`/`ttscommit` only in the outermost caller, not in helper methods.
- A plain `insert()` doesn't need its own transaction; `ttsbegin`/`ttscommit` isn't mandatory there. Don't flag it in review.
- Prefer set-based `update_recordset` / `insert_recordset` / `delete_from` over row-by-row loops.
- `skipDataMethods`, `skipDatabaseLog`, `skipEvents` and the other `skip*` methods are used sometimes, but only when the user asks or approves, since they bypass table logic.
- No `doInsert` / `doUpdate` / `doDelete` without explicit approval.

## Branch flow (git only)
The user does the preparation; just tell them the steps:
1. Stop the AOS.
2. `git checkout <XPPDEV_BASE_BRANCH>`, `git fetch`, `git pull`.
   When the user says the pull is done, run the repo index staleness check and propose `/d365fo-devkit:xpp-dev index repo create` if stale.
3. Build `<XPPDEV_BASE_BRANCH>`.
4. Wait for the user to say something like "build is ok, continue work with branch".
5. Create the branch from `<XPPDEV_BASE_BRANCH>` named by `XPPDEV_BRANCH_PATTERN`.

Commit only when the user asks.

- The user switches branches in Visual Studio. Check the current branch (`git branch --show-current`) only when the user asks.
- Uncommitted changes made while on the base branch are fine; they are carried over to the new branch. Don't warn about it.
- Checkout, cherry-pick or merge that changes files in `<Model>/bin` (e.g. dll from a C# project): AOS, AOS app pool, batch service and DIXF service must be stopped first, since they lock those files. Confirm with the user before running it.
- `<Model>/bin/*.dll` belongs in the commit whenever it changed.
- Never edit `.gitignore`; only suggest changes to the user when needed.

### Moving work from an old branch (git only)
Use when the user has an old branch (e.g. `<branch>_OLD`) and a fresh branch from the base branch, and wants the old commits moved.
1. Deep verify (read-only), via a subagent to keep context small. It reports:
   - both branches, merge-base with the base branch, how many commits the base branch moved since;
   - every old-only commit (`git log --no-merges <base>..<old>`), any merges, `--stat` per commit;
   - `git diff --name-status -M <merge-base> <old>`: adds, renames, binaries (`<Model>/bin/*.dll`);
   - files also changed in the base branch since the merge-base (conflict risk);
   - references in the base branch to renamed or removed objects;
   - suspicious items: scratch jobs (e.g. `RunnableClass1`), edits outside the ticket scope, VS solutions (.sln/.rnrproj/.csproj) in the commits.
2. Grill the user: with the `mattpocock-skills:grilling` skill ("grill-me") if installed, otherwise in AskUserQuestion rounds.
   Cover: pick method (default `git cherry-pick -n <c1> <c2> ...`, oldest first, staged, no commit), scratch/WIP objects,
   binaries (default: take now, rebuild before PR), out-of-scope edits, VS solutions for the task, renames vs stored setup data,
   AOS/services state for `bin` files, fate of the old branch (default: keep, the user deletes it).
3. Execute: check `git status` is clean, run `git cherry-pick -n ...`. On a conflict, stop and report.
4. Verify: the staged patch equals the old branch patch from the merge-base
   (`git diff --cached -M --binary <base>` vs `git diff -M --binary <merge-base> <old>`, compared without `index` lines);
   `.rnrproj` items match the picked objects.
5. Update the repo's task note, if it keeps one (VS solutions, changed objects, open questions, to-dos). Commit only on request.

Example: 2 WIP commits, 18 files, 3 class renames, C# dll and its C# project, X++ VS project; no conflicts, patch identical.

## VS solutions
- A task may use several VS solutions under `XPPDEV_VSPROJECTS_DIR`: X++ (`.rnrproj`) and C# (`.csproj`, e.g. a service client that builds a dll).
- Record all of them in the repo's task note, if it keeps one (format in CLAUDE.md). Never infer them; ask if not named.
- Add every new or extended AOT object to the task's X++ `.rnrproj`. Projects are usually named after the branch, but the ticket number can differ.
- A C# project builds a dll that an X++ project references (HintPath to the C# `bin\Debug`); the X++ build copies it to `<Model>/bin`.
- Changing an existing object that is not yet in the task's X++ project: tell the user which object and what changed, and wait for acceptance. Add the object to the project only after the user accepts the change.

## Build
- Ask for permission before every build.
- Logs are huge: redirect output to a log file in the scratchpad and report only the filtered errors and warnings, never the full log.
- Task with more than one solution: ask the user how the build works for this task (order, configuration), record it as `Build:` in the task note and follow it.
  After a few such tasks, propose a general rule here.
- Confirm the exact build command with the user the first time, then record it in CLAUDE.md.
- X++ build mechanics: the `trud-d365fo-xpp:d365-xpp-compile` skill if installed (xppc on the task's .rnrproj; this skill's "always ask first" overrides its "compile without waiting to be asked"); otherwise ask the user for the build command.

## Reuse existing methods
- Before writing a new helper (amounts, totals, finds, exists, validations), do a quick check for an existing method on the standard table/class (e.g. `CustInvoiceTable.displayInvoiceAmount()` for FTI gross total).
- Keep that check cheap: one targeted grep or xref on the obvious table/class. If finding a fit needs deeper analysis (many classes, call chains, frameworks), ask the user first; they may do the research themselves while you work on something else.
- Propose the found method with its trade-offs (exactness, cost, security checks) before using it.

## AOT metadata index
Needs `XPPDEV_AOT_INDEX_DIR` (and `XPPDEV_PACKAGES_DIR`, `XPPDEV_D365PU_VERSION` for the standard DB).
SQLite index of AOT definitions: objects (type, model, path, extends, implements, extension/CoC target), methods
(signature + line in the file), table fields, indexes, relations, event handlers, labels (languages of `XPPDEV_LABEL_LANGS`).
It answers "what exists, where, and what it looks like". "Who uses it" stays with xref.

- Files in `XPPDEV_AOT_INDEX_DIR`: `repo_<ddMMyy>_metadata.db` (repo models, small, seconds) and `<version>_metadata.db`, e.g.
  `10_0_45_metadata.db` (standard models without the repo's symlinked ones, ~300 MB, ~30 s). A build replaces older DBs of the same kind.
- Use it before Glob/Grep/Read on AOT XML, then Read only the needed lines (`line` column):
  `python "<skill-dir>/scripts/aot_query.py" --index-dir "<XPPDEV_AOT_INDEX_DIR>" [--scope repo|aot] <cmd> <arg>`
  | cmd | returns |
  |---|---|
  | `find <name>` | objects by name (`*` wildcard) |
  | `ext <target>` | all extensions of an object (table/form/EDT/enum/menu extensions, CoC classes) |
  | `coc <target>` | CoC classes with their methods (`SalesTable` also matches form data sources `SalesTable.*`) |
  | `handlers <target>` | event handlers (prefix match, e.g. `SalesTable` or `SalesTable.SalesLine`) |
  | `methods <object>` / `sig <object>.<method>` | signatures with file line |
  | `fields <table>` | fields of a table and its extensions |
  | `label <text>` / `label @File:Id` / `label @SYS12345` | labels |
  | `sql "<query>"` | raw SQL (tables: element, method, field, idx, relation, handler, label) |
  Without `--scope`, both DBs are queried; column `src` is `repo` or the version (e.g. `10_0_45`).
- The repo DB is a snapshot from its build; for objects changed since then, read the files directly.
- Staleness check (git only): the repo DB is stale when its mtime is older than `.git/FETCH_HEAD` mtime or the last commit on
  the current branch (`git log -1 --format=%ci`). Report the DB date and propose a rebuild; never rebuild unasked.
- No DB found: say so and offer the build.
- Build: `python "<skill-dir>/scripts/aot_index.py" repo --source "<repo root>" --index-dir "<XPPDEV_AOT_INDEX_DIR>" --langs "<XPPDEV_LABEL_LANGS>"` or
  `... aot --version <XPPDEV_D365PU_VERSION> --index-dir "<XPPDEV_AOT_INDEX_DIR>" --packages-dir "<XPPDEV_PACKAGES_DIR>" --langs "<XPPDEV_LABEL_LANGS>"`.
  Run it in the background and report only the summary lines (db, files, rows, size_mb, seconds). Watch free disk space.
- If plain `python` is not found (stale PATH), use `XPPDEV_PYTHON`.

### Triggers
- `/d365fo-devkit:xpp-dev index repo create`: build the repo DB.
- `/d365fo-devkit:xpp-dev index aot create`: build the standard DB for `XPPDEV_D365PU_VERSION`.
- `/d365fo-devkit:xpp-dev index find <cmd> <arg> [in repo|in aot]`: run `aot_query.py [--scope repo|aot] <cmd> <arg>`,
  e.g. `/d365fo-devkit:xpp-dev index find ext CustFreeInvoice in repo`. `/d365fo-devkit:xpp-dev index find <name>` alone means `find <name>`.
  Without `in …`, query both. Reply with the rows in a code block.
- Platform update: when the user announces a new D365 version, update `XPPDEV_D365PU_VERSION` and ask
  "Rebuild the AOT index for <version>?". On yes, run `/d365fo-devkit:xpp-dev index aot create`.
- New task: when the repo's task commands (CLAUDE.md) start or continue a task, run the staleness check and propose `/d365fo-devkit:xpp-dev index repo create` if stale.
- Branch flow: after `git pull` on the base branch, the same check and proposal.

## Finding usages and keeping context small
- For "where is X used", callers or impact analysis, use the `trud-d365fo-xpp:d365-xpp-xref` skill (cross-reference DB) if installed, instead of grepping `XPPDEV_PACKAGES_DIR`. Otherwise use the AOT metadata index and targeted file searches, or an Explore subagent for wide ones.
- For definitions (paths, signatures, extensions, CoC, handlers, fields, labels), use the **AOT metadata index**.
- Read large AOT XML files in parts (the needed method or node only), not whole.
- Hand wide searches across many models to an Explore subagent and keep only its conclusion.
- When a ticket is done, remind the user to `/clear`. When a session gets long, suggest `/compact` with what to keep (ticket, changed files, open issues).
- Save newly learned rules, never only in the chat:
  - repo-specific (naming, build command, config): CLAUDE.md;
  - general: in the plugin source at `XPPDEV_PLUGIN_SRC`, after the user approves (commit/PR only on request).
    Never edit the installed plugin copy. Without `XPPDEV_PLUGIN_SRC`, propose the change as text.
- After any change to this skill (or to the repo's workflow rules in CLAUDE.md), ask the user whether to update the readme at `XPPDEV_README_PATH`. Update it only after a yes.

## Switching tasks and time tracking
Repo-specific; see CLAUDE.md if the repo defines task commands.

## Checklist before handing over code
- [ ] Correct model and prefix; no standard objects modified
- [ ] CoC preferred; SysOperation for jobs
- [ ] All user-facing text uses allowed labels (new ones only if the user said so, all `XPPDEV_LABEL_LANGS`)
- [ ] `forUpdate` before `update()`, tts in the outermost caller, set-based where possible
- [ ] No `do*` or `skip*` calls without approval
- [ ] Objects added to the task's X++ project; changed `<Model>/bin/*.dll` included
