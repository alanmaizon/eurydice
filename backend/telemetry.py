# Thin re-export — source of truth is engine/telemetry/collector.py
from engine.telemetry.collector import *  # noqa: F401,F403
from engine.telemetry.collector import get_collector as get_collector
from engine.telemetry.collector import TelemetryCollector as TelemetryCollector
