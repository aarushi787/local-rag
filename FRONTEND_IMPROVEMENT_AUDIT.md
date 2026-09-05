# Local RAG frontend improvement audit

Date: 2026-09-04

## Product direction

This interface is an operations-critical private AI workspace, not a marketing site. The visual system should feel calm, precise, trustworthy, and fast to scan.

- Design system: Radix Themes, retained to avoid introducing a second component system.
- Visual variance: 5/10. Distinctive enough to feel intentional without distracting from document work.
- Motion: 3/10. Motion is limited to feedback and state changes.
- Information density: 6/10. Desktop favors operational context; mobile progressively hides secondary detail.
- Accent: one jade green accent for action, focus, privacy, and healthy state.

## Implemented in this pass

1. Replaced the generic centered welcome page with an asymmetric workspace layout.
2. Added a live workspace summary for document count, chunk count, response mode, scope, and active model.
3. Made response mode and search scope explicit on desktop while retaining compact mobile controls.
4. Replaced decorative AI sparkle imagery with document and privacy iconography.
5. Added a source counter and disabled the source control when no evidence exists.
6. Added a checking state so a slow health request does not immediately claim the server is offline.
7. Improved grounded answer hierarchy with a restrained evidence rail.
8. Combined the composer guidance into one compact footer and kept keyboard shortcuts discoverable.
9. Added `aria-current` to the active conversation and `aria-busy` during generation.
10. Kept the existing routes, labels, data flow, dialogs, and API contracts intact.

## Recommended next improvements

| Priority | Improvement | User value | Effort | Acceptance check |
|---|---|---:|---:|---|
| P0 | Open a citation at the exact source page and highlighted passage | Very high | Medium | Clicking a citation shows the matching page and quoted text |
| P0 | Add a health request timeout plus retry action | High | Low | A failed check resolves within 8 seconds and offers Retry |
| P0 | Add visual regression checks at 390, 768, 1280, and 1440 px | High | Medium | Key screens have approved snapshots at all four widths |
| P0 | Add complete keyboard operation for source details and dialogs | High | Low | All primary tasks pass a keyboard-only walkthrough |
| P1 | Show a latency breakdown per answer | High | Medium | First token, retrieval, reranking, generation, and total time are visible on demand |
| P1 | Add answer feedback tied to the exact retrieval trace | High | Medium | Helpful and incorrect reports include source IDs and model settings |
| P1 | Add document collections and saved search scopes | High | Medium | Users can reuse a named group such as Policies or Product Files |
| P1 | Stream source availability before the full answer finishes | Medium | Medium | Evidence appears as soon as retrieval completes |
| P1 | Add conversation filters for document, model, date, and owner | Medium | Medium | A user can narrow long history without changing page |
| P2 | Add side-by-side answer comparison for two response profiles | Medium | High | The same question can be evaluated without duplicating a conversation |
| P2 | Add an admin ingestion activity view | Medium | Medium | Queue, OCR, chunking, embedding, failures, and retries are visible |
| P2 | Add export bundles containing answer, sources, and settings | Medium | Medium | Export can reproduce why an answer was produced |
| P2 | Add multilingual query and source-language indicators | Medium | Medium | Users can see query language, source language, and translation state |

## RAG answer quality improvements with frontend support

1. Show retrieval mode, selected collection, and number of searched chunks before submission.
2. Let users choose concise, balanced, or evidence-heavy answer styles without editing prompts.
3. Display source coverage separately from similarity score. A high score is not the same as complete evidence.
4. Mark unsupported answer paragraphs when no citation maps to them.
5. Provide a one-click "answer only from selected sources" action in the evidence panel.
6. Add a "not found in my documents" outcome that is visually distinct from system failure.
7. Capture the user question, rewritten search query, retrieved chunk IDs, reranker scores, prompt version, and model version for evaluation.
8. Add a prompt-version label only inside the admin evaluation view, not the chat interface.

## Performance improvements

1. Lazy-load admin dialogs and document-management code as separate chunks.
2. Virtualize conversations and documents once either list exceeds 200 items.
3. Keep Markdown lazy loading and add syntax highlighting only when a code block is present.
4. Cache the latest successful health state so slow checks do not cause visual status flicker.
5. Preconnect only to the configured local API origin. Do not add external font or analytics requests.
6. Track interaction latency, first-token latency, and long tasks locally without transmitting telemetry.

## Accessibility and resilience checks

- Maintain at least 4.5:1 text contrast and a visible focus ring in both themes.
- Keep the skip link and semantic main, navigation, section, aside, and form regions.
- Respect reduced-motion preferences.
- Use text with every color-based status.
- Keep touch targets at least 44 px on mobile.
- Preserve user input when a request fails.
- Never describe a pending health check as an outage.

## Definition of done for the next frontend release

- Production build and type check pass.
- No console errors on first load, chat, sources, documents, connection, and admin dialogs.
- Keyboard-only workflow passes for new chat, send, stop, copy, citations, and dialogs.
- Light and dark themes pass contrast review.
- Responsive screenshots pass at four target widths.
- A real grounded answer shows correct citations and latency metrics.
- No API routes, persisted settings, or user permissions regress.
