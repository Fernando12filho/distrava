function _coalesce(times, values) {
  const t = [];
  const v = [];
  for (let i = 0; i < times.length; i++) {
    if (values[i] !== null && values[i] !== undefined) {
      t.push(times[i]);
      v.push(values[i]);
    }
  }
  return [t, v];
}

function _interpolate(xs, ys, targetX) {
  if (targetX <= xs[0]) return ys[0];
  if (targetX >= xs[xs.length - 1]) return ys[ys.length - 1];
  for (let i = 1; i < xs.length; i++) {
    if (xs[i] >= targetX) {
      const x0 = xs[i - 1];
      const x1 = xs[i];
      const y0 = ys[i - 1];
      const y1 = ys[i];
      if (x1 === x0) return y1;
      return y0 + ((targetX - x0) / (x1 - x0)) * (y1 - y0);
    }
  }
  return ys[ys.length - 1];
}

function _nearest(times, values, targetTime) {
  if (!times.length) return null;
  let best = 0;
  let bestDiff = Infinity;
  for (let i = 0; i < times.length; i++) {
    const diff = Math.abs(times[i] - targetTime);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = i;
    }
  }
  return values[best];
}

function _fmtClock(v) {
  if (v === null || v === undefined || !isFinite(v)) return "";
  const m = Math.floor(v);
  const s = Math.round((v - m) * 60);
  return m + ":" + String(s).padStart(2, "0");
}

function _lerpHex(a, b, t) {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  let out = "#";
  for (const shift of [16, 8, 0]) {
    const ca = (pa >> shift) & 255;
    const cb = (pb >> shift) & 255;
    out += Math.round(ca + t * (cb - ca)).toString(16).padStart(2, "0");
  }
  return out;
}

function _effortRampColor(ramp, t) {
  const clamped = Math.min(1, Math.max(0, t));
  const scaled = clamped * (ramp.length - 1);
  const i = Math.min(ramp.length - 2, Math.floor(scaled));
  return _lerpHex(ramp[i], ramp[i + 1], scaled - i);
}

function renderRoutePolyline(containerId, lats, lons, times, hrs, zones) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const points = [];
  for (let i = 0; i < lats.length; i++) {
    if (lats[i] !== null && lats[i] !== undefined && lons[i] !== null && lons[i] !== undefined) {
      points.push({ lat: lats[i], lon: lons[i], t: times ? times[i] : null });
    }
  }
  if (points.length < 2) return;

  const avgLat = points.reduce((sum, p) => sum + p.lat, 0) / points.length;
  const cosLat = Math.cos((avgLat * Math.PI) / 180);
  const projected = points.map((p) => [p.lon * cosLat, p.lat]);

  const xs = projected.map((p) => p[0]);
  const ys = projected.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;

  const width = 400;
  const height = 300;
  const padding = 24;
  const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY);
  const offsetX = (width - spanX * scale) / 2;
  const offsetY = (height - spanY * scale) / 2;

  const coords = projected.map(([x, y]) => {
    const px = offsetX + (x - minX) * scale;
    const py = height - (offsetY + (y - minY) * scale);
    return px.toFixed(1) + "," + py.toFixed(1);
  });

  const strokeAttrs =
    'fill="none" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"';

  const [hrTimes, hrVals] = _coalesce(times || [], hrs || []);
  let svgBody;
  if (zones && zones.length >= 3 && hrTimes.length) {
    // Zone floors are resting + lo × reserve, so any two floors recover the
    // resting HR and reserve without shipping them separately.
    const reserve = (zones[2].min_bpm - zones[1].min_bpm) / (zones[2].lo - zones[1].lo);
    const restingHr = zones[1].min_bpm - zones[1].lo * reserve;

    // The zone colors are a validated brightness ramp, so the route gradient
    // interpolates the same palette the zones card shows.
    const ramp = zones.map((z) => z.color);

    // Both hrTimes and route point times ascend, so a single forward-walking
    // pointer finds each point's nearest HR sample in linear time. The ramp
    // position is quantized so same-shade segments merge into few polylines.
    let j = 0;
    const colors = points.map((p) => {
      while (j + 1 < hrTimes.length && Math.abs(hrTimes[j + 1] - p.t) <= Math.abs(hrTimes[j] - p.t)) j++;
      const effort = ((hrVals[j] - restingHr) / reserve - 0.5) / 0.5;
      return _effortRampColor(ramp, Math.round(effort * 24) / 24);
    });

    // One polyline per same-zone run; the boundary point is repeated in both
    // runs so the route stays visually continuous.
    const runs = [];
    let start = 0;
    for (let k = 1; k < points.length - 1; k++) {
      if (colors[k] !== colors[start]) {
        runs.push({ from: start, to: k, color: colors[start] });
        start = k;
      }
    }
    runs.push({ from: start, to: points.length - 1, color: colors[start] });
    svgBody = runs
      .map((r) => '<polyline points="' + coords.slice(r.from, r.to + 1).join(" ") + '" stroke="' + r.color + '" ' + strokeAttrs + " />")
      .join("");
  } else {
    svgBody = '<polyline points="' + coords.join(" ") + '" stroke="#C4F82A" ' + strokeAttrs + " />";
  }

  el.innerHTML =
    '<svg viewBox="0 0 ' + width + " " + height + '" style="width:100%; height:100%;" preserveAspectRatio="xMidYMid meet">' +
    svgBody +
    "</svg>";
  el.style.backgroundImage = "none";
}

async function initActivityCharts(streamUrl, units, zones) {
  const response = await fetch(streamUrl);
  const stream = await response.json();

  renderRoutePolyline("route-map", stream.lat || [], stream.lon || [], stream.time || [], stream.hr || [], zones || []);

  const isImperial = units === "imperial";
  const distDivisor = isImperial ? 1609.344 : 1000;
  const distUnit = isImperial ? "mi" : "km";
  const feetPerMeter = 3.28084;

  const [distTimes, dists] = _coalesce(stream.time, stream.distance);
  if (distTimes.length < 2) return;

  const [hrTimes, hrs] = _coalesce(stream.time, stream.hr);
  const [elevTimes, elevs] = _coalesce(stream.time, stream.elevation);

  const bucketCount = Math.max(1, Math.min(60, distTimes.length - 1));
  const bucketTimes = [];
  const bucketDist = [];
  for (let i = 0; i <= bucketCount; i++) {
    const targetDist = dists[0] + (i / bucketCount) * (dists[dists.length - 1] - dists[0]);
    bucketTimes.push(_interpolate(dists, distTimes, targetDist));
    bucketDist.push(targetDist / distDivisor);
  }

  const paceLabels = bucketDist.slice(1);
  const paceSeries = [];
  for (let i = 1; i <= bucketCount; i++) {
    const dt = bucketTimes[i] - bucketTimes[i - 1];
    const dd = bucketDist[i] - bucketDist[i - 1];
    paceSeries.push(dd > 0 ? dt / 60 / dd : null);
  }

  const hrSeries = bucketTimes.map((t) => _nearest(hrTimes, hrs, t));
  const elevSeries = bucketTimes.map((t) => {
    const v = _nearest(elevTimes, elevs, t);
    if (v === null || v === undefined) return null;
    return isImperial ? v * feetPerMeter : v;
  });

  const baseX = (labels, showTicks) => ({
    grid: { display: false },
    border: { color: "#26262E", display: showTicks },
    ticks: {
      display: showTicks,
      color: "#5E5E68",
      font: { family: "'JetBrains Mono'", size: 9 },
      maxTicksLimit: 8,
      callback: (v, i) => labels[i].toFixed(1) + (i === labels.length - 1 ? " " + distUnit : ""),
    },
  });

  const common = (bodyColor) => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#1E1E26",
        borderColor: "#2C2C36",
        borderWidth: 1,
        titleColor: "#5E5E68",
        bodyColor,
        bodyFont: { family: "'JetBrains Mono'" },
        titleFont: { family: "'JetBrains Mono'", size: 10 },
        displayColors: false,
        padding: 8,
      },
    },
    elements: { point: { radius: 0 } },
  });

  const render = (id, labels, data, color, fill, showXTicks, yFmt) => {
    const el = document.getElementById(id);
    if (!el) return;
    new Chart(el.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            data,
            borderColor: color,
            borderWidth: 2,
            tension: 0.35,
            spanGaps: true,
            fill: fill ? { target: "origin" } : false,
            backgroundColor: fill ? "rgba(60,60,72,0.35)" : "transparent",
          },
        ],
      },
      options: {
        ...common(color),
        scales: {
          x: baseX(labels, showXTicks),
          y: {
            grid: { color: "#17171D" },
            border: { display: false },
            ticks: { color: "#5E5E68", font: { family: "'JetBrains Mono'", size: 9 }, maxTicksLimit: 3, callback: yFmt },
          },
        },
      },
    });
  };

  render("paceChart", paceLabels, paceSeries, "#C4F82A", false, false, _fmtClock);
  render("hrChart", bucketDist, hrSeries, "#C4F82A", false, false, (v) => Math.round(v));
  render("elevChart", bucketDist, elevSeries, "#6C6C78", true, true, (v) => Math.round(v));
}
