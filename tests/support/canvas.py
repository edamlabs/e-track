"""tests/support/canvas: the viewer's canvas driven by a real browser — a sampler inside the page, read from the test.

The sampler runs in the page every 40 ms and records what a person would see: the ids of the nodes drawn, how many are
hidden, the viewport's transform, and which nodes are lit. The test asserts on the whole record, never on one frame."""

from typing import TYPE_CHECKING, Any, Final

import msgspec

if TYPE_CHECKING:
    from playwright.async_api import Page

SAMPLER: Final[str] = """() => {
  window.__samples = [];
  window.__sampler = setInterval(() => {
    const nodes = [...document.querySelectorAll('.react-flow__node')];
    window.__samples.push({
      ids: nodes.map((node) => node.dataset.id).sort(),
      hidden: nodes.filter((node) => getComputedStyle(node).visibility === 'hidden').length,
      viewport: document.querySelector('.react-flow__viewport')?.style.transform ?? '',
      running: [...document.querySelectorAll('.react-flow__node:has(.stage.running)')].map((node) => node.dataset.id),
    });
  }, 40);
}"""
SETTLED: Final[str] = """(expected) => {
  const counts = document.querySelector('.react-flow__node[data-id="model"] .counts')?.textContent ?? '';
  return counts.includes(expected) && !document.querySelector('.stage.running');
}"""


class Sample(msgspec.Struct, frozen=True):
    """One look at the canvas."""

    ids: list[str]
    hidden: int
    viewport: str
    running: list[str]


class Canvas:
    """The served canvas in one browser page, on one thread."""

    __slots__ = ("_page",)

    def __init__(self, page: Page) -> None:
        self._page = page

    ##### PUBLIC #####

    @property
    def page(self) -> Page:
        """The browser page showing the canvas."""
        return self._page

    async def drawn(self, count: int) -> None:
        """Wait until the declared graph is drawn: `count` nodes, none hidden, the first fit done."""
        await self._page.wait_for_function(
            """(count) => {
              const nodes = [...document.querySelectorAll('.react-flow__node')];
              return nodes.length === count && nodes.every((node) => getComputedStyle(node).visibility !== 'hidden');
            }""",
            arg=count,
        )
        await self._page.wait_for_timeout(400)

    async def watch(self) -> None:
        """Start the in-page sampler."""
        await self._page.evaluate(SAMPLER)

    async def settled(self, expected: str) -> None:
        """Wait until the model node shows `expected` among its counts and nothing runs."""
        await self._page.wait_for_function(SETTLED, arg=expected)

    async def samples(self) -> list[Sample]:
        """Every look the sampler took, oldest first."""
        raw: Any = await self._page.evaluate("() => { clearInterval(window.__sampler); return window.__samples; }")
        return msgspec.convert(raw, list[Sample])

    async def text(self, node: str, part: str) -> str:
        """The text of one part (`counts`, `title`, `kind`…) of a drawn node."""
        return await self._page.locator(f'.react-flow__node[data-id="{node}"] .{part}').first.inner_text()

    async def classes(self, node: str) -> frozenset[str]:
        """The classes a drawn node's stage wears: its status (`done`, `idle`…), `last`, its family."""
        stage = self._page.locator(f'.react-flow__node[data-id="{node}"] .stage')
        return frozenset(str(await stage.get_attribute("class")).split())

    async def border(self, node: str) -> str:
        """The computed colour of a node's border: its family."""
        stage = self._page.locator(f'.react-flow__node[data-id="{node}"] .stage')
        return await stage.evaluate("(element) => getComputedStyle(element).borderTopColor")

    async def link(self, state: str) -> None:
        """Wait until the bar shows the event stream in `state` (`live`, `reconnecting`…)."""
        await self._page.locator(f".link.{state}").wait_for()

    async def boxes(self) -> tuple[dict[str, float], dict[str, float], list[dict[str, float]]]:
        """Where the canvas pane, the panel and every drawn node sit on the screen."""
        found: Any = await self._page.evaluate(
            """() => {
              const box = (element) => { const r = element.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height}; };
              return [box(document.querySelector('.canvas')), box(document.querySelector('.panel')),
                      [...document.querySelectorAll('.react-flow__node')].map(box)];
            }"""
        )
        return found[0], found[1], found[2]

    async def runs(self) -> list[str]:
        """The runs the run picker offers, oldest first."""
        return await self._page.locator("header label:has-text('run') option").all_inner_texts()

    async def pick(self, index: int) -> None:
        """Choose the run at `index` in the run picker."""
        await self._page.locator("header label:has-text('run') select").select_option(index=index)

    async def arcs(self, state: str) -> int:
        """How many arcs are drawn in a state (`walked`, `hot`)."""
        return await self._page.locator(f".react-flow__edge.{state}").count()
