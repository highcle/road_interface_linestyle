const slider = document.getElementById('timeSlider');
const now = new Date();
const past24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

noUiSlider.create(slider, {
  start: [now.getTime() - 6 * 60 * 60 * 1000, now.getTime()],
  connect: true,
  range: { 'min': past24h.getTime(), 'max': now.getTime() },
  step: 5 * 60 * 1000,
  pips: {
    mode: 'count',
    values: 7,
    density: 4,
    format: {
      to: function (value) {
        const d = new Date(value);
        return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      }
    }
  }
});

function formatTimeString(timestamp) {
  const d = new Date(timestamp);
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0') + ' ' +
    String(d.getHours()).padStart(2, '0') + ':' +
    String(d.getMinutes()).padStart(2, '0') + ':00';
}

function getSliderTimeRange() {
  const vals = slider.noUiSlider.get();
  return {
    startStr: formatTimeString(Number(vals[0])),
    endStr: formatTimeString(Number(vals[1]))
  };
}

slider.noUiSlider.on('update', function (values) {
  const startStr = formatTimeString(Number(values[0]));
  const endStr = formatTimeString(Number(values[1]));
  document.getElementById('timeRangeLabel').innerText = `${startStr}  〜  ${endStr}`;
});

// ★ スライダー変更時：サーバー通信なしで即座にクライアント表示を更新
slider.noUiSlider.on('change', function () {
  AppState.customSearchMode = false;
  refreshLayerStyles();
});