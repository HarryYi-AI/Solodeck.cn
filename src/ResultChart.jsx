import React from "react";
import {
  Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis
} from "recharts";

export default function ResultChart({ chart }) {
  if (!chart) return null;
  if (chart.type === "bar") {
    return (
      <div className="result-chart" aria-label="分析结果图表">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chart.data || []} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="#e8eeeb" vertical={false} />
            <XAxis dataKey={chart.x} tick={{ fontSize: 10 }} interval={0} tickFormatter={(value) => String(value).slice(0, 8)} />
            <YAxis tick={{ fontSize: 10 }} width={42} />
            <Tooltip formatter={(value) => [`${value}${chart.suffix || ""}`, "结果"]} />
            <Bar dataKey={chart.y} fill="#14745d" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (chart.type === "interval") {
    const low = Number(chart.ci?.[0] ?? 0);
    const high = Number(chart.ci?.[1] ?? 0);
    const estimate = Number(chart.estimate ?? 0);
    const data = [{ name: "效果区间", low, range: high - low, estimate }];
    return (
      <div className="result-chart" aria-label="效果置信区间">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 18, right: 18, left: 8, bottom: 18 }}>
            <CartesianGrid stroke="#e8eeeb" horizontal={false} />
            <XAxis type="number" domain={[Math.min(low, 0), Math.max(high, 0)]} tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" width={58} tick={{ fontSize: 10 }} />
            <ReferenceLine x={0} stroke="#d36b60" strokeDasharray="4 4" />
            <Bar dataKey="low" stackId="ci" fill="transparent" />
            <Bar dataKey="range" stackId="ci" fill="#65aa93" radius={4} />
            <Tooltip />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }
  return null;
}
