# Phase 1 desktop engine review

22 November 2026. Scope includes typed requests, routing, application control, source reading, approval, learning and the boundary for future memory.

## Verdict

Keep the engine. Its strongest feature is that Python can check the recipient and the actual text before a model's suggestion affects someone else. Its weakest feature is that getting from a natural request to that check depends on which route the sentence takes and what Windows reports at that instant.

The reported 96 correct classifications out of 100 measure Laya's choice of area. A correct classification earns no credit for opening the wrong group, submitting a malformed search or answering from a preview. On Windows a single WhatsApp search field appeared eleven times under the same accessibility ID, and focusing it moved input to a separate WebView process. A simulated control tree hid both problems.

The patched Windows flow opened the requested group. One run read two visible messages, summarized them in 41 seconds including a model timeout, and treated “yes” as a request for the reply wording. An earlier run had correctly identified the group but incorrectly summarized the navigation request. The revised prompt asks only about the participants' discussion. A separate self-chat test read back the exact unsent draft after typing once. A successful accessibility write alone had previously left that composer empty. Live delivery, microphone input, Gemini replacement and remote PDF reading were outside these live checks.

## Where the design works

- The same typed pipeline serves as the entry point for voice transcripts. Fast rules and bounded model calls keep simple actions affordable. The local model call count and elapsed time in the CLI make slow paths visible.
- The task executor represents verified, dispatched, uncertain and failed outcomes separately. The verified draft and send actions demonstrate how to apply that distinction to a user-visible result.
- Source readers can report how many pages or messages they read. When a PDF is open in an unsupported viewer, reporting the missing source prevents a filename from turning into an invented document summary.

## Where the design breaks down

1. **A follow-up needs a target.** The pipeline keeps recent chat, pending question, last task and foreground window in separate places. A group summary followed by “yes” needs a conversation identity and the question it answers. A durable vault entry cannot authorize that reply. The next simplification should carry the target, requested action and evidence together through both routes.
2. **The two execution paths set different standards for success.** A verified search skill checks the query in a results URL. A generic keypress can tell that a key was pressed. Both facts are valid, but only the former answers “did it search for these words?” Give each common user task a completion check shared by the quick path and agent before adding tools.
3. **Read the scope before asking the model to summarize.** The WhatsApp sidebar contains names, snippets and timestamps formatted much like messages. Group summaries should name the verified group, distinguish quotations from replies, surface the outstanding question and report coverage. A local file PDF, a downloaded attachment and a remote Chrome viewer require different source checks.
4. **Measure recovery as part of the job.** Reopening WhatsApp three times moved no closer to a draft. Track whether a retry acquired new evidence about the same target. When it did not, stop with the exact missing observation. Saved examples should require a verified outcome.

## What to take from the Jarvis reference

Its shared orchestration layer is worth borrowing as a design constraint. Text, voice, a future overlay and Obsidian should enter through one task interface with the same approvals and completion checks. Otto already has the beginnings of this in its pipeline and executor. The reference describes how requests and memories travel. It provides no measured evidence for Windows focus, message delivery or recovery from partial actions.

Keep current-task state in process. Persist preferences, user-approved facts, source references and confirmed outcomes in Obsidian later. In particular, keep a remembered contact separate from the identity of the chat on screen now. A second interface, a heavier model, MCP and scheduled work can all reuse the engine once its completion checks hold up.

## Phase 1 exit test

Run the same tasks from typed and spoken input, starting from different windows, a populated field, an ambiguous name and a lost focus. Record correct target, exact final contents, whether anything was sent, reported coverage, elapsed time and whether recovery needed the user. Count an honest refusal separately from successful completion. Any wrong-recipient send, accidental submit or false claim of success blocks promotion. The first three tasks should be find/read/draft in a group, replace a populated search field, and summarize a PDF opened from Chrome.
