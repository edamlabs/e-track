---
hide:
  - navigation
  - toc
---

<div class="rx-hero">
  <img src="assets/logo.svg" alt="e-track">
  <p>See what your agents are doing. e-track turns every run of a <strong>LangGraph</strong> agent — its nodes, model
  calls, tools, MCP calls and subagents — into <strong>one stream of events</strong>, and sends it wherever you look:
  Langfuse, Phoenix, any OpenTelemetry backend, your own code, or a <strong>live canvas</strong> of the graph.</p>
</div>

Part of the **EDamLabs eager series**: EDamLabs' own e- products ([EDamLabs families](https://github.com/edamlabs/e-workbench#identity)).

<div class="rx-grid">
  <div><h3>One record</h3><p>Every span of a run becomes a <code>RunEvent</code>: what it is, where it sits in the tree, what it carried, what it cost. Backends and clients read the same thing.</p></div>
  <div><h3>Every backend at once</h3><p>OpenTelemetry spans and logs in the GenAI, OpenInference and Langfuse dialects together — Langfuse, LangSmith, Phoenix, Tempo, any collector.</p></div>
  <div><h3>A live canvas</h3><p>The agent's graph drawn as declared, lit as it runs, with a picker for every conversation. One line to serve it.</p></div>
  <div><h3>Never in the way</h3><p>Emitting costs the run ~5 µs. A slow or broken backend drops and counts — it never slows the agent or another backend.</p></div>
</div>

![The live viewer: the agent's declared graph lit by its run, the calls each node made, and the span tree with every span's input and output](assets/viewer.png)

```python
tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter())

# one conversation, one run
with tracker.track(thread="t1", config={}) as run:
    # your graph, untouched: the config carries the hook
    await agent.ainvoke(inputs, run.config)
```

[What it is](start/introduction.md){ .md-button } [Run it in 3 steps](start/quickstart.md){ .md-button .md-button--primary } [API at a glance](reference/api.md){ .md-button }
