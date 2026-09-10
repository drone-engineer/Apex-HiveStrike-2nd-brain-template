"use client";

import { useEffect, useRef } from "react";
import type { ChartSeries } from "@/lib/api";

type PlotlyModule = typeof import("plotly.js-dist-min");

const plotlyCache: { current: PlotlyModule | null } = { current: null };

async function loadPlotly(): Promise<PlotlyModule> {
  if (!plotlyCache.current) {
    plotlyCache.current = await import("plotly.js-dist-min");
  }
  return plotlyCache.current;
}

export function FlightCharts({ charts }: { charts: ChartSeries[] }) {
  if (charts.length === 0) {
    return (
      <p className="text-sm text-hive-muted">
        이 로그에는 그릴 시계열이 없어 차트를 만들지 못했습니다.
      </p>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {charts.map((chart) => (
        <ChartCard key={chart.id} chart={chart} />
      ))}
    </div>
  );
}

function ChartCard({ chart }: { chart: ChartSeries }) {
  const elRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = elRef.current;
    if (!el) {
      return;
    }
    let cancelled = false;
    const run = async () => {
      const Plotly = await loadPlotly();
      if (cancelled || !elRef.current) {
        return;
      }
      const isPath = chart.kind === "path";
      await Plotly.newPlot(
        el,
        [
          {
            x: chart.x,
            y: chart.y,
            mode: isPath ? "lines+markers" : "lines",
            type: "scatter",
            marker: { size: isPath ? 4 : 3, color: "#f5a524" },
            line: { color: "#f5a524", width: 2 },
            hoverinfo: "x+y",
          },
        ],
        {
          paper_bgcolor: "#121a2b",
          plot_bgcolor: "#121a2b",
          font: { color: "#e8eefc", size: 12 },
          margin: { t: 36, r: 16, b: 48, l: 52 },
          title: { text: chart.title, font: { size: 14 } },
          xaxis: {
            title: chart.x_label,
            gridcolor: "#243049",
            zerolinecolor: "#243049",
            scaleanchor: isPath ? "y" : undefined,
          },
          yaxis: {
            title: chart.y_label,
            gridcolor: "#243049",
            zerolinecolor: "#243049",
          },
        },
        { displayModeBar: false, responsive: true }
      );
    };
    void run();
    return () => {
      cancelled = true;
      if (el && plotlyCache.current) {
        plotlyCache.current.purge(el);
      }
    };
  }, [chart]);

  return <div ref={elRef} className="h-80 w-full rounded-xl border border-hive-line bg-hive-panel" />;
}
