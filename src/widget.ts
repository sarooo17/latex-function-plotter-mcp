export const WIDGET_URI = "ui://widget/function-plot-v1.html";

export const WIDGET_HTML = `<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif;
      background: #0f1117;
      color: #e8eaed;
    }
    #root { padding: 12px; }
    #title {
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 4px;
      word-break: break-word;
    }
    #subtitle {
      font-size: 12px;
      color: #9aa0a6;
      margin-bottom: 10px;
      word-break: break-word;
    }
    #chart { width: 100%; height: 420px; }
    #empty {
      padding: 24px;
      text-align: center;
      color: #9aa0a6;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <div id="root">
    <div id="title">Grafico funzione</div>
    <div id="subtitle">In attesa dei dati…</div>
    <div id="chart"></div>
    <div id="empty" hidden>Nessun dato da visualizzare.</div>
  </div>
  <script>
    const titleEl = document.getElementById('title');
    const subtitleEl = document.getElementById('subtitle');
    const chartEl = document.getElementById('chart');
    const emptyEl = document.getElementById('empty');

    function renderPlot(data) {
      if (!data || !data.curves) {
        chartEl.hidden = true;
        emptyEl.hidden = false;
        return;
      }
      chartEl.hidden = false;
      emptyEl.hidden = true;

      titleEl.textContent = 'f(x) = ' + (data.latex || data.expression || '');
      subtitleEl.textContent = (data.expression ? 'SymPy: ' + data.expression + ' · ' : '') +
        'Dominio [' + data.domain[0] + ', ' + data.domain[1] + ']';

      const traces = (data.curves || []).map((curve, i) => ({
        x: curve.x,
        y: curve.y,
        type: 'scatter',
        mode: 'lines',
        name: i === 0 ? 'f(x)' : 'ramo ' + (i + 1),
        line: { color: '#4f8cff', width: 2.5 },
        hovertemplate: 'x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>'
      }));

      const shapes = [];
      const annotations = [];

      for (const a of data.asymptotes || []) {
        if (a.type === 'vertical' && a.x != null) {
          shapes.push({
            type: 'line', x0: a.x, x1: a.x, y0: 0, y1: 1,
            xref: 'x', yref: 'paper',
            line: { color: '#ff6b6b', width: 2, dash: 'dash' }
          });
          annotations.push({
            x: a.x, y: 1, xref: 'x', yref: 'paper',
            text: 'x=' + Number(a.x).toFixed(2),
            showarrow: false, yanchor: 'bottom',
            font: { color: '#ff8a8a', size: 11 }
          });
        }
        if (a.type === 'horizontal' && a.y != null) {
          shapes.push({
            type: 'line', x0: 0, x1: 1, y0: a.y, y1: a.y,
            xref: 'paper', yref: 'y',
            line: { color: '#ffd166', width: 2, dash: 'dash' }
          });
          annotations.push({
            x: 1, y: a.y, xref: 'paper', yref: 'y',
            text: 'y=' + Number(a.y).toFixed(2),
            showarrow: false, xanchor: 'right',
            font: { color: '#ffe08a', size: 11 }
          });
        }
        if (a.type === 'oblique' && a.m != null && a.b != null) {
          const x0 = data.domain[0];
          const x1 = data.domain[1];
          shapes.push({
            type: 'line',
            x0, y0: a.m * x0 + a.b,
            x1, y1: a.m * x1 + a.b,
            line: { color: '#c77dff', width: 2, dash: 'dot' }
          });
        }
      }

      const points = data.specialPoints || [];
      if (points.length) {
        traces.push({
          x: points.map(p => p.x),
          y: points.map(p => p.y),
          type: 'scatter',
          mode: 'markers',
          name: 'punti notevoli',
          marker: { color: '#2ee59d', size: 9, symbol: 'circle-open', line: { width: 2 } },
          text: points.map(p => p.type),
          hovertemplate: '%{text}<br>x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>'
        });
      }

      Plotly.newPlot(chartEl, traces, {
        margin: { l: 48, r: 16, t: 16, b: 44 },
        paper_bgcolor: '#0f1117',
        plot_bgcolor: '#151922',
        font: { color: '#e8eaed' },
        xaxis: {
          title: 'x',
          gridcolor: '#2a2f3a',
          zerolinecolor: '#4a5160',
          range: data.domain
        },
        yaxis: {
          title: 'f(x)',
          gridcolor: '#2a2f3a',
          zerolinecolor: '#4a5160',
          scaleanchor: null
        },
        shapes,
        annotations,
        legend: { orientation: 'h', y: -0.15, font: { size: 11 } },
        hovermode: 'closest'
      }, { responsive: true, displayModeBar: false });
    }

    function handleToolResult(message) {
      const params = message?.params ?? message;
      const structured = params?.structuredContent ?? params?.result?.structuredContent ?? params;
      if (structured?.plot) renderPlot(structured.plot);
    }

    window.addEventListener('message', (event) => {
      if (event.source !== window.parent) return;
      const message = event.data;
      if (!message || message.jsonrpc !== '2.0') return;
      if (message.method === 'ui/notifications/tool-result') {
        handleToolResult(message);
      }
    }, { passive: true });
  </script>
</body>
</html>`;
