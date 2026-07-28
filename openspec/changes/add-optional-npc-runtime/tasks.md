## 1. Compatibility Baseline and Graph Controls

- [x] 1.1 Add regression tests that prove legacy document uploads, assistant conversations, chat requests, history responses, and memory retrieval retain their current defaults.
- [x] 1.2 Add a migration and model/schema fields for document `graph_mode` and conversation `retrieval_mode`, using backward-compatible defaults.
- [x] 1.3 Extend document upload and serialization APIs to validate `inherit|enabled|disabled` and expose a clear skipped/unavailable graph state.
- [x] 1.4 Update document worker job creation so disabled graph mode never queues graph extraction while text/vector indexing still reaches ready.
- [x] 1.5 Add owner-only idempotent graph build/rebuild endpoints for text-ready documents and cover revision, duplicate-job, unavailable-service, and cross-user cases.
- [x] 1.6 Make document retrieval honor `auto|off|vector|hybrid`, including vector-only behavior and hybrid graph failure degradation.
- [x] 1.7 Add the upload graph switch, per-document build/rebuild controls, retrieval-mode setting, and independent text/graph statuses to the Vue UI.
- [x] 1.8 Run backend and frontend graph-control tests and update environment/configuration documentation.

## 2. Character Persistence and API

- [x] 2.1 Add character and conversation-member migrations/models with ownership indexes, soft deletion, ordering, overrides, and safe defaults.
- [x] 2.2 Add nullable message `character_id` plus immutable `speaker_name` snapshot and serialize both without changing legacy message payload behavior.
- [x] 2.3 Implement validated character schemas and owner-scoped CRUD, duplicate, archive, and avatar endpoints.
- [x] 2.4 Implement private avatar storage, MIME/size checks, authorized serving, replacement cleanup, and deletion cleanup.
- [x] 2.5 Implement conversation mode, runtime settings, and ordered member-management endpoints with mode/member validation.
- [x] 2.6 Add backend tests for character lifecycle, ownership isolation, soft deletion with history, avatar safety, and conversation membership.

## 3. Character Management Frontend

- [x] 3.1 Add typed character and conversation-runtime API clients plus Pinia stores with recoverable error states.
- [x] 3.2 Build character list/create/edit/duplicate/archive/delete UI with avatar, structured persona, greeting, examples, generation settings, and capability permissions.
- [x] 3.3 Add assistant/single-character/group selectors and ordered member management to the conversation interface.
- [x] 3.4 Render avatar and immutable speaker name on NPC messages while preserving the legacy assistant layout.
- [x] 3.5 Add frontend tests for character forms, ownership-safe error handling, mode switching, member validation, and legacy conversations.

## 4. Single-NPC Runtime

- [x] 4.1 Extract a reusable single-speaker executor from the current ChatService without changing assistant-mode tool loop, retries, streaming, citations, or idempotency.
- [x] 4.2 Implement deterministic layered prompt construction with untrusted character boundaries and server-side effective permission intersection.
- [x] 4.3 Route single-character conversations through the speaker executor and persist speaker attribution on complete, interrupted, and failed turns.
- [x] 4.4 Extend SSE and frontend stream handling with compatible speaker-start, speaker-done, token, done, and error attribution.
- [x] 4.5 Add integration tests for character prompt composition, unauthorized tool denial at prompt and execution, streaming, failure persistence, and legacy request compatibility.

## 5. Layered Memory and Compression

- [x] 5.1 Add memory scope, optional character, importance, validity, and replacement metadata plus summary, scene-state, and compression-job tables.
- [x] 5.2 Update Qdrant payloads, filters, outbox operations, rebuild handling, and conversation deletion for scoped memories.
- [x] 5.3 Implement structured scoped fact extraction, conflict/supersession handling, and owner-facing memory invalidation/restoration APIs.
- [x] 5.4 Implement asynchronous versioned rolling summaries with contiguous message boundaries, validation, retries, and no deletion of original messages.
- [x] 5.5 Implement revision-checked shared scene state and deterministic context-budget allocation across summaries, state, memories, evidence, and recent messages.
- [x] 5.6 Add memory and summary management UI showing scope, source, validity, coverage, regeneration, invalidation, and deletion controls.
- [x] 5.7 Add tests for private/shared retrieval isolation, legacy memories, supersession, summary failure fallback, concurrent state updates, context budgets, and deletion cleanup.

## 6. Multi-NPC Orchestration

- [x] 6.1 Implement `NpcOrchestrator` and persisted speaker plans for manual, mention, round-robin, and bounded automatic strategies.
- [x] 6.2 Validate automatic router structured output against enabled conversation members and implement deterministic fallback reason codes.
- [x] 6.3 Execute planned speakers sequentially with per-speaker persistence, context refresh, stream attribution, partial failure handling, and strict turn limits.
- [x] 6.4 Extend request idempotency so retries return or resume persisted group plans without duplicating messages or generations.
- [x] 6.5 Add group controls for routing strategy, explicit speaker, per-turn limits, active-speaker state, and partial failure recovery.
- [x] 6.6 Add backend/frontend tests for every routing strategy, unknown members, disabled members, limits, ordering, partial failure, retries, and observability metadata.

## 7. Optional Image and TTS Providers

- [x] 7.1 Add administrator-configured provider settings, capability registry, disabled-by-default feature flags, and startup validation without exposing secrets.
- [x] 7.2 Define image and TTS Provider interfaces and implement first OpenAI-compatible adapters with timeout, retry, MIME, and response-size enforcement.
- [x] 7.3 Add media task and message attachment migrations/models with ownership, provenance, idempotency, status, and private storage lifecycle.
- [x] 7.4 Implement text-first image/TTS task APIs, background execution, retry, authorized download, cleanup, and SSE media-status events.
- [x] 7.5 Resolve character media profiles only from allowed capabilities and enforce per-message, per-turn, and automatic-generation limits.
- [x] 7.6 Add frontend capability detection, manual image/TTS actions, audio playback, image display, progress, retry, and unavailable-provider states.
- [x] 7.7 Add tests for no-provider startup, secret redaction, duplicate requests, timeout/failure fallback, oversized/invalid media, cross-user access, and cleanup.

## 8. Security, Observability, Migration, and Release

- [x] 8.1 Add metrics and structured logs for routing, per-speaker generation, context allocation, compression, graph degradation, and media tasks without recording secrets or hidden reasoning.
- [x] 8.2 Add configurable rate, context, speaker, tool, graph, media size, and cost-oriented limits with safe production defaults.
- [x] 8.3 Run migration upgrade/downgrade tests against existing data and verify old conversations, messages, memories, documents, vectors, and graph facts remain usable.
- [x] 8.4 Run the full backend, frontend, RAG, isolation, deletion, streaming, and security suites and fix regressions.
- [x] 8.5 Update README, `.env.example`, startup guide, API documentation, architecture notes, and operator rollback instructions.
- [x] 8.6 Gate single NPC, group routing, memory compression, image, and TTS independently and document the staged enablement sequence.
