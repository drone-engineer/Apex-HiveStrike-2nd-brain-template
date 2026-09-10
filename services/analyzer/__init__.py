"""Apex HiveStrike ULog 비행 로그 이상 진단 패키지."""

__all__ = ["AnalysisReport", "ULogAnalyzer", "ULogParseError"]


def __getattr__(name: str):
    if name in {"AnalysisReport"}:
        from services.analyzer.schemas import AnalysisReport

        return AnalysisReport
    if name in {"ULogAnalyzer", "ULogParseError"}:
        from services.analyzer.ulog_analyzer import ULogAnalyzer, ULogParseError

        return ULogParseError if name == "ULogParseError" else ULogAnalyzer
    raise AttributeError(name)
