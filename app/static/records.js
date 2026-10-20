// One small line per distance: each point is a new record, so the line only
// ever steps down. Times arrive as whole seconds and are shown as m:ss.
function _fmtRecordTime(seconds) {
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

function initRecordCharts() {
  document.querySelectorAll("canvas[data-chart]").forEach((canvas) => {
    const { dates, seconds } = JSON.parse(canvas.dataset.chart);
    new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: dates,
        datasets: [
          {
            data: seconds,
            borderColor: "#C4F82A",
            backgroundColor: "#C4F82A",
            borderWidth: 2,
            pointRadius: 3,
            stepped: "before",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#1E1E26",
            borderColor: "#2C2C36",
            borderWidth: 1,
            titleColor: "#ECECEF",
            bodyColor: "#C4F82A",
            bodyFont: { family: "'JetBrains Mono'" },
            titleFont: { family: "'JetBrains Mono'" },
            displayColors: false,
            callbacks: { label: (c) => _fmtRecordTime(c.parsed.y) },
          },
        },
        scales: {
          x: { display: false },
          y: {
            grid: { color: "#1A1A20" },
            border: { display: false },
            ticks: {
              color: "#5E5E68",
              font: { family: "'JetBrains Mono'", size: 9 },
              maxTicksLimit: 3,
              callback: (v) => _fmtRecordTime(v),
            },
          },
        },
      },
    });
  });
}
