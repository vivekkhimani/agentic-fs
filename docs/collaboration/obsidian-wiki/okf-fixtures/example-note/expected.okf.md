---
type: concept
title: Vector databases vs. agentic filesystem navigation
description: Why compounding markdown wikis beat re-retrieval for long-lived knowledge.
resource:
  - https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
  - https://github.com/vivekkhimani/agentic-fs/issues/108
tags:
  - rag
  - knowledge-base
  - agents
timestamp: 2026-06-16
---

# Vector databases vs. agentic filesystem navigation

RAG re-derives the same context on every query. The LLM-Wiki pattern instead *compiles* knowledge
into a persistent, cross-linked markdown corpus that the agent maintains over time.

See [[okf-interchange-format]] for how this corpus stays portable across tools.
