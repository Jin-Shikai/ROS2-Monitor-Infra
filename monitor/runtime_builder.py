"""Reusable builders for monitor-side routing and component wiring."""

from __future__ import annotations

from typing import Any

from config_model import ExporterSpec, MonitoredSourceSpec, TransformerSpec
from data_record import DataRecord
from exporter import Dispatcher, Exporter
from exporters import resolve_data_record_exporter_class
from pipeline import build_converter_chain
from transformer import (
    FieldExtractor,
    OnChangeFilter,
    RateThrottler,
    Transformer,
    TransformerPipeline,
)


TRANSFORMER_REGISTRY: dict[str, type[Transformer]] = {
    "FieldExtractor": FieldExtractor,
    "RateThrottler": RateThrottler,
    "OnChangeFilter": OnChangeFilter,
}


def build_transformer_pipeline(
    specs: list[TransformerSpec] | None,
    logger: Any,
) -> TransformerPipeline:
    chain: list[Transformer] = []
    for spec in specs or []:
        if not spec.type:
            logger.warn(f"Transformer spec missing 'type'; skipping: {spec.raw}")
            continue
        cls = TRANSFORMER_REGISTRY.get(spec.type)
        if cls is None:
            logger.warn(f"Unknown transformer type: {spec.type}; skipping.")
            continue
        try:
            chain.append(cls(**spec.kwargs))
        except Exception as ex:
            logger.error(f"Failed to build transformer {spec.type}: {ex}")
    return TransformerPipeline(chain)


def sanitize_source_name(source_name: str) -> str:
    return source_name.replace("/", "_") or "_root"


def build_data_record_dispatcher(
    specs: list[ExporterSpec],
    output_dir: str,
    session_id: str,
    logger: Any,
    label: str = "Dispatcher",
    source_name: str | None = None,
) -> Dispatcher[DataRecord]:
    dispatcher: Dispatcher[DataRecord] = Dispatcher(label=label)

    if not specs:
        if source_name is not None:
            return dispatcher
        specs = [ExporterSpec.from_dict({"type": "file"})]

    suffix_default = sanitize_source_name(source_name) if source_name else ""
    for spec in specs:
        if not spec.type:
            logger.warn(f"Exporter spec missing 'type'; skipping: {spec.raw}")
            continue
        try:
            cls = resolve_data_record_exporter_class(spec.type)
        except (KeyError, ImportError, AttributeError, TypeError, ValueError) as ex:
            logger.warn(f"Cannot resolve exporter '{spec.type}': {ex}")
            continue
        kwargs = dict(spec.kwargs)
        if spec.type == "file":
            kwargs.setdefault("output_dir", output_dir)
            kwargs.setdefault("session_id", session_id)
            if suffix_default:
                kwargs.setdefault("filename_suffix", suffix_default)
        try:
            dispatcher.add(cls(**kwargs))
            logger.info(
                f"Exporter enabled: {spec.type}"
                + (f" (source={source_name})" if source_name else "")
            )
        except Exception as ex:
            logger.error(f"Failed to build exporter {spec.type}: {ex}")
    return dispatcher


class MonitorRuntime:
    """Owns monitor-side dispatchers and converter/verdict chains."""

    def __init__(self, config, session_id: str, logger: Any):
        self.config = config
        self.session_id = session_id
        self.logger = logger
        self.dispatcher = build_data_record_dispatcher(
            config.exporters,
            config.output_dir,
            session_id,
            logger,
        )
        self.converter_dispatcher: Dispatcher[DataRecord] = Dispatcher(
            label="Converters"
        )
        self.source_dispatchers: list[Dispatcher[DataRecord]] = []
        self.verdict_dispatchers: list[Dispatcher] = []
        self._build_converter_chains()

    def _build_converter_chains(self) -> None:
        for spec in self.config.converters:
            built = build_converter_chain(
                spec, self.config.output_dir, self.session_id, self.logger
            )
            if built is None:
                continue
            converter_exporter, verdict_dispatcher = built
            self.converter_dispatcher.add(converter_exporter)
            self.verdict_dispatchers.append(verdict_dispatcher)

    def emit_session_start(self) -> None:
        self.dispatcher.export(
            DataRecord.make_session_start(self.session_id, self.config.raw)
        )

    def emit_session_end(self, stats: dict) -> None:
        self.dispatcher.export(
            DataRecord.make_session_end(self.session_id, stats)
        )

    def export_for(self, spec: MonitoredSourceSpec, source_name: str) -> Exporter[DataRecord]:
        if spec.exporters:
            sub = build_data_record_dispatcher(
                spec.exporters,
                self.config.output_dir,
                self.session_id,
                self.logger,
                label=f"Exporters[{source_name}]",
                source_name=source_name,
            )
            self.source_dispatchers.append(sub)
            target: Exporter[DataRecord] = sub
        else:
            target = self.dispatcher

        converter_exporter = self.converter_dispatcher

        class TeeExporter(Exporter[DataRecord]):
            def export(self, record: DataRecord) -> None:
                target.export(record)
                converter_exporter.export(record)

        return TeeExporter()

    def close_all(self) -> None:
        self.dispatcher.close_all()
        self.converter_dispatcher.close_all()
        for dispatcher in self.source_dispatchers:
            dispatcher.close_all()
        for dispatcher in self.verdict_dispatchers:
            dispatcher.close_all()
