(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const toastEl = $("#toast");
  function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    setTimeout(() => toastEl.classList.remove("show"), 2600);
  }
  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  const state = {
    session: null,
    godowns: [],
    meta: null,
    editingSlabId: null,
    lastCalc: null,
    uploadedImageData: null,
    uploadedThumbnailData: null,
    imageProcessing: null,
  };

  // ---------------------------------------------------------------- auth
  function getStoredSession() {
    try { return JSON.parse(localStorage.getItem("sbg_staff_session") || "null"); }
    catch (e) { return null; }
  }

  async function init() {
    bindLogin();
    const session = getStoredSession();
    if (session && localStorage.getItem("sbg_staff_token")) {
      state.session = session;
      await enterApp();
    }
  }

  function bindLogin() {
    $("#loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = $("#loginUser").value.trim();
      const password = $("#loginPass").value;
      const errEl = $("#loginError");
      errEl.classList.remove("show");
      const btn = $("#loginSubmit");
      btn.disabled = true; btn.textContent = "Signing in…";
      try {
        const { token, session } = await api.login(username, password);
        localStorage.setItem("sbg_staff_token", token);
        localStorage.setItem("sbg_staff_session", JSON.stringify(session));
        state.session = session;
        await enterApp();
      } catch (err) {
        errEl.textContent = err.message;
        errEl.classList.add("show");
      } finally {
        btn.disabled = false; btn.textContent = "Sign In";
      }
    });

    $("#logoutBtn").addEventListener("click", () => {
      localStorage.removeItem("sbg_staff_token");
      localStorage.removeItem("sbg_staff_session");
      window.location.reload();
    });
  }

  async function enterApp() {
    $("#loginShell").style.display = "none";
    $("#staffApp").classList.add("active");
    $("#roleLabel").textContent = state.session.role.replace(/_/g, " ").toUpperCase();
    $("#userLabel").textContent = state.session.name + (state.session.godownName ? ` · ${state.session.godownName}` : " · All Yards");

    // Fire together instead of one-after-the-other — same fix as the public
    // catalog, cuts the wait before the dashboard is usable.
    const [godownsRes, metaRes] = await Promise.allSettled([api.getGodowns(), api.getMeta()]);
    state.godowns = godownsRes.status === "fulfilled" ? godownsRes.value : [];
    state.meta = metaRes.status === "fulfilled" ? metaRes.value : { categories: [], finishes: [] };

    populateGodownSelects();
    populateCategorySelects();
    bindTabs();
    bindStockTab();
    bindCalculatorTab();
    bindQueriesTab();
    bindTrashTab();
    bindReportsTab();
    bindAnnouncementsTab();

    loadStock();
  }

  function isManager() { return state.session.role !== "admin"; }
  function myGodownId() { return state.session.godownId; }

  function populateGodownSelects() {
    const targets = [$("#stockGodownFilter"), $("#sfGodown")];
    targets.forEach((sel) => {
      state.godowns.forEach((g) => {
        const opt = document.createElement("option");
        opt.value = g.id; opt.textContent = g.name;
        sel.appendChild(opt);
      });
    });
    if (isManager()) {
      $("#stockGodownFilter").value = myGodownId();
      $("#stockGodownFilter").disabled = true;
      $("#sfGodown").value = myGodownId();
      $("#sfGodown").disabled = true;
    }
  }

  function populateCategorySelects() {
    const filterSel = $("#stockCategoryFilter");
    const formSel = $("#sfCategory");
    (state.meta.categories || []).forEach((c) => {
      filterSel.appendChild(new Option(c, c));
      formSel.appendChild(new Option(c, c));
    });
  }

  function bindTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        $("#panel-" + btn.dataset.tab).classList.add("active");
        if (btn.dataset.tab === "queries") loadQueries();
        if (btn.dataset.tab === "trash") loadTrash();
        if (btn.dataset.tab === "reports") loadReports();
        if (btn.dataset.tab === "announcements") loadAnnouncements();
      });
    });
  }

  // ===================================================================
  // STOCK TAB
  // ===================================================================
  function bindStockTab() {
    $("#stockSearch").addEventListener("input", debounce(loadStock, 300));
    $("#stockGodownFilter").addEventListener("change", loadStock);
    $("#stockCategoryFilter").addEventListener("change", loadStock);
    $("#addSlabBtn").addEventListener("click", () => openSlabForm());
    $("#slabFormCancel").addEventListener("click", closeSlabForm);
    $("#slabForm").addEventListener("submit", submitSlabForm);
    $("#sfImageFile").addEventListener("change", handleSlabImageFile);
  }

  async function loadStock() {
    const tbody = $("#stockTableBody");
    tbody.innerHTML = `<tr class="empty-row"><td colspan="8">Loading…</td></tr>`;
    try {
      const params = {
        search: $("#stockSearch").value,
        category: $("#stockCategoryFilter").value,
        godown: isManager() ? myGodownId() : $("#stockGodownFilter").value,
        inStockOnly: "false",
      };
      const slabs = await api.getSlabs(params);
      renderStockKpis(slabs);
      if (!slabs.length) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="8">No slabs found.</td></tr>`;
        return;
      }
      tbody.innerHTML = slabs.map(stockRowHtml).join("");
      tbody.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => openSlabForm(slabs.find(s => s.id === b.dataset.edit))));
      tbody.querySelectorAll("[data-toggle-sold]").forEach((b) => b.addEventListener("click", () => toggleSold(b.dataset.toggleSold, slabs)));
      tbody.querySelectorAll("[data-delete]").forEach((b) => b.addEventListener("click", () => deleteSlab(b.dataset.delete)));
    } catch (e) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="8">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  function renderStockKpis(slabs) {
    const inStock = slabs.filter((s) => !s.isSold);
    const value = inStock.reduce((sum, s) => sum + s.totalSqFt * s.pricePerSqFt, 0);
    $("#stockKpis").innerHTML = [
      kpi(slabs.length, "Total Slabs"),
      kpi(inStock.length, "In Stock"),
      kpi(slabs.length - inStock.length, "Sold"),
      kpi(formatCurrencyINR(value), "Stock Value"),
    ].join("");
  }
  function kpi(n, l) { return `<div class="kpi-card"><div class="n">${n}</div><div class="l">${l}</div></div>`; }

  function stockRowHtml(s) {
    return `
      <tr>
        <td><img class="row-thumb" src="${s.imageUrl}" alt="" onerror="this.onerror=null;this.src='${NO_IMAGE_PLACEHOLDER}'" /></td>
        <td>${escapeHtml(s.title)}<br><span class="mono" style="color:var(--ink-soft);font-size:11px;">${escapeHtml(s.blockNumber || "")}</span></td>
        <td>${escapeHtml(s.category)}</td>
        <td>${escapeHtml(s.godownName)}</td>
        <td class="mono">${s.totalSqFt} sqft</td>
        <td class="mono">${formatCurrencyINR(s.pricePerSqFt)}</td>
        <td><span class="status-pill" data-status="${s.isSold ? "Closed" : "Pending"}">${s.isSold ? "SOLD" : "IN STOCK"}</span></td>
        <td class="row-actions">
          <button data-edit="${s.id}">Edit</button>
          <button data-toggle-sold="${s.id}">${s.isSold ? "Mark Available" : "Mark Sold"}</button>
          <button data-delete="${s.id}">Delete</button>
        </td>
      </tr>`;
  }

  async function toggleSold(id, slabs) {
    const slab = slabs.find((s) => s.id === id);
    try {
      await api.updateSlab(id, { isSold: !slab.isSold });
      showToast("Stock updated");
      loadStock();
    } catch (e) { showToast(e.message); }
  }

  async function deleteSlab(id) {
    if (!confirm("Move this slab to Trash?")) return;
    try {
      await api.deleteSlab(id);
      showToast("Moved to Trash");
      loadStock();
    } catch (e) { showToast(e.message); }
  }

  async function openSlabForm(slab) {
    const editId = slab && slab.id;
    state.editingSlabId = editId || null;
    state.uploadedImageData = null;
    state.uploadedThumbnailData = null;
    state.imageProcessing = null;

    // The stock table only carries the small list-view thumbnail per row
    // (kept deliberately small so the table itself loads fast) — so when
    // editing an existing slab, fetch the full record here to get the real
    // full-size image instead of accidentally overwriting it with the
    // thumbnail on save.
    if (editId) {
      try {
        slab = await api.getSlab(editId);
      } catch (e) {
        showToast("Couldn't load slab details");
        return;
      }
    }

    $("#slabFormTitle").textContent = editId ? "Edit Slab" : "Add Slab";
    $("#sfTitle").value = slab?.title || "";
    $("#sfCategory").value = slab?.category || state.meta.categories[0] || "";
    if (!isManager()) $("#sfGodown").value = slab?.godownId || state.godowns[0]?.id || "";
    $("#sfBlock").value = slab?.blockNumber || "";
    $("#sfFinish").value = slab?.finish || "Polished";
    $("#sfLength").value = slab?.length ?? "";
    $("#sfWidth").value = slab?.width ?? "";
    $("#sfUnit").value = slab?.unit || "feet";
    $("#sfPieces").value = slab?.pieces ?? 1;
    $("#sfThickness").value = slab?.thicknessMm ?? "";
    $("#sfRate").value = slab?.pricePerSqFt ?? "";
    $("#sfImage").value = slab?.imageUrl || "";
    $("#sfImageFile").value = "";
    const preview = $("#sfImagePreview");
    if (slab?.imageUrl) { preview.src = slab.imageUrl; preview.style.display = "block"; }
    else { preview.src = ""; preview.style.display = "none"; }
    $("#sfSold").checked = !!slab?.isSold;
    $("#slabFormOverlay").classList.add("open");
  }
  function closeSlabForm() { $("#slabFormOverlay").classList.remove("open"); }

  // Phone camera photos land here at 3-10MB straight out of the FileReader.
  // Two things used to break because of that: (1) the full-size base64 blob
  // rode along inside every /api/slabs list response, making the whole site
  // heavier as stock grew, and (2) a single upload could itself be big
  // enough to get rejected by the hosting platform's request-size limit,
  // which looked like "upload isn't working". Fix: resize+compress on a
  // canvas, and produce a small thumbnail (for lists) separately from a
  // moderate full image (for the detail view) — with size checked and
  // quality stepped down automatically if a photo is unusually detailed.
  function canvasToSizedJpeg(img, maxDim, targetBytes) {
    let { width, height } = img;
    if (width > maxDim || height > maxDim) {
      if (width >= height) { height = Math.round(height * (maxDim / width)); width = maxDim; }
      else { width = Math.round(width * (maxDim / height)); height = maxDim; }
    }
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d").drawImage(img, 0, 0, width, height);
    let quality = 0.75;
    let dataUrl = canvas.toDataURL("image/jpeg", quality);
    // Base64 runs ~33% bigger than raw bytes; step quality down until the
    // encoded result is comfortably within targetBytes, or we hit a floor.
    while (dataUrl.length * 0.75 > targetBytes && quality > 0.35) {
      quality -= 0.1;
      dataUrl = canvas.toDataURL("image/jpeg", quality);
    }
    return dataUrl;
  }

  // Resizing/compressing a photo (especially generating two sizes) takes a
  // real moment — if staff hit Save before this finished, the form used to
  // submit with no image ready yet and silently fall back to a random
  // placeholder photo. state.imageProcessing lets submitSlabForm wait for
  // this to actually finish instead of racing it.
  function handleSlabImageFile(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      showToast("Please choose an image file");
      e.target.value = "";
      return;
    }
    const preview = $("#sfImagePreview");
    const btn = $("#slabFormSubmit");
    showToast("Processing image…");
    btn.disabled = true;
    const prevBtnText = btn.textContent;
    btn.textContent = "Processing image…";
    state.imageProcessing = new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const img = new Image();
        img.onload = () => {
          state.uploadedImageData = canvasToSizedJpeg(img, 1280, 500 * 1024);
          state.uploadedThumbnailData = canvasToSizedJpeg(img, 360, 40 * 1024);
          preview.src = state.uploadedImageData;
          preview.style.display = "block";
          showToast("Image ready");
          btn.disabled = false; btn.textContent = prevBtnText;
          resolve();
        };
        img.onerror = () => {
          // Fallback: still works even if canvas decoding fails for some reason.
          state.uploadedImageData = reader.result;
          state.uploadedThumbnailData = reader.result;
          preview.src = reader.result;
          preview.style.display = "block";
          btn.disabled = false; btn.textContent = prevBtnText;
          resolve();
        };
        img.src = reader.result;
      };
      reader.onerror = () => {
        showToast("Couldn't read that image file");
        btn.disabled = false; btn.textContent = prevBtnText;
        resolve();
      };
      reader.readAsDataURL(file);
    });
  }

  // No upload and no manual URL: previously fell back to a random photo
  // from picsum.photos, which is what was showing up as "some old/generic
  // photo" on the customer page instead of the real product. A plain
  // in-page placeholder (no external service, nothing misleading) instead.
  const NO_IMAGE_PLACEHOLDER = "data:image/svg+xml," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="700">' +
    '<rect width="100%" height="100%" fill="#e9e4dd"/>' +
    '<text x="50%" y="50%" font-family="sans-serif" font-size="36" fill="#9a9186" text-anchor="middle" dominant-baseline="middle">No Photo</text>' +
    '</svg>'
  );

  async function submitSlabForm(e) {
    e.preventDefault();
    if (state.imageProcessing) {
      showToast("Finishing image processing…");
      await state.imageProcessing;
    }
    const payload = {
      title: $("#sfTitle").value.trim(),
      category: $("#sfCategory").value,
      godownId: isManager() ? myGodownId() : $("#sfGodown").value,
      blockNumber: $("#sfBlock").value.trim(),
      finish: $("#sfFinish").value,
      length: parseFloat($("#sfLength").value),
      width: parseFloat($("#sfWidth").value),
      unit: $("#sfUnit").value,
      pieces: parseInt($("#sfPieces").value, 10) || 1,
      thicknessMm: $("#sfThickness").value ? parseFloat($("#sfThickness").value) : null,
      pricePerSqFt: parseFloat($("#sfRate").value),
      imageUrl: state.uploadedImageData || $("#sfImage").value.trim() || NO_IMAGE_PLACEHOLDER,
      isSold: $("#sfSold").checked,
    };
    if (state.uploadedThumbnailData) payload.thumbnailUrl = state.uploadedThumbnailData;
    const btn = $("#slabFormSubmit");
    btn.disabled = true; btn.textContent = "Saving…";
    try {
      if (state.editingSlabId) await api.updateSlab(state.editingSlabId, payload);
      else await api.createSlab(payload);
      showToast("Slab saved");
      closeSlabForm();
      loadStock();
    } catch (err) {
      showToast(err.message);
    } finally {
      btn.disabled = false; btn.textContent = "Save Slab";
    }
  }

  // ===================================================================
  // CALCULATOR TAB
  // ===================================================================
  function bindCalculatorTab() {
    $("#calcForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const length = parseFloat($("#calcLength").value);
      const width = parseFloat($("#calcWidth").value);
      const unit = $("#calcUnit").value;
      const pieces = parseInt($("#calcPieces").value, 10) || 1;
      const rate = $("#calcRate").value ? parseFloat($("#calcRate").value) : null;

      const area = calculateSlabArea(length, width, unit, pieces);
      let html = `<dl>
        <dt>Total Sq.Ft</dt><dd>${area.totalSqFt}</dd>
        <dt>Total Sq.Meter</dt><dd>${area.totalSqMeters}</dd>
        <dt>Total Sq.Cm</dt><dd>${area.totalSqCm}</dd>`;
      state.lastCalc = { length, width, unit, pieces, area, rate };
      if (rate != null) {
        const rates = getRatesInAllUnits(rate);
        const value = area.totalSqFt * rate;
        html += `
          <dt>Rate / Sq.Ft</dt><dd>${formatCurrencyINR(rates.perSqFt)}</dd>
          <dt>Rate / Sq.Meter</dt><dd>${formatCurrencyINR(rates.perSqMeter)}</dd>
          <dt>Estimated Value</dt><dd>${formatCurrencyINR(value)}</dd>`;
      }
      html += `</dl>`;
      $("#calcResult").innerHTML = html;
      $("#calcQuickAdd").style.display = "inline-flex";
    });

    $("#calcQuickAdd").addEventListener("click", () => {
      if (!state.lastCalc) return;
      openSlabForm({
        length: state.lastCalc.length, width: state.lastCalc.width,
        unit: state.lastCalc.unit, pieces: state.lastCalc.pieces,
        pricePerSqFt: state.lastCalc.rate || "",
      });
      document.querySelector('.tab-btn[data-tab="stock"]').click();
    });
  }

  // ===================================================================
  // QUERIES TAB
  // ===================================================================
  function bindQueriesTab() {
    $("#queryStatusFilter").addEventListener("change", loadQueries);
  }

  async function loadQueries() {
    const tbody = $("#queriesTableBody");
    tbody.innerHTML = `<tr class="empty-row"><td colspan="7">Loading…</td></tr>`;
    try {
      let queries = await api.getQueries();
      const filter = $("#queryStatusFilter").value;
      if (filter !== "all") queries = queries.filter((q) => q.status === filter);
      if (!queries.length) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="7">No enquiries yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = queries.map(queryRowHtml).join("");
      tbody.querySelectorAll("[data-status-select]").forEach((sel) => {
        sel.addEventListener("change", async () => {
          try { await api.updateQuery(sel.dataset.statusSelect, { status: sel.value }); showToast("Status updated"); loadQueries(); }
          catch (e) { showToast(e.message); }
        });
      });
      tbody.querySelectorAll("[data-wa]").forEach((b) => {
        b.addEventListener("click", () => window.open(`https://wa.me/${b.dataset.wa}`, "_blank"));
      });
    } catch (e) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="7">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  function queryRowHtml(q) {
    const godownName = (state.godowns.find((g) => g.id === q.preferredGodown) || {}).name || "Any";
    const waNum = (q.mobileNumber || "").replace(/[^0-9]/g, "");
    return `
      <tr>
        <td class="mono">${escapeHtml(q.orderNumber || "—")}</td>
        <td>${escapeHtml(q.clientName)}</td>
        <td class="mono">${escapeHtml(q.mobileNumber)}</td>
        <td style="max-width:220px;">${escapeHtml(q.requirement || "—")}</td>
        <td>${escapeHtml(godownName)}</td>
        <td>
          <select class="select-field" data-status-select="${q.id}">
            ${["Pending", "Contacted", "Quoted", "Closed"].map((s) => `<option ${s === q.status ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </td>
        <td class="row-actions"><button data-wa="${waNum}">WhatsApp</button></td>
      </tr>`;
  }

  // ===================================================================
  // TRASH TAB
  // ===================================================================
  function bindTrashTab() {}

  async function loadTrash() {
    const tbody = $("#trashTableBody");
    tbody.innerHTML = `<tr class="empty-row"><td colspan="6">Loading…</td></tr>`;
    try {
      const items = await api.getTrash();
      if (!items.length) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="6">Trash is empty.</td></tr>`;
        return;
      }
      tbody.innerHTML = items.map((t) => `
        <tr>
          <td><img class="row-thumb" src="${t.slab.imageUrl || NO_IMAGE_PLACEHOLDER}" alt="" onerror="this.onerror=null;this.src='${NO_IMAGE_PLACEHOLDER}'" /></td>
          <td>${escapeHtml(t.slab.title)}</td>
          <td>${escapeHtml(t.slab.godownName)}</td>
          <td>${escapeHtml(t.deletedBy || "—")}</td>
          <td class="mono">${t.remainingDays ?? "—"}d</td>
          <td class="row-actions">
            <button data-restore="${t.id}">Restore</button>
            <button data-purge="${t.id}">Delete Forever</button>
          </td>
        </tr>`).join("");
      tbody.querySelectorAll("[data-restore]").forEach((b) => b.addEventListener("click", async () => {
        try { await api.restoreTrash(b.dataset.restore); showToast("Slab restored"); loadTrash(); } catch (e) { showToast(e.message); }
      }));
      tbody.querySelectorAll("[data-purge]").forEach((b) => b.addEventListener("click", async () => {
        if (!confirm("Permanently delete this slab?")) return;
        try { await api.purgeTrash(b.dataset.purge); showToast("Deleted permanently"); loadTrash(); } catch (e) { showToast(e.message); }
      }));
    } catch (e) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="6">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  // ===================================================================
  // REPORTS TAB
  // ===================================================================
  function bindReportsTab() {
    $("#exportCsvBtn").addEventListener("click", async () => {
      try {
        const blob = await api.exportCsv();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "stock_export.csv"; a.click();
        URL.revokeObjectURL(url);
      } catch (e) { showToast(e.message); }
    });
  }

  async function loadReports() {
    try {
      const summary = await api.getSummary();
      $("#reportKpis").innerHTML = [
        kpi(summary.totalSlabs, "Total Slabs"),
        kpi(summary.inStockCount, "In Stock"),
        kpi(summary.soldCount, "Sold"),
        kpi(summary.totalStockValueFormatted, "Stock Value"),
      ].join("");
      const rows = Object.entries(summary.byCategory || {}).map(([cat, d]) => `
        <tr><td>${escapeHtml(cat)}</td><td class="mono">${d.count}</td><td class="mono">${Math.round(d.sqft)}</td><td class="mono">${formatCurrencyINR(d.value)}</td></tr>`);
      $("#reportCategoryBody").innerHTML = rows.join("") || `<tr class="empty-row"><td colspan="4">No stock data yet.</td></tr>`;
    } catch (e) { showToast(e.message); }
  }

  // ===================================================================
  // ANNOUNCEMENTS TAB
  // ===================================================================
  function bindAnnouncementsTab() {
    $("#addAnnBtn").addEventListener("click", () => {
      $("#annForm").reset();
      $("#afActive").checked = true;
      $("#annFormOverlay").classList.add("open");
    });
    $("#annFormCancel").addEventListener("click", () => $("#annFormOverlay").classList.remove("open"));
    $("#annForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api.createAnnouncement({
          title: $("#afTitle").value.trim(),
          message: $("#afMessage").value.trim(),
          type: $("#afType").value,
          isActive: $("#afActive").checked,
        });
        showToast("Announcement published");
        $("#annFormOverlay").classList.remove("open");
        loadAnnouncements();
      } catch (err) { showToast(err.message); }
    });
  }

  async function loadAnnouncements() {
    const tbody = $("#annTableBody");
    tbody.innerHTML = `<tr class="empty-row"><td colspan="5">Loading…</td></tr>`;
    try {
      const items = await api.getAllAnnouncements();
      if (!items.length) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="5">No announcements yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = items.map((a) => `
        <tr>
          <td>${escapeHtml(a.title)}</td>
          <td>${escapeHtml(a.type)}</td>
          <td style="max-width:280px;">${escapeHtml(a.message)}</td>
          <td><input type="checkbox" data-toggle="${a.id}" ${a.isActive ? "checked" : ""} /></td>
          <td class="row-actions"><button data-del-ann="${a.id}">Delete</button></td>
        </tr>`).join("");
      tbody.querySelectorAll("[data-toggle]").forEach((cb) => cb.addEventListener("change", async () => {
        try { await api.updateAnnouncement(cb.dataset.toggle, { isActive: cb.checked }); showToast("Updated"); } catch (e) { showToast(e.message); }
      }));
      tbody.querySelectorAll("[data-del-ann]").forEach((b) => b.addEventListener("click", async () => {
        if (!confirm("Delete this announcement?")) return;
        try { await api.deleteAnnouncement(b.dataset.delAnn); showToast("Deleted"); loadAnnouncements(); } catch (e) { showToast(e.message); }
      }));
    } catch (e) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="5">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  // ---------------------------------------------------------------- utils
  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  document.addEventListener("DOMContentLoaded", init);
})();
