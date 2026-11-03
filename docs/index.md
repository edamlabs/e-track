---
hide:
  - navigation
  - toc
---

<div class="rx-hero">
  <img src="assets/logo.svg" alt="e-track">
  <p>Run tracking for agent systems. A source turns a framework's run into <strong>one event model</strong>; the
  model travels on a <strong>structlog channel</strong> of its own; a bus fans it out to <strong>parallel
  sinks</strong>, each reading the partial view it declares.</p>
</div>

Part of the **EDamLabs eager series**: EDamLabs' own e- products ([EDamLabs families](https://github.com/edamlabs/e-workbench#identity)).

<div class="rx-grid">
  <div><h3>One record</h3><p><code>RunEvent</code>: kind × phase × part, a span tree any client rebuilds without the framework that made it.</p></div>
  <div><h3>The log is the bus</h3><p>A structlog channel validates, publishes and forwards; the host's logging is never configured.</p></div>
  <div><h3>Never blocks</h3><p>Publish returns at once from any thread; a slow sink drops and counts, never slows the run.</p></div>
  <div><h3>Every backend</h3><p>OTLP spans and logs in GenAI, OpenInference and Langfuse dialects at once; live replay for a canvas.</p></div>
</div>

```bash
uv add "e-track[langgraph,otel]"
```

[Get started](introduction.md){ .md-button .md-button--primary } [Usage](usage.md){ .md-button }
