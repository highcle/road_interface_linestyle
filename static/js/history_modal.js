function openHistoryModal() {
  const modal = document.getElementById('historyModal');
  const nowObj = new Date();
  const past1hObj = new Date(nowObj.getTime() - 60 * 60 * 1000);

  const toLocalISO = (d) => {
    const tzOffset = d.getTimezoneOffset() * 60000;
    return new Date(d.getTime() - tzOffset).toISOString().slice(0, 16);
  };

  document.getElementById('modalStartTime').value = toLocalISO(past1hObj);
  document.getElementById('modalEndTime').value = toLocalISO(nowObj);
  modal.style.display = 'flex';
}

function closeHistoryModal() {
  document.getElementById('historyModal').style.display = 'none';
}

function executeHistorySearch() {
  const startInput = document.getElementById('modalStartTime').value;
  const endInput = document.getElementById('modalEndTime').value;

  if (!startInput || !endInput) {
    alert("日時を正しく入力してください。");
    return;
  }

  const startStr = startInput.replace('T', ' ') + ':00';
  const endStr = endInput.replace('T', ' ') + ':00';

  AppState.customSearchMode = true;
  document.getElementById('autoUpdate').checked = false;
  document.getElementById('timeRangeLabel').innerText = `[過去指定] ${startStr} 〜 ${endStr}`;
  closeHistoryModal();

  // ★ 手動検索のときだけローディング表示
  fetchHistoryRoadData(startStr, endStr);
}