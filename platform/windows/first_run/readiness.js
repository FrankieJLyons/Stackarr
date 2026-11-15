"use strict";
(() => {
  let key = location.hash.slice(1);
  if (!key) { try { key = sessionStorage.getItem("stackarr-readiness-key"); } catch (_) {} }
  if (location.hash) {
    try { sessionStorage.setItem("stackarr-readiness-key", key); } catch (_) {}
    history.replaceState(null, "", "/");
  }
  const retry = document.getElementById("retry");
  const close = document.getElementById("close");
  const choices = document.getElementById("choices");
  const list = document.getElementById("checks");
  const title = document.getElementById("result-title");
  const next = document.getElementById("next-step");
  const badge = document.getElementById("result-badge");
  const summary = document.querySelector(".summary");
  const guide = document.getElementById("guide");
  const installDocker = document.getElementById("install-docker");
  const setupError = document.getElementById("setup-error");
  const reviewDialog = document.getElementById("docker-review");
  const approveDocker = document.getElementById("approve-docker");
  const previousClosed = document.getElementById("previous-closed");
  const progressPanel = document.getElementById("docker-progress");
  const cancelDownload = document.getElementById("cancel-download");
  const continueStackarr = document.getElementById("continue-stackarr");
  const openNetwork = document.getElementById("open-network");
  openNetwork.addEventListener("click", async () => {
    if (busy || closed || setupBusy || handoffBusy) return;
    openNetwork.disabled = true;
    try { next.textContent = (await request("/api/stackarr/network")).message; }
    catch (error) { errorMessage(error.message); }
    finally { openNetwork.disabled = false; }
  });
  const labels = {pass:"Ready", block:"Action needed", unknown:"Check needed", note:"Review", skip:"Later"};
  const symbols = {pass:"\u2713", block:"!", unknown:"?", note:"i", skip:"\u2013"};
  const safeGuides = new Set(["https://docs.docker.com/desktop/setup/install/windows-install/"]);
  let mode = "install";
  let busy = false;
  let closed = false;
  let setupBusy = false;
  let handoffBusy = false;
  let review = null;
  let statusTimer = null;
  async function request(path, values = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 150000);
    try {
      const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json", "X-Readiness-Key":key}, body:JSON.stringify({mode, ...values}), signal:controller.signal});
      if (!response.ok) {
        let message = "The checker could not complete that step. Try again.";
        try { message = (await response.json()).message || message; } catch (_) {}
        throw new Error(message);
      }
      return await response.json();
    } finally { clearTimeout(timeout); }
  }
  async function check() {
    if (busy || closed || handoffBusy) return;
    if (!key) {
      title.textContent = "Reopen Stackarr readiness";
      badge.textContent = "REOPEN CHECKER";
      next.textContent = "Open the readiness application again to check this computer.";
      list.setAttribute("aria-busy", "false");
      return;
    }
    busy = true;
    retry.disabled = close.disabled = choices.disabled = true;
    list.replaceChildren();
    guide.hidden = true;
    installDocker.hidden = true;
    continueStackarr.hidden = true;
    document.getElementById("count").textContent = "";
    list.setAttribute("aria-busy", "true");
    title.textContent = mode === "install" ? "Checking your computer..." : "Checking your next step...";
    badge.textContent = "CHECKING";
    next.textContent = "This usually takes a few seconds. Docker checks can take longer while its engine starts.";
    try {
      const report = await request("/api/check");
      document.getElementById("network-recovery").hidden = !report.integrated;
      title.textContent = report.title;
      next.textContent = report.next_step;
      badge.textContent = report.state === "ready" ? "READY FOR SETUP" : "NEXT STEPS";
      summary.classList.toggle("attention", report.state !== "ready");
      continueStackarr.hidden = !report.integrated || report.state !== "ready";
      continueStackarr.disabled = setupBusy;
      if (report.integrated) document.querySelector(".after p").textContent = "Continue here to choose apps and folders, then review setup. Your existing apps and media stay separate from a new installation.";
      if (report.primary_action && safeGuides.has(report.primary_action.url)) {
        guide.href = report.primary_action.url;
        guide.textContent = report.primary_action.label + " \u2197";
        guide.hidden = false;
        installDocker.hidden = report.primary_action.label !== "Get Docker Desktop" || setupBusy;
      }
      for (const row of report.checks) {
        const item = document.createElement("li");
        item.className = "check " + row.state;
        const symbol = document.createElement("span");
        symbol.className = "symbol";
        symbol.textContent = symbols[row.state] || "?";
        symbol.setAttribute("aria-hidden", "true");
        const content = document.createElement("div");
        const heading = document.createElement("h3");
        heading.textContent = row.title;
        const status = document.createElement("span");
        status.className = "state-label";
        status.textContent = labels[row.state] || "Check needed";
        heading.append(status);
        const detail = document.createElement("p");
        detail.textContent = row.detail;
        content.append(heading, detail);
        if (row.action && safeGuides.has(row.action.url)) {
          const link = document.createElement("a");
          link.href = row.action.url;
          link.textContent = row.action.label + " \u2197";
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          content.append(link);
        }
        item.append(symbol, content);
        list.append(item);
      }
      document.getElementById("count").textContent = report.checks.filter(row => row.state === "pass").length + " ready / " + report.checks.length + " checks";
    } catch (_) {
      title.textContent = "Checks could not finish";
      badge.textContent = "TRY AGAIN";
      summary.classList.add("attention");
      next.textContent = "Choose Check again. If this window was left open for a while, reopen the readiness application.";
    } finally {
      busy = false;
      retry.disabled = close.disabled = choices.disabled = setupBusy;
      list.setAttribute("aria-busy", "false");
    }
  }
  retry.addEventListener("click", check);
  choices.addEventListener("change", () => { mode = document.querySelector("input[name=mode]:checked").value; check(); });
  close.addEventListener("click", async () => {
    if (busy || closed || setupBusy || handoffBusy) return;
    try {
      await request("/api/close");
      closed = true;
      try { sessionStorage.removeItem("stackarr-readiness-key"); } catch (_) {}
      key = null;
      retry.disabled = close.disabled = choices.disabled = true;
      guide.hidden = true;
      title.textContent = "Checks closed";
      badge.textContent = "DONE";
      next.textContent = "You can close this browser tab. Reopen the readiness application whenever you want to check again.";
      clearTimeout(statusTimer);
    } catch (error) { next.textContent = error.message; }
  });
  function errorMessage(message) { setupError.textContent = message; setupError.hidden = false; }
  async function pollSetup() {
    if (closed || !key) return;
    try {
      const status = await request("/api/docker/status");
      const wasBusy = setupBusy;
      setupBusy = status.busy;
      progressPanel.hidden = status.phase === "idle";
      document.getElementById("docker-message").textContent = status.message;
      const downloading = status.phase === "downloading";
      document.getElementById("download-progress").hidden = !downloading;
      const count = document.getElementById("download-count");
      count.hidden = !downloading;
      if (downloading) {
        document.getElementById("download-progress").value = 100 * status.downloaded / status.total;
        count.textContent = Math.round(status.downloaded / 1000000) + " / " + Math.round(status.total / 1000000) + " MB";
      }
      cancelDownload.hidden = !["downloading", "verifying"].includes(status.phase);
      retry.disabled = close.disabled = choices.disabled = busy || setupBusy || handoffBusy;
      continueStackarr.disabled = setupBusy || handoffBusy;
      installDocker.disabled = setupBusy;
      if (wasBusy && !setupBusy) check();
      if (setupBusy) statusTimer = setTimeout(pollSetup, 800);
    } catch (error) { errorMessage(error.message); }
  }
  installDocker.addEventListener("click", async () => {
    if (busy || setupBusy) return;
    setupError.hidden = true;
    installDocker.disabled = true;
    try {
      review = await request("/api/docker/review");
      document.getElementById("docker-release").textContent = "Docker Desktop " + review.version + " for this Windows account. Download: " + Math.round(review.download_bytes / 1000000) + " MB. Publisher: " + review.publisher + ".";
      const changes = document.getElementById("docker-changes");
      changes.replaceChildren();
      for (const text of review.changes) { const li = document.createElement("li"); li.textContent = text; changes.append(li); }
      previousClosed.checked = false;
      document.getElementById("previous-installer").hidden = !review.previous_installer_check;
      approveDocker.disabled = review.previous_installer_check;
      reviewDialog.showModal();
    } catch (error) { errorMessage(error.message); }
    finally { installDocker.disabled = false; }
  });
  previousClosed.addEventListener("change", () => { approveDocker.disabled = !previousClosed.checked; });
  document.getElementById("dismiss-docker").addEventListener("click", () => reviewDialog.close());
  approveDocker.addEventListener("click", async () => {
    if (!review) return;
    approveDocker.disabled = true;
    try {
      await request("/api/docker/start", {review_id:review.review_id, previous_closed:previousClosed.checked});
      reviewDialog.close();
      review = null;
      await pollSetup();
    } catch (error) { reviewDialog.close(); errorMessage(error.message); }
    finally { approveDocker.disabled = false; }
  });
  cancelDownload.addEventListener("click", async () => {
    cancelDownload.disabled = true;
    try { await request("/api/docker/cancel"); }
    catch (error) { errorMessage(error.message); }
    finally { cancelDownload.disabled = false; }
  });
  continueStackarr.addEventListener("click", async () => {
    if (busy || closed || setupBusy || handoffBusy) return;
    handoffBusy = true;
    setupError.hidden = true;
    retry.disabled = close.disabled = choices.disabled = continueStackarr.disabled = true;
    try {
      let result = await request("/api/stackarr/start");
      next.textContent = result.message || "Opening Stackarr...";
      while (result.phase === "starting") {
        await new Promise(resolve => setTimeout(resolve, 800));
        result = await request("/api/stackarr/status");
      }
      if (result.phase === "review-required") {
        next.textContent = result.message;
        handoffBusy = false;
        retry.disabled = close.disabled = choices.disabled = continueStackarr.disabled = false;
        return;
      }
      if (result.phase !== "ready") throw new Error(result.message || "Stackarr could not open. Try again.");
      const destination = new URL(result.url);
      if (destination.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(destination.hostname)) throw new Error("Stackarr returned an unexpected address.");
      closed = true;
      clearTimeout(statusTimer);
      location.replace(destination.href);
    } catch (error) {
      errorMessage(error.message);
      handoffBusy = false;
      retry.disabled = close.disabled = choices.disabled = continueStackarr.disabled = false;
    }
  });
  check();
  pollSetup();
})();
