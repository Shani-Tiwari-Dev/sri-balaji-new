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

    try { state.godowns = await api.getGodowns(); } catch (e) { state.godowns = []; }
    try { state.meta = await api.getMeta(); } catch (e) { state.meta = { categories: [], finishes: [] }; }

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
        <td><img class="row-thumb" src="${s.imageUrl}" alt="" /></td>
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

  function openSlabForm(slab) {
    state.editingSlabId = slab ? slab.id : null;
    state.uploadedImageData = null;
    $("#slabFormTitle").textContent = slab ? "Edit Slab" : "Add Slab";
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

  function handleSlabImageFile(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      showToast("Please choose an image file");
      e.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      state.uploadedImageData = reader.result;
      const preview = $("#sfImagePreview");
      preview.src = reader.result;
      preview.style.display = "block";
    };
    reader.readAsDataURL(file);
  }

  async function submitSlabForm(e) {
    e.preventDefault();
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
      imageUrl: state.uploadedImageData || $("#sfImage").value.trim() || `https://picsum.photos/seed/${Date.now()}/900/700`,
      isSold: $("#sfSold").checked,
    };
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
          <td><img class="row-thumb" src="${t.slab.imageUrl || ""}" alt="" /></td>
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
