(() => {
  "use strict";

  const state = {
    meta: null,
    godowns: [],
    slabs: [],
    filters: { search: "", category: "all", godown: "all", inStockOnly: true },
    cart: JSON.parse(localStorage.getItem("sbg_cart") || "[]"),
    lastSubmittedOrder: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const grid = $("#grid");
  const toastEl = $("#toast");

  function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    setTimeout(() => toastEl.classList.remove("show"), 2600);
  }

  function saveCart() {
    localStorage.setItem("sbg_cart", JSON.stringify(state.cart));
    updateCartBadge();
  }

  function updateCartBadge() {
    const badge = $("#cartBadge");
    if (state.cart.length) {
      badge.hidden = false;
      badge.textContent = state.cart.length;
    } else {
      badge.hidden = true;
    }
  }

  // ------------------------------------------------------------ bootstrap
  async function init() {
    $("#year").textContent = new Date().getFullYear();
    updateCartBadge();

    // These three don't depend on each other, so fire them together instead
    // of waiting on each one in turn — on a cold serverless start each round
    // trip can take a while, and doing them back-to-back was tripling that
    // wait before the page even started loading stock.
    const [metaRes, godownsRes, annsRes] = await Promise.allSettled([
      api.getMeta(),
      api.getGodowns(),
      api.getAnnouncements(),
    ]);
    if (metaRes.status === "fulfilled") {
      state.meta = metaRes.value;
      buildCategoryChips(state.meta.categories);
    } // else categories fall back to "All" only
    if (godownsRes.status === "fulfilled") {
      state.godowns = godownsRes.value;
      buildGodownFilter(state.godowns);
    } // else godown filter falls back to "All Yards" only
    if (annsRes.status === "fulfilled") {
      buildTicker(annsRes.value);
    } // else ticker stays hidden

    bindFilterEvents();
    bindModalEvents();
    bindDrawerEvents();
    await loadSlabs();
  }

  function buildCategoryChips(categories) {
    const row = $("#categoryChips");
    categories.forEach((cat) => {
      const btn = document.createElement("button");
      btn.className = "chip";
      btn.dataset.category = cat;
      btn.textContent = cat;
      row.appendChild(btn);
    });
    row.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      row.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.filters.category = chip.dataset.category;
      loadSlabs();
    });
  }

  function buildGodownFilter(godowns) {
    const sel = $("#godownFilter");
    godowns.forEach((g) => {
      const opt = document.createElement("option");
      opt.value = g.id;
      opt.textContent = g.name;
      sel.appendChild(opt);
    });
  }

  function buildTicker(anns) {
    if (!anns || !anns.length) return;
    const track = $("#tickerTrack");
    const items = anns.map((a) => `<span>${badgeLabel(a.type)} ${escapeHtml(a.title)} — ${escapeHtml(a.message)}</span>`);
    track.innerHTML = items.join("") + items.join(""); // duplicate for seamless loop
    $("#ticker").hidden = false;
  }

  function badgeLabel(type) {
    return { offer: "[OFFER]", arrival: "[NEW ARRIVAL]", general: "[NOTICE]" }[type] || "[NOTICE]";
  }

  let searchDebounce;
  function bindFilterEvents() {
    $("#searchInput").addEventListener("input", (e) => {
      clearTimeout(searchDebounce);
      const val = e.target.value;
      searchDebounce = setTimeout(() => { state.filters.search = val; loadSlabs(); }, 300);
    });
    $("#godownFilter").addEventListener("change", (e) => {
      state.filters.godown = e.target.value; loadSlabs();
    });
    $("#inStockOnly").addEventListener("change", (e) => {
      state.filters.inStockOnly = e.target.checked; loadSlabs();
    });
  }

  // ------------------------------------------------------------- grid
  async function loadSlabs() {
    grid.setAttribute("aria-busy", "true");
    try {
      state.slabs = await api.getSlabs({
        search: state.filters.search,
        category: state.filters.category,
        godown: state.filters.godown,
        inStockOnly: state.filters.inStockOnly,
      });
      renderGrid();
    } catch (e) {
      grid.innerHTML = `<div class="tile-empty-state"><h3>Couldn't load stock</h3><p>${escapeHtml(e.message)}</p></div>`;
    }
    grid.removeAttribute("aria-busy");
  }

  function renderGrid() {
    if (!state.slabs.length) {
      grid.innerHTML = `<div class="tile-empty-state"><h3>No slabs match yet</h3><p>Try a different category, yard, or search term.</p></div>`;
      return;
    }
    grid.innerHTML = state.slabs.map(tileHtml).join("");
    grid.querySelectorAll(".tile").forEach((el) => {
      el.addEventListener("click", () => openSlabModal(el.dataset.id));
    });
  }

  function tileHtml(s) {
    return `
      <div class="tile ${s.isSold ? "is-sold" : ""}" data-id="${s.id}">
        ${s.isSold ? '<span class="tile-sold-flag">Sold</span>' : ""}
        <img src="${s.imageUrl}" alt="${escapeHtml(s.title)}" loading="lazy" />
        <div class="tile-stamp">
          <span class="tile-stamp__tag"><b>${escapeHtml(s.title)}</b>${escapeHtml(s.blockNumber || "")} · ${escapeHtml(s.godownName)}</span>
          <span class="tile-stamp__rate">${formatCurrencyINR(s.pricePerSqFt)}/sqft</span>
        </div>
      </div>`;
  }

  // ------------------------------------------------------------ modal
  function bindModalEvents() {
    $("#closeModal").addEventListener("click", closeSlabModal);
    $("#slabOverlay").addEventListener("click", (e) => { if (e.target.id === "slabOverlay") closeSlabModal(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeSlabModal(); closeDrawer(); } });
  }

  async function openSlabModal(id) {
    const overlay = $("#slabOverlay");
    const content = $("#modalContent");
    content.innerHTML = `<div class="modal-body">Loading…</div>`;
    overlay.classList.add("open");
    try {
      const s = await api.getSlab(id);
      content.innerHTML = modalHtml(s);
      content.querySelector("[data-add-cart]").addEventListener("click", () => {
        addToCart(s); showToast("Added to enquiry cart");
      });
      content.querySelector("[data-whatsapp]").addEventListener("click", () => {
        window.open(buildWhatsAppUrl({
          clientName: "", mobileNumber: "", requirement: `Interested in ${s.title}`,
          selectedSlabs: [s], requestedQuantitySqFt: s.totalSqFt, unit: "feet",
        }), "_blank");
      });
    } catch (e) {
      content.innerHTML = `<div class="modal-body">Couldn't load this slab. ${escapeHtml(e.message)}</div>`;
    }
  }

  function closeSlabModal() { $("#slabOverlay").classList.remove("open"); }

  function modalHtml(s) {
    const dims = `${s.length} × ${s.width} ${s.unit}`;
    return `
      <div class="modal-media"><img src="${s.imageUrl}" alt="${escapeHtml(s.title)}" /></div>
      <div class="modal-body">
        <div class="modal-eyebrow">${escapeHtml(s.category)} · ${escapeHtml(s.finish || "")}</div>
        <h2 class="modal-title">${escapeHtml(s.title)}</h2>
        <div class="modal-godown">${escapeHtml(s.godownName)} · Block ${escapeHtml(s.blockNumber || "—")}${s.isSold ? " · Sold" : ""}</div>

        <div class="spec-grid">
          <div class="spec-item"><div class="label">Dimensions</div><div class="value mono">${dims}</div></div>
          <div class="spec-item"><div class="label">Pieces</div><div class="value mono">${s.pieces}</div></div>
          <div class="spec-item"><div class="label">Thickness</div><div class="value mono">${s.thicknessMm || "—"} mm</div></div>
          <div class="spec-item"><div class="label">Total Area</div><div class="value mono">${s.totalSqFt} sq.ft</div></div>
        </div>

        <table class="rate-unit-table">
          <tr><td>Rate / Sq.Ft</td><td>${formatCurrencyINR(s.rates.perSqFt)}</td></tr>
          <tr><td>Rate / Sq.Meter</td><td>${formatCurrencyINR(s.rates.perSqMeter)}</td></tr>
          <tr><td>Total Area (Sq.Meter)</td><td>${s.totalSqMeters} m²</td></tr>
        </table>

        <div class="total-value"><span>Estimated total value</span>${s.estimatedValueFormatted}</div>

        <div class="modal-actions">
          <button class="btn" data-add-cart ${s.isSold ? "disabled" : ""}>Add to Enquiry</button>
          <button class="btn btn-outline btn-whatsapp" data-whatsapp>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5.1-1.3A10 10 0 1 0 12 2Zm5.7 14.2c-.2.6-1.4 1.2-2 1.3-.5.1-1.1.1-1.8-.1-.4-.1-1-.3-1.7-.6-3-1.3-4.9-4.3-5-4.5-.1-.2-1.2-1.6-1.2-3s.7-2.1 1-2.4c.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5.2.6.7 1.9.8 2 .1.2.1.4 0 .6-.1.2-.2.3-.3.5-.2.2-.3.3-.5.5-.2.2-.3.4-.1.7.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.4 2.4 1.5.3.1.5.1.7-.1.2-.2.7-.8.9-1.1.2-.3.4-.2.6-.1.2.1 1.5.7 1.8.8.3.1.5.2.5.3.1.2.1.6-.1 1.2Z"/></svg>
            WhatsApp
          </button>
        </div>
      </div>`;
  }

  // ------------------------------------------------------------- cart
  function addToCart(slab) {
    if (state.cart.some((s) => s.id === slab.id)) { showToast("Already in your cart"); return; }
    state.cart.push(slab);
    saveCart();
  }

  function removeFromCart(id) {
    state.cart = state.cart.filter((s) => s.id !== id);
    saveCart();
    renderDrawer();
  }

  function bindDrawerEvents() {
    $("#cartBtn").addEventListener("click", openDrawer);
    $("#closeDrawer").addEventListener("click", closeDrawer);
    $("#drawerOverlay").addEventListener("click", (e) => { if (e.target.id === "drawerOverlay") closeDrawer(); });
  }

  function openDrawer() { renderDrawer(); $("#drawerOverlay").classList.add("open"); }
  function closeDrawer() { $("#drawerOverlay").classList.remove("open"); }

  function renderDrawer() {
    $("#drawerTitle").textContent = `Enquiry Cart (${state.cart.length})`;
    const body = $("#drawerBody");
    const foot = $("#drawerFoot");

    if (!state.cart.length) {
      body.innerHTML = `<div class="cart-empty">Your cart is empty.<br>Add slabs from the catalog to build an enquiry.</div>`;
      foot.innerHTML = "";
      return;
    }

    body.innerHTML = state.cart.map((s) => `
      <div class="cart-line">
        <img src="${s.imageUrl}" alt="" />
        <div class="meta">
          <div class="t">${escapeHtml(s.title)}</div>
          <div class="s">${s.totalSqFt} sq.ft · ${formatCurrencyINR(s.pricePerSqFt)}/sqft</div>
          <button data-remove="${s.id}">Remove</button>
        </div>
      </div>`).join("");

    body.querySelectorAll("[data-remove]").forEach((btn) => {
      btn.addEventListener("click", () => removeFromCart(btn.dataset.remove));
    });

    const total = state.cart.reduce((sum, s) => sum + s.totalSqFt * s.pricePerSqFt, 0);
    foot.innerHTML = `
      <div class="total-value" style="margin-bottom:14px;"><span>Estimated total</span>${formatCurrencyINR(total)}</div>
      <button class="btn btn-block" id="proceedBtn">Continue to Enquiry Form</button>`;
    $("#proceedBtn").addEventListener("click", renderOrderForm);
  }

  function renderOrderForm() {
    const body = $("#drawerBody");
    const foot = $("#drawerFoot");
    const godownOptions = ["any", ...state.godowns.map((g) => g.id)];
    body.innerHTML = `
      <form id="orderForm">
        <div class="form-grid">
          <div class="field full"><label for="fClient">Full Name</label><input id="fClient" required /></div>
          <div class="field full"><label for="fMobile">Mobile Number</label><input id="fMobile" type="tel" required /></div>
          <div class="field full"><label for="fAddress">Delivery Address</label><textarea id="fAddress"></textarea></div>
          <div class="field"><label for="fGodown">Preferred Yard</label>
            <select id="fGodown">
              ${godownOptions.map((id) => `<option value="${id}">${id === "any" ? "Any" : (state.godowns.find(g=>g.id===id)||{}).name}</option>`).join("")}
            </select>
          </div>
          <div class="field"><label for="fUnit">Quantity Unit</label>
            <select id="fUnit"><option value="feet">Sq.Ft</option><option value="meters">Sq.Meter</option></select>
          </div>
          <div class="field full"><label for="fQty">Required Quantity</label><input id="fQty" type="number" min="0" step="0.01" /></div>
          <div class="field full"><label for="fReq">Requirement</label><textarea id="fReq" placeholder="Tell us what you need this stone for…"></textarea></div>
        </div>
        <p class="form-note">We'll confirm your enquiry on-screen and you can also send it straight to our WhatsApp.</p>
      </form>`;
    foot.innerHTML = `
      <div style="display:flex;gap:10px;">
        <button class="btn btn-outline" id="backToCart" type="button">Back</button>
        <button class="btn" id="submitOrder" form="orderForm" type="submit">Submit Enquiry</button>
      </div>`;
    $("#backToCart").addEventListener("click", renderDrawer);
    $("#orderForm").addEventListener("submit", handleOrderSubmit);
  }

  async function handleOrderSubmit(e) {
    e.preventDefault();
    const payload = {
      clientName: $("#fClient").value.trim(),
      mobileNumber: $("#fMobile").value.trim(),
      deliveryAddress: $("#fAddress").value.trim(),
      preferredGodown: $("#fGodown").value,
      dimensionUnit: $("#fUnit").value,
      requestedQuantitySqFt: parseFloat($("#fQty").value) || 0,
      requirement: $("#fReq").value.trim(),
      selectedSlabs: state.cart,
    };
    if (!payload.clientName || !payload.mobileNumber) { showToast("Name and mobile number are required"); return; }

    const btn = $("#submitOrder");
    btn.disabled = true; btn.textContent = "Submitting…";
    try {
      const result = await api.submitQuery(payload);
      state.lastSubmittedOrder = { ...payload, orderNumber: result.orderNumber };
      renderConfirmation(result);
      state.cart = [];
      saveCart();
    } catch (err) {
      showToast(err.message);
      btn.disabled = false; btn.textContent = "Submit Enquiry";
    }
  }

  function renderConfirmation(result) {
    const body = $("#drawerBody");
    const foot = $("#drawerFoot");
    body.innerHTML = `
      <div class="confirmation">
        <svg class="ok-mark" viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="22" stroke="#0a0a0a" stroke-width="1.6"/><path d="M15 24l6 6 12-13" stroke="#0a0a0a" stroke-width="2" fill="none"/></svg>
        <h3>Enquiry received</h3>
        <p>We'll reach out shortly with a quote.</p>
        <p class="order-no">Order ${escapeHtml(result.orderNumber || "")}</p>
      </div>`;
    foot.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:10px;">
        <button class="btn btn-whatsapp" id="waSend">
          <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5.1-1.3A10 10 0 1 0 12 2Z"/></svg>
          Send this to WhatsApp too
        </button>
        <button class="btn btn-outline" id="closeCartBtn">Done</button>
      </div>`;
    $("#waSend").addEventListener("click", () => {
      window.open(buildWhatsAppUrl(state.lastSubmittedOrder), "_blank");
    });
    $("#closeCartBtn").addEventListener("click", closeDrawer);
  }

  function buildWhatsAppUrl(order) {
    const num = (state.meta && state.meta.whatsappNumber) || "919828400811";
    const lines = [];
    lines.push(`*New Enquiry — Sri Balaji Granites*`);
    if (order.clientName) lines.push(`Name: ${order.clientName}`);
    if (order.mobileNumber) lines.push(`Mobile: ${order.mobileNumber}`);
    if (order.requirement) lines.push(`Requirement: ${order.requirement}`);
    if (order.selectedSlabs && order.selectedSlabs.length) {
      lines.push("");
      lines.push("Slabs:");
      order.selectedSlabs.forEach((s) => {
        lines.push(`• ${s.title} — Block ${s.blockNumber || "—"} — ${s.totalSqFt} sqft — ${formatCurrencyINR(s.pricePerSqFt)}/sqft — ${s.godownName}`);
      });
      const total = order.selectedSlabs.reduce((sum, s) => sum + s.totalSqFt * s.pricePerSqFt, 0);
      lines.push("");
      lines.push(`Estimated total: ${formatCurrencyINR(total)}`);
    }
    lines.push("");
    lines.push("Sent from the online catalog.");
    const text = encodeURIComponent(lines.join("\n"));
    return `https://wa.me/${num}?text=${text}`;
  }

  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  document.addEventListener("DOMContentLoaded", init);
})();
