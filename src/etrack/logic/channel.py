"""logic/channel: EventChannel — the log that carries the events: reserved keys in, validated record out, fanned out.

The channel is a structlog logger of its own (`wrap_logger`), so it never touches the host's configuration and the
host's level never drops an event. Its chain: the bound context (`run_id`, `thread_id`) merged in → the keys
validated into the channel's model (`RunEvent` or a project's subclass) → the record published on the bus → a
narrowed line (`LogView` by default) forwarded to the host's own `etrack` logger at the phase's level, where the
host's rendering and filtering decide what is printed. Without a bus the channel stands alone: validated, forwarded,
published nowhere — run tracking as log lines, no sink and no worker; hand it a bus to add the sinks. Any code may emit: `channel.log.info("run.event", kind=…)`
with the reserved keys, or `channel.emit(event)` with a record already built — the same chain either way.

Like structlog, any other key travels too: a keyword the model does not declare, or a key bound with
`structlog.contextvars.bind_contextvars` — on this call or around a whole run — lands in the record's `attributes`, so
every sink sees it (OTLP as span attributes, the HTTP driver in the body) and the forwarded line carries it flat.
Explicit `attributes` win over a bound key of the same name; a model's own field is never an extra. `strict=True`
turns that off: a key the model does not declare is refused (`ChannelError`), and a record already built keeps
only what it was built with."""

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

import msgspec
import structlog

from etrack.infra.errors import ChannelError
from etrack.infra.logger import NAME
from etrack.models.event import EventPhase, EventView, LogView, RunEvent

if TYPE_CHECKING:
    from collections.abc import Mapping

    from structlog.typing import EventDict, WrappedLogger

    from etrack.ports.bus import BusPort

EVENT: Final[str] = "run.event"
### structlog's own keys, never fields of the record.
RESERVED: Final[frozenset[str]] = frozenset({"event", "_record"})
EMPTY: Final[tuple[object, ...]] = (None, "")
LEVELS: Final[Mapping[EventPhase, int]] = MappingProxyType(
    {
        EventPhase.START: logging.INFO,
        EventPhase.DELTA: logging.DEBUG,
        EventPhase.END: logging.INFO,
        EventPhase.ERROR: logging.ERROR,
        EventPhase.INSTANT: logging.INFO,
    }
)


class EventChannel:
    """One emission point per process: validate, publish, forward — then the line is dropped, nothing is rendered here."""

    __slots__ = ("_bus", "_fields", "_forward", "_host", "_log", "_model", "_strict")

    def __init__(
        self,
        bus: BusPort | None = None,
        model: type[RunEvent] = RunEvent,
        forward: type[EventView] | None = LogView,
        *,
        strict: bool = False,
    ) -> None:
        self._bus = bus
        self._model = model
        self._strict = strict
        self._fields = frozenset(field.name for field in msgspec.structs.fields(model))
        self._forward = forward
        self._host: Any = structlog.get_logger(NAME)
        self._log: Any = structlog.wrap_logger(
            structlog.ReturnLogger(),
            processors=[
                structlog.contextvars.merge_contextvars,
                self._emit_validate,
                self._emit_publish,
                self._emit_forward,
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
        )

    ##### PRIVATE #####

    def _emit_validate(self, _logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        given = {key: value for key, value in event_dict.items() if key not in RESERVED}
        extras = {key: value for key, value in given.items() if key not in self._fields}
        match event_dict.get("_record"), self._strict:
            case RunEvent() as built, True:
                record = built
            case RunEvent() as built, False:
                record = msgspec.structs.replace(built, attributes={**extras, **built.attributes}) if extras else built
            case _, True if extras:
                msg = f"not a {self._model.__name__} — strict: no field {sorted(extras)}"
                raise ChannelError(msg)
            case _:
                known = {key: value for key, value in given.items() if key in self._fields}
                own = known.get("attributes", {})
                ### a malformed `attributes` stays malformed: validation refuses it, the merge never hides it.
                merged = {**extras, **own} if isinstance(own, dict) else own
                record = self._emit_convert({**known, "attributes": merged})
        return {"event": event_dict.get("event", EVENT), "_record": record}

    def _emit_convert(self, fields: dict[str, Any]) -> RunEvent:
        try:
            return msgspec.convert(fields, self._model)
        except msgspec.ValidationError as failure:
            msg = f"not a {self._model.__name__} — {failure}"
            raise ChannelError(msg) from failure

    def _emit_publish(self, _logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        match self._bus:
            case None:
                pass
            case bus:
                bus.publish(event_dict["_record"])
        return event_dict

    def _emit_forward(self, _logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        record: RunEvent = event_dict["_record"]
        match self._forward:
            case None:
                pass
            case view:
                ### empty fields stay off the line: a host's log is read by people and grepped by machines.
                ### the extras ride flat, as structlog keys do; a field of the view wins over an extra of its name.
                line = {
                    **record.attributes,
                    **{
                        key: value
                        for key, value in msgspec.structs.asdict(view.project(record)).items()
                        if value not in EMPTY
                    },
                }
                self._host.log(LEVELS[record.phase], event_dict["event"], **line)
        raise structlog.DropEvent

    ############################################################

    ##### PUBLIC #####

    @property
    def log(self) -> Any:
        """The channel as a logger: `log.info("run.event", **reserved_keys)` validates, publishes and forwards."""
        return self._log

    @property
    def model(self) -> type[RunEvent]:
        """The record every emission is validated into."""
        return self._model

    def emit(self, event: RunEvent) -> None:
        """A record already built, through the same chain: published as is, forwarded narrowed."""
        self._log.info(EVENT, _record=event)
