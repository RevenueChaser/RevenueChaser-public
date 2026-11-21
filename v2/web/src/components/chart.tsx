/** `chart-block`: uPlot on the web, and everything contract §10 says is shared with the phone's native chart.
 *
 * What this component refuses, on purpose:
 *   - **a second y-axis.** Contract §10: a price line behind value bars makes two unrelated scales look
 *     comparable. Two stacked panels on one x-axis is the shape instead, so this block draws one axis and the
 *     board asks for two blocks.
 *   - **a third series.** The categorical ramp `--c1 … --c6` is not in `ref/design-system/tokens.css` yet
 *     (contract §2.3, §14), so `seriesTokens` throws and this block says so in words rather than inventing a hue.
 *
 * uPlot's own stylesheet is imported for its positioning; the colours come from our tokens, in `components.css`.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

import type { ChartBody } from '../board/envelope';
import { amsterdamTime, num, parseAsof } from '../format/format';
import { Legend } from './panel';
import { SegmentedControl } from './primitives';
import { CategoricalChartBlocked, seriesTokens } from './series';

/** The token's resolved value, because a canvas takes a colour string and not a `var()`. */
function resolved(token: string, host: Element): string {
  return getComputedStyle(host).getPropertyValue(token).trim() || 'currentColor';
}

export type ChartBlockProps = {
  body: ChartBody;
  /** The envelope's `data_asof`: the as-of rule on a time chart, the method line otherwise (contract §10). */
  dataAsof: string | null;
  height?: number;
  label: string;
};

export function ChartBlock({ body, dataAsof, height = 220, label }: ChartBlockProps) {
  const host = useRef<HTMLDivElement | null>(null);
  const [axis, setAxis] = useState<'fixed' | 'fit'>(body.axis ?? 'fit');

  const tokens = useMemo(() => {
    try {
      return { names: seriesTokens(body.series.length), blocked: null as string | null };
    } catch (error) {
      if (error instanceof CategoricalChartBlocked) return { names: [], blocked: error.message };
      throw error;
    }
  }, [body.series.length]);

  const asofMs = parseAsof(dataAsof);

  useEffect(() => {
    const element = host.current;
    if (element === null || tokens.blocked !== null || body.series.length === 0) return;
    // A canvas-less environment (the unit tier's jsdom) still renders the legend, the method line and the
    // controls; only the drawing is skipped. The browser tier is what proves the drawing.
    let context: unknown = null;
    try {
      context = document.createElement('canvas').getContext('2d');
    } catch {
      context = null;
    }
    if (context === null) return;

    const xs = body.series[0].points.map(([x]) => x);
    const data: uPlot.AlignedData = [
      xs,
      ...body.series.map((series) => series.points.map(([, y]) => y)),
    ];
    const range: uPlot.Scale['range'] =
      axis === 'fixed' && body.fixedRange !== undefined ? [body.fixedRange[0], body.fixedRange[1]] : undefined;

    let chart: uPlot | null = null;
    try {
      chart = new uPlot(
        {
          width: element.clientWidth || 640,
          height,
          legend: { show: false },
          cursor: { drag: { x: false, y: false } },
          scales: { x: { time: body.xKind === 'time' }, y: range === undefined ? {} : { range } },
          axes: [
            { stroke: resolved('--muted', element), grid: { stroke: resolved('--grid', element), width: 1 } },
            {
              stroke: resolved('--muted', element),
              grid: { stroke: resolved('--grid', element), width: 1 },
              label: body.yLabel,
            },
          ],
          series: [
            {},
            ...body.series.map((series, index) => ({
              label: series.name,
              stroke: resolved(tokens.names[index], element),
              width: 1.6,
              // A partial series is drawn as partial, never as a finished line (contract §10).
              dash: series.partialFrom === undefined ? undefined : [6, 4],
            })),
          ],
        },
        data,
        element,
      );
    } catch {
      // uPlot could not draw here (no canvas backend). The text around the chart still carries the numbers.
      return;
    }

    const resize = () => chart?.setSize({ width: element.clientWidth || 640, height });
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chart?.destroy();
    };
  }, [axis, body, height, tokens]);

  if (tokens.blocked !== null) {
    return (
      <div className="rc-chart" data-rc="chart-block" data-blocked="true">
        <p className="rc-chart-blocked">{tokens.blocked}</p>
      </div>
    );
  }

  const legend = body.series.map((series, index) => {
    const points = series.points.filter(([, y]) => y !== null);
    const last = points.length === 0 ? null : points[points.length - 1][1];
    return { name: series.name, token: tokens.names[index], value: last === null ? undefined : num(last, 2) };
  });

  return (
    <div className="rc-chart" data-rc="chart-block" aria-label={label}>
      {body.axis !== undefined && body.fixedRange !== undefined && (
        <div className="rc-chart-axis">
          <SegmentedControl
            label="Axis"
            options={['Fixed', 'Fit']}
            selected={axis === 'fixed' ? 'Fixed' : 'Fit'}
            onSelect={(choice) => setAxis(choice === 'Fixed' ? 'fixed' : 'fit')}
          />
        </div>
      )}
      <div className="rc-chart-canvas" ref={host} style={{ minHeight: height }} />
      <Legend entries={legend} />
      {body.xKind === 'time' && asofMs !== null && (
        <p className="rc-chart-asof" data-rc="chart-asof">
          As-of rule at {amsterdamTime(asofMs)} Amsterdam.
        </p>
      )}
      <p className="rc-chart-method" data-rc="chart-method">
        {body.method}
        {body.xKind !== 'time' && asofMs !== null && ` Data as of ${amsterdamTime(asofMs)} Amsterdam.`}
      </p>
    </div>
  );
}
