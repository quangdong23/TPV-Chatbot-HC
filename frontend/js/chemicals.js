/* ===========================================================================
 * chemicals.js - Module Frontend cho Giám sát Hóa chất & Soát tài liệu (Feature 2)
 * ======================================================================== */
(function (global) {
  'use strict';

  function getApi() {
    return global.API || global.tpvApi || window.API;
  }
  function getMd() {
    return global.MD || global.tpvMarkdown || window.MD;
  }

  var state = {
    rooms: [],
    catalog: [],
    anomalies: [],
    lastReviewResult: null,
    reviewFilter: 'all',
    chatMessages: [],
    extractedItems: null,
    selectedFile: null,
  };

  function el(id) { return document.getElementById(id); }

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Khởi tạo và nạp dữ liệu ban đầu
  async function init() {
    setupDropzone();
    bindEvents();
    resetReview();
    await loadInitialData();
  }

  async function loadInitialData() {
    var api = getApi();
    if (!api) return;
    try {
      var roomsRes = await api.chemicalRooms();
      state.rooms = (roomsRes && roomsRes.items) || [];
      populateRoomPickers();
    } catch (e) {
      console.warn('Lỗi tải danh sách phòng:', e);
    }

    try {
      var catRes = await api.chemicalCatalog();
      state.catalog = (catRes && catRes.items) || [];
      populateChemicalPickers();
    } catch (e) {
      console.warn('Lỗi tải danh mục hóa chất:', e);
    }

    loadAnomalies();
  }

  function populateRoomPickers() {
    var pickers = [el('chemChatRoom'), el('chemRevRoomFilter')];
    pickers.forEach(function (sel) {
      if (!sel) return;
      var cur = sel.value;
      sel.innerHTML = '<option value="">-- Mọi phòng --</option>';
      state.rooms.forEach(function (r) {
        var opt = document.createElement('option');
        opt.value = r.room_code;
        opt.textContent = r.room_code + (r.room_name ? ' - ' + r.room_name : '');
        sel.appendChild(opt);
      });
      if (cur) sel.value = cur;
    });
  }

  function populateChemicalPickers() {
    var sel = el('chemChatChem');
    if (!sel) return;
    var cur = sel.value;
    sel.innerHTML = '<option value="">-- Mọi hóa chất --</option>';
    state.catalog.forEach(function (c) {
      var opt = document.createElement('option');
      opt.value = c.chemical_code;
      opt.textContent = c.chemical_code + (c.chemical_name ? ' - ' + c.chemical_name : '');
      sel.appendChild(opt);
    });
    if (cur) sel.value = cur;
  }

  async function loadAnomalies() {
    var container = el('chemAnomaliesList');
    var badgePill = el('chemAnomCountPill');
    if (!container) return;
    var api = getApi();
    if (!api) {
      container.innerHTML = '<div class="muted sm">Đang kết nối API...</div>';
      return;
    }
    try {
      container.innerHTML = '<div class="muted sm" style="padding:10px 0;"><span class="loading-dots">Đang cập nhật danh sách bất thường...</span></div>';
      var res = await api.chemicalAnomalies();
      var findings = (res && res.findings) || [];
      state.anomalies = findings;

      if (badgePill) {
        badgePill.textContent = findings.length;
        badgePill.className = 'pill ' + (findings.length > 0 ? 'warn' : 'ok');
      }

      if (!findings.length) {
        container.innerHTML = '<div class="muted sm" style="padding:8px 0;">✅ Không có phát hiện bất thường nào cần xử lý.</div>';
        return;
      }

      var html = '<div class="chem-anom-cards">';
      findings.forEach(function (f) {
        var sevClass = f.severity === 'high' ? 'card-severity-high' :
                       f.severity === 'medium' ? 'card-severity-medium' : 'card-severity-low';
        var sevBadge = f.severity === 'high' ? '<span class="chem-badge badge-danger">🔴 Nguy cấp</span>' :
                       f.severity === 'medium' ? '<span class="chem-badge badge-warning">🟡 Cảnh báo</span>' :
                       '<span class="chem-badge badge-info">🔵 Thông tin</span>';

        var timeStr = f.window_to ? f.window_to.slice(0, 19).replace('T', ' ') : '—';
        var roomInfo = f.room_code || 'Toàn bộ';
        var chemInfo = f.chemical_code ? ' · Hóa chất ' + escapeHtml(f.chemical_code) : '';

        html += '<div class="chem-card ' + sevClass + '">' +
          '<div class="chem-card-header">' +
            '<strong>' + escapeHtml(f.metric) + ' (' + escapeHtml(roomInfo) + chemInfo + ')</strong>' +
            sevBadge +
          '</div>' +
          '<div class="chem-card-body">' +
            '<p class="chem-desc">' + escapeHtml(f.explanation || '') + '</p>' +
            '<div class="chem-kv">' +
              '<span>🕒 Thời điểm: <b>' + escapeHtml(timeStr) + ' UTC</b></span>' +
              '<span>Đo được: <b style="color:#ef4444">' + escapeHtml(f.observed_value) + '</b> (Chuẩn: ' + escapeHtml(f.baseline_value) + ')</span>' +
            '</div>' +
          '</div>' +
        '</div>';
      });
      html += '</div>';
      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = '<div class="text-danger sm" style="padding:8px 0;">Lỗi tải bất thường: ' + escapeHtml(e.message) + '</div>';
    }
  }

  // ──────────────────────────── CHATBOT HÓA CHẤT ────────────────────────────
  async function handleSendChat() {
    var input = el('chemChatInput');
    var btn = el('chemChatSendBtn');
    var messagesDiv = el('chemChatMessages');
    var text = (input.value || '').trim();
    if (!text) return;

    var roomCode = el('chemChatRoom') ? el('chemChatRoom').value : null;
    var chemCode = el('chemChatChem') ? el('chemChatChem').value : null;

    appendChatMessage('user', text);
    input.value = '';
    btn.disabled = true;

    var botMsgDiv = appendChatMessage('bot', '<span class="loading-dots">Đang xử lý truy vấn dữ liệu & tài liệu…</span>');
    var api = getApi();
    var md = getMd();

    try {
      var res = await api.chemicalChat({
        question: text,
        room_code: roomCode,
        chemical_code: chemCode,
      });

      var answerHtml = md ? md.render(res.answer || '') : escapeHtml(res.answer || '');
      
      var badges = '<div class="chem-sources-bar">';
      if (res.sql_evidence && res.sql_evidence.length) {
        badges += '<span class="chem-badge badge-sql">📊 SQL Server (' + res.sql_evidence.length + ' bảng/truy vấn)</span> ';
      }
      if (res.document_citations && res.document_citations.length) {
        badges += '<span class="chem-badge badge-rag">📄 Qdrant SDS (' + res.document_citations.length + ' trích dẫn)</span>';
      }
      badges += '</div>';

      botMsgDiv.innerHTML = badges + '<div class="chem-bot-content">' + answerHtml + '</div>';
    } catch (e) {
      botMsgDiv.innerHTML = '<div class="text-danger">Lỗi phản hồi: ' + escapeHtml(e.message) + '</div>';
    } finally {
      btn.disabled = false;
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  }

  function appendChatMessage(role, htmlContent) {
    var container = el('chemChatMessages');
    if (!container) return null;
    var msgDiv = document.createElement('div');
    msgDiv.className = 'chem-chat-msg ' + (role === 'user' ? 'msg-user' : 'msg-bot');
    msgDiv.innerHTML = htmlContent;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
    return msgDiv;
  }

  // ──────────────────────────── SOÁT TÀI LIỆU ────────────────────────────
  function setupDropzone() {
    var dropzone = el('chemDropzone');
    var fileInput = el('chemRevFile');
    var selectedDiv = el('chemSelectedFile');
    var fileNameSpan = el('chemSelectedFileName');
    var clearBtn = el('chemClearFileBtn');
    var promptDiv = el('dropzonePrompt');

    if (!dropzone || !fileInput) return;

    fileInput.addEventListener('click', function (e) {
      e.stopPropagation();
    });

    dropzone.addEventListener('click', function (e) {
      if (clearBtn && (e.target === clearBtn || clearBtn.contains(e.target))) return;
      fileInput.click();
    });

    dropzone.addEventListener('keydown', function (e) {
      if (e.target === dropzone && !state.reviewBusy && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); fileInput.click(); }
    });

    // Handle Drag & Drop
    ['dragenter', 'dragover'].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (e) {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('drag');
      });
    });

    ['dragleave', 'dragend'].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (e) {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('drag');
      });
    });

    dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('drag');
      if (state.reviewBusy) return;
      var dt = e.dataTransfer;
      if (dt && dt.files && dt.files.length) {
        state.selectedFile = dt.files[0];
        try {
          fileInput.files = dt.files;
        } catch (_) {}
        updateFileDisplay();
      }
    });

    fileInput.addEventListener('change', function () {
      if (state.reviewBusy) return;
      if (fileInput.files && fileInput.files.length) {
        state.selectedFile = fileInput.files[0];
      }
      updateFileDisplay();
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        fileInput.value = '';
        state.selectedFile = null;
        updateFileDisplay();
      });
    }

    function updateFileDisplay() {
      resetReview();
      var file = state.selectedFile || (fileInput.files && fileInput.files[0]);
      dropzone.classList.toggle('has-file', !!file);
      if (file) {
        el('chemRevText').value = '';
        if (fileNameSpan) fileNameSpan.textContent = file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
        if (selectedDiv) selectedDiv.style.display = 'flex';
        if (promptDiv) promptDiv.style.display = 'none';
      } else {
        if (selectedDiv) selectedDiv.style.display = 'none';
        if (promptDiv) promptDiv.style.display = 'flex';
      }
    }
  }

  function reviewMessage(message) {
    el('chemRevResult').innerHTML = '<div class="result-empty">' + escapeHtml(message) + '</div>';
  }

  function resetReview() {
    state.extractedItems = null;
    state.lastReviewResult = null;
    el('chemExtractedPreview').style.display = 'none';
    el('chemRevSubmitBtn').disabled = true;
    el('chemRevResult').innerHTML = '<div class="result-empty">Kết quả đối soát sẽ hiện ở đây.</div>';
  }

  function setReviewBusy(busy) {
    state.reviewBusy = busy;
    ['chemExtractAiBtn', 'chemRevFile', 'chemRevText', 'chemRevDate', 'chemClearFileBtn', 'chemClearTextBtn'].forEach(function (id) {
      if (el(id)) el(id).disabled = busy;
    });
    el('chemRevSubmitBtn').disabled = busy || !state.extractedItems;
    el('chemExtractAiBtnLabel').textContent = busy ? 'Đang xử lý…' : 'Đọc số liệu';
    el('chemDropzone').style.pointerEvents = busy ? 'none' : '';
    el('chemExtractedTable').querySelectorAll('input').forEach(function (input) { input.disabled = busy; });
  }

  var REVIEW_FIELDS = [
    ['room_code', 'Phòng'], ['chemical_code', 'Mã hóa chất'], ['metric', 'Chỉ số'],
    ['value', 'Giá trị'], ['unit', 'Đơn vị'], ['measured_at', 'Thời điểm đo'],
  ];

  function renderExtractedItems(items) {
    el('chemExtractedCount').textContent = items.length + ' dòng số liệu — kiểm tra và sửa trực tiếp trước khi đối soát';
    el('chemExtractedTable').innerHTML = '<table class="doc-table chem-edit-table"><thead><tr><th>Dòng</th>' +
      REVIEW_FIELDS.map(function (f) { return '<th>' + f[1] + '</th>'; }).join('') + '</tr></thead><tbody>' +
      items.map(function (row, index) {
        return '<tr><td>' + (index + 1) + '</td>' + REVIEW_FIELDS.map(function (f) {
          var value = row[f[0]] == null ? '' : String(row[f[0]]);
          return '<td><input type="text" data-row="' + index + '" data-field="' + f[0] + '" value="' + escapeHtml(value) +
            '" aria-label="' + f[1] + ' dòng ' + (index + 1) + '"' + (f[0] === 'value' ? ' inputmode="decimal"' : '') + '></td>';
        }).join('') + '</tr>';
      }).join('') + '</tbody></table>';
    el('chemExtractedPreview').style.display = 'flex';
  }

  async function handleExtractAi() {
    if (state.reviewBusy) return;
    var file = state.selectedFile;
    var text = el('chemRevText').value.trim();
    if (!file && !text) { alert('Chọn tệp hoặc dán nội dung báo cáo trước.'); return; }
    resetReview();
    setReviewBusy(true);
    reviewMessage('Đang đọc và trích xuất số liệu, chưa đối soát SQL Server…');
    try {
      var result;
      if (file) {
        result = await getApi().chemicalPreviewFile(file);
      } else if (/^[\[{]/.test(text)) {
        var parsed = JSON.parse(text);
        result = { items: Array.isArray(parsed) ? parsed : (parsed.items || [parsed]), report_date: parsed.report_date };
      } else {
        result = await getApi().chemicalExtractDocText({ text: text });
      }
      if (!Array.isArray(result.items) || !result.items.length || result.items.some(function (item) { return !item || typeof item !== 'object' || Array.isArray(item); })) {
        throw new Error('Không tìm thấy dòng số liệu hợp lệ. Hãy kiểm tra tài liệu.');
      }
      state.extractedItems = result.items.map(function (item, i) { return Object.assign({}, item, { row_number: item.row_number || i + 1 }); });
      state.reviewFileName = result.file_name || (file ? file.name : 'bao_cao_kiem_ke.txt');
      if (result.report_date && !el('chemRevDate').value) {
        var date = new Date(result.report_date);
        if (!isNaN(date.getTime())) el('chemRevDate').value = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      }
      renderExtractedItems(state.extractedItems);
      reviewMessage('Kiểm tra số liệu bên trên, sau đó bấm Đối soát SQL Server.');
    } catch (err) {
      reviewMessage('Không đọc được số liệu: ' + err.message);
    } finally {
      setReviewBusy(false);
    }
  }

  async function handleRunDocumentReview() {
    if (state.reviewBusy || !state.extractedItems) return;
    var items = state.extractedItems.map(function (item) { return Object.assign({}, item); });
    for (var i = 0; i < items.length; i++) {
      var row = items[i];
      var value = String(row.value == null ? '' : row.value).trim();
      if (!String(row.room_code || '').trim() || !String(row.metric || '').trim() || !value || !Number.isFinite(Number(value.replace(',', '.')))) {
        alert('Dòng ' + (i + 1) + ': cần mã phòng, chỉ số và giá trị số hợp lệ.'); return;
      }
      if (row.measured_at && isNaN(new Date(row.measured_at).getTime())) {
        alert('Dòng ' + (i + 1) + ': thời điểm đo chưa hợp lệ. Dùng dạng 2026-11-07T08:00:00+07:00 hoặc để trống.'); return;
      }
    }
    var dateInput = el('chemRevDate').value;
    if (dateInput && isNaN(new Date(dateInput).getTime())) { alert('Ngày lập báo cáo chưa hợp lệ.'); return; }
    setReviewBusy(true);
    reviewMessage('Đang đối chiếu các dòng đã kiểm tra với SQL Server…');
    try {
      var result = await getApi().chemicalReviewDoc({
        file_name: state.reviewFileName,
        report_date: dateInput ? new Date(dateInput).toISOString() : null,
        items: items,
      });
      state.lastReviewResult = result;
      state.reviewFilter = 'all';
      renderReviewResult(result);
    } catch (err) {
      reviewMessage('Không đối soát được: ' + err.message);
    } finally {
      setReviewBusy(false);
    }
  }

  var REVIEW_STATUS = {
    matched: ['Khớp', 'matched'],
    matched_latest_snapshot: ['Khớp bản ghi chốt gần nhất', 'matched'],
    value_mismatch: ['Lệch số liệu', 'mismatch'],
    mismatched: ['Lệch số liệu', 'mismatch'],
    missing_in_report: ['Báo cáo thiếu số liệu', 'mismatch'],
    timestamp_mismatch: ['Nghi lệch thời điểm', 'verify'],
    unit_mismatch: ['Đơn vị không tương thích', 'verify'],
    invalid_value: ['Giá trị chưa hợp lệ', 'verify'],
    unknown_room: ['Mã phòng chưa hợp lệ', 'verify'],
    unknown_chemical: ['Mã hóa chất chưa hợp lệ', 'verify'],
    duplicate_report_row: ['Dòng báo cáo trùng', 'verify'],
    missing_in_database: ['SQL Server chưa có bản ghi phù hợp', 'missing'],
    out_of_data_range: ['Ngoài phạm vi thời gian dữ liệu', 'missing'],
  };

  function reviewStatus(status) { return REVIEW_STATUS[status] || ['Cần xác minh: ' + (status || 'chưa rõ'), 'verify']; }
  function getStatusBadge(status) {
    var info = reviewStatus(status);
    var cls = { matched: 'ok', mismatch: 'err', verify: 'warn', missing: 'info' }[info[1]];
    return '<span class="pill ' + cls + '">' + escapeHtml(info[0]) + '</span>';
  }
  function reviewTime(value) {
    if (!value) return 'Không có thời điểm';
    var date = new Date(value);
    return isNaN(date.getTime()) ? String(value) : date.toLocaleString('vi-VN', { timeZone: 'Asia/Bangkok', hour12: false }) + ' (UTC+7)';
  }
  function reviewNumber(value, unit) { return value == null ? 'Không có dữ liệu' : String(value) + (unit ? ' ' + unit : ''); }
  function reviewReason(row) {
    var evidence = row.evidence || {};
    var reason = evidence.note || evidence.reason || reviewStatus(row.status)[0];
    if (row.status === 'value_mismatch' || row.status === 'mismatched') {
      reason = 'Số liệu báo cáo khác SQL Server.' + (evidence.note ? ' ' + evidence.note : '');
    }
    if (row.abs_diff != null) reason += ' Chênh lệch (báo cáo − SQL): ' + reviewNumber(row.abs_diff, row.db_unit) + '.';
    if (evidence.tolerance != null) reason += ' Sai số cho phép: ' + reviewNumber(evidence.tolerance, row.db_unit) + '.';
    return reason;
  }

  function renderReviewResult(data) {
    var host = el('chemRevResult');
    if (!data || !Array.isArray(data.results)) { host.textContent = 'Không có kết quả đối soát.'; return; }
    var counts = { matched: 0, mismatch: 0, verify: 0, missing: 0 };
    data.results.forEach(function (row) { counts[reviewStatus(row.status)[1]]++; });
    var tiles = [['Tổng dòng kiểm tra', data.results.length], ['Khớp', counts.matched], ['Sai lệch', counts.mismatch], ['Cần xác minh', counts.verify], ['Thiếu dữ liệu đối chiếu', counts.missing]];
    var html = '<div class="card chemical-review-results"><div class="card-head"><h3>Kết quả đối soát</h3></div><div class="chemical-review-summary">' + tiles.map(function (tile) {
      return '<div class="stat"><span class="stat-label">' + tile[0] + '</span><b class="stat-value">' + tile[1] + '</b></div>';
    }).join('') + '</div>';
    var coverage = (data.summary || {}).db_coverage || {};
    if (coverage.min_measured_at || coverage.max_measured_at) html += '<p class="panel-sub chemical-review-coverage">Dữ liệu SQL Server: ' + escapeHtml(reviewTime(coverage.min_measured_at)) + ' → ' + escapeHtml(reviewTime(coverage.max_measured_at)) + '</p>';
    html += '<p class="muted sm">Số liệu được quy về cùng đơn vị khi chuyển đổi được. Thiếu dữ liệu không được xem là số 0 hoặc kết luận sai.</p>';
    var filters = [['all', 'Tất cả', data.results.length], ['issue', 'Cần chú ý', data.results.length - counts.matched], ['matched', 'Khớp', counts.matched]];
    html += '<div class="chemical-review-toolbar"><div class="seg">' + filters.map(function (filter) {
      return '<button type="button" class="seg-btn ' + (state.reviewFilter === filter[0] ? 'is-on' : '') + '" data-filter="' + filter[0] + '">' + filter[1] + ' (' + filter[2] + ')</button>';
    }).join('') + '</div></div>';
    var rows = data.results.filter(function (row) {
      var matched = reviewStatus(row.status)[1] === 'matched';
      return state.reviewFilter === 'all' || (state.reviewFilter === 'matched' ? matched : !matched);
    });
    html += '<div class="table-scroll"><table class="doc-table"><thead><tr><th>Dòng</th><th>Phòng / Hóa chất</th><th>Chỉ số</th><th>Thời điểm</th><th>Báo cáo</th><th>SQL Server</th><th>Kết quả</th><th>Lý do / Chênh lệch</th></tr></thead><tbody>';
    html += rows.map(function (row) {
      var group = reviewStatus(row.status)[1];
      var target = (row.room_code || '—') + (row.chemical_code ? ' / ' + row.chemical_code : ' (Môi trường)');
      var reportTime = row.report_measured_at || data.report_date;
      return '<tr class="' + (group === 'mismatch' ? 'row-mismatch' : group === 'verify' ? 'row-warning' : '') + '">' +
        '<td>' + escapeHtml(row.report_row_number == null ? '—' : row.report_row_number) + '</td><td>' + escapeHtml(target) + '</td><td>' + escapeHtml(row.metric) + '</td>' +
        '<td>BC: ' + escapeHtml(reportTime ? reviewTime(reportTime) : 'Không ghi riêng') + '<br>SQL: ' + escapeHtml(reviewTime(row.db_measured_at)) + '</td>' +
        '<td>' + escapeHtml(reviewNumber(row.report_value, row.report_unit)) + '</td><td>' + escapeHtml(reviewNumber(row.db_value, row.db_unit)) + '</td>' +
        '<td>' + getStatusBadge(row.status) + '</td><td>' + escapeHtml(reviewReason(row)) + '</td></tr>';
    }).join('') || '<tr><td colspan="8">Không có dòng trong nhóm này.</td></tr>';
    host.innerHTML = html + '</tbody></table></div></div>';
    host.querySelectorAll('[data-filter]').forEach(function (button) {
      button.addEventListener('click', function () { state.reviewFilter = button.dataset.filter; renderReviewResult(data); });
    });
  }

  function bindEvents() {
    var sendBtn = el('chemChatSendBtn');
    if (sendBtn) sendBtn.addEventListener('click', handleSendChat);

    var chatInput = el('chemChatInput');
    if (chatInput) {
      chatInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          handleSendChat();
        }
      });
    }

    var clearTextBtn = el('chemClearTextBtn');
    if (clearTextBtn) {
      clearTextBtn.addEventListener('click', function () {
        if (el('chemRevText')) el('chemRevText').value = '';
        resetReview();
        var hint = el('chemJsonValidationHint');
        if (hint) hint.textContent = '';
      });
    }

    var extractBtn = el('chemExtractAiBtn');
    if (extractBtn) extractBtn.addEventListener('click', handleExtractAi);

    el('chemRevText').addEventListener('input', function () {
      state.selectedFile = null;
      el('chemRevFile').value = '';
      el('chemSelectedFile').style.display = 'none';
      el('dropzonePrompt').style.display = 'flex';
      resetReview();
    });
    el('chemExtractedTable').addEventListener('input', function (event) {
      var input = event.target;
      if (!input.dataset.field || !state.extractedItems) return;
      state.extractedItems[Number(input.dataset.row)][input.dataset.field] = input.value.trim() || null;
      state.lastReviewResult = null;
      reviewMessage('Số liệu đã thay đổi. Bấm Đối soát SQL Server để cập nhật kết quả.');
    });
    el('chemRevDate').addEventListener('input', function () {
      state.lastReviewResult = null;
      reviewMessage('Ngày báo cáo đã thay đổi. Cần đối soát lại để cập nhật kết quả.');
    });

    // Nút thực hiện đối soát
    var revBtn = el('chemRevSubmitBtn');
    if (revBtn) revBtn.addEventListener('click', handleRunDocumentReview);

    var refreshAnomBtn = el('chemRefreshAnomBtn');
    if (refreshAnomBtn) refreshAnomBtn.addEventListener('click', loadAnomalies);
  }

  global.tpvChemicals = {
    init: init,
    loadInitialData: loadInitialData,
  };

  // Tự động nạp khi trang sẵn sàng
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
