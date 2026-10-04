const state = {
  cases: [],
  history: [],
  currentResult: null,
  currentJourney: null,
  selectedModality: "CT_CHEST",
  initialized: false,
};

const elements = {
  select: document.querySelector("#case-select"),
  caseDescription: document.querySelector("#case-description"),
  analyzeButton: document.querySelector("#analyze-button"),
  resultSection: document.querySelector("#result-section"),
  historyBody: document.querySelector("#history-body"),
  recentList: document.querySelector("#recent-list"),
  refreshHistory: document.querySelector("#refresh-history"),
  confirmReviewButton: document.querySelector("#confirm-review-button"),
  resetDemoButton: document.querySelector("#reset-demo-button"),
  resetDialog: document.querySelector("#reset-demo-dialog"),
  resetDialogCancel: document.querySelector("#reset-dialog-cancel"),
  resetDialogConfirm: document.querySelector("#reset-dialog-confirm"),
  toast: document.querySelector("#toast"),
};

const modalityLabels = {
  CT_CHEST: "КТ органов грудной клетки",
  MAMMOGRAPHY: "Маммография",
  UNKNOWN: "Неизвестная модальность",
};

const priorityLabels = {
  ROUTINE: "Плановый",
  PRIORITY: "Приоритетный",
  URGENT: "Срочный",
  MANUAL_REVIEW: "Ручная проверка",
};

const workflowLabels = {
  PENDING_CLINICIAN_REVIEW: "Ожидает врача",
  ESCALATED_FOR_REVIEW: "Срочная проверка",
  BLOCKED_PENDING_REVIEW: "Маршрут заблокирован",
  PATIENT_ACTION_AVAILABLE: "Маршрут подтверждён",
  APPOINTMENT_BOOKED: "Пациент записался",
};

const traceStageLabels = {
  SOURCE_RESULT: "Исходный результат",
  NORMALIZED_FINDING: "Нормализованная находка",
  ROUTING_RULE: "Правило маршрутизации",
  SAFETY_CHECK: "Проверка безопасности",
};

document.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  bindNavigation();
  bindActions();

  await Promise.allSettled([loadDemoCases(), loadHistory()]);
  state.initialized = true;
}

function bindNavigation() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
}

function bindActions() {
  elements.select.addEventListener("change", updateCaseDescription);
  elements.analyzeButton.addEventListener("click", analyzeSelectedCase);
  elements.refreshHistory.addEventListener("click", loadHistory);
  document.querySelector("#open-all-history").addEventListener("click", () => switchView("history"));
  document.querySelector("#open-source-button").addEventListener("click", openSourceDetails);
  elements.confirmReviewButton.addEventListener("click", submitClinicianReview);
  elements.resetDemoButton.addEventListener("click", () => elements.resetDialog.showModal());
  elements.resetDialogCancel.addEventListener("click", () => elements.resetDialog.close());
  elements.resetDialogConfirm.addEventListener("click", resetDemonstration);
  elements.resetDialog.addEventListener("click", (event) => {
    if (event.target === elements.resetDialog) elements.resetDialog.close();
  });
  document.addEventListener("visibilitychange", refreshDoctorState);
  window.addEventListener("pageshow", refreshDoctorState);
  document.querySelectorAll(".modality-option[data-modality]").forEach((button) => {
    button.addEventListener("click", () => selectModality(button.dataset.modality));
  });
}

async function resetDemonstration() {
  const originalLabel = elements.resetDialogConfirm.textContent;
  elements.resetDemoButton.disabled = true;
  elements.resetDialogCancel.disabled = true;
  elements.resetDialogConfirm.disabled = true;
  elements.resetDialogConfirm.setAttribute("aria-busy", "true");
  elements.resetDialogConfirm.textContent = "Сбрасываем…";
  try {
    const result = await apiRequest("/api/v1/demo/reset", { method: "POST" });
    state.history = [];
    state.currentResult = null;
    state.currentJourney = null;
    state.selectedModality = "CT_CHEST";
    elements.resultSection.classList.add("hidden");
    document.querySelector("#source-details").open = false;
    renderHistory();
    renderRecentAdmissions();
    renderMetrics();
    selectModality("CT_CHEST");
    elements.resetDialog.close();
    showToast(`Демо готово к новому показу. Удалено исследований: ${result.deleted_analyses}`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    elements.resetDemoButton.disabled = false;
    elements.resetDialogCancel.disabled = false;
    elements.resetDialogConfirm.disabled = false;
    elements.resetDialogConfirm.removeAttribute("aria-busy");
    elements.resetDialogConfirm.textContent = originalLabel;
  }
}

async function refreshDoctorState() {
  if (!state.initialized || document.hidden) return;
  await loadHistory({ silent: true });
  if (state.currentResult) await loadCareJourney(state.currentResult.analysis_id);
}

function switchView(viewName) {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelector(`#${viewName}-view`).classList.add("active");
  document.querySelector("#page-title").textContent = "Кабинет врача";
  if (viewName === "history") loadHistory();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadDemoCases() {
  try {
    state.cases = await apiRequest("/api/v1/demo-cases");
    renderCaseOptions();
  } catch (error) {
    elements.select.innerHTML = '<option value="">Не удалось загрузить сценарии</option>';
    showToast(error.message, true);
  }
}

function selectModality(modality) {
  state.selectedModality = modality;
  document.querySelectorAll(".modality-option[data-modality]").forEach((button) => {
    button.classList.toggle("active", button.dataset.modality === modality);
  });
  renderCaseOptions();
}

function renderCaseOptions() {
  const validCases = state.cases.filter(
    (item) => item.validation === "valid" && item.modality === state.selectedModality,
  );
  elements.select.innerHTML = validCases
      .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)}</option>`)
      .join("");
  const preferred = validCases.find((item) => item.id === "ct-lung-nodule");
  if (preferred) elements.select.value = preferred.id;
  elements.analyzeButton.disabled = validCases.length === 0;
  updateCaseDescription();
}

function updateCaseDescription() {
  const selected = state.cases.find((item) => item.id === elements.select.value);
  elements.caseDescription.textContent = selected?.description || "Выберите подготовленный клинический сценарий.";
}

async function analyzeSelectedCase() {
  const caseId = elements.select.value;
  if (!caseId) return;

  setAnalyzeLoading(true);
  try {
    const result = await apiRequest(`/api/v1/demo-cases/${encodeURIComponent(caseId)}/analyze`, {
      method: "POST",
    });
    state.currentResult = result;
    renderResult(result);
    await loadHistory({ silent: true });
    elements.resultSection.classList.remove("hidden");
    elements.resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
    showToast("Исследование обработано и сохранено в истории");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setAnalyzeLoading(false);
  }
}

function setAnalyzeLoading(isLoading) {
  elements.analyzeButton.disabled = isLoading;
  elements.analyzeButton.classList.toggle("loading", isLoading);
  elements.analyzeButton.setAttribute("aria-busy", String(isLoading));
  elements.analyzeButton.querySelector(".button-icon").textContent = isLoading ? "◌" : "↑";
  elements.analyzeButton.querySelector(".button-label").textContent =
    isLoading ? "Выполняется анализ…" : "Запустить анализ";
}

function renderResult(result) {
  const study = result.normalized_study;
  const route = result.routing_decision;
  const safety = result.safety_result;
  const finding = study.findings[0];

  setText("#workflow-status", workflowLabels[result.workflow_status] || result.workflow_status);
  setText("#result-modality", modalityLabels[study.modality] || study.modality);
  setText("#result-study-id", study.study_id);
  setText("#result-pathology", study.pathology_present ? "Выявлена" : "Не выявлена");
  setText("#result-confidence", `${study.overall_confidence}%`);
  setText("#result-finding", finding?.display_name || "Значимые находки не указаны");
  setText("#result-measurements", formatMeasurements(finding?.measurements));
  setText("#result-action", route.action);
  setText("#result-specialty", route.specialty);
  setText("#result-timeframe", route.timeframe);
  setText("#result-reason", route.reason);
  setText("#source-report", study.report);
  setText("#source-conclusion", study.conclusion);
  setText("#result-analysis-id", `ID: ${result.analysis_id}`);

  const priority = document.querySelector("#result-priority");
  priority.textContent = priorityLabels[route.priority] || route.priority;
  priority.className = `priority-pill ${route.priority.toLowerCase().replace("_review", "")}`;

  renderSafety(safety);
  renderTraceability(study, route, safety);
  resetCareJourney(result);
  loadCareJourney(result.analysis_id);
}

function resetCareJourney(result) {
  state.currentJourney = null;
  document.querySelector("#clinician-review-step").classList.remove("hidden");
  document.querySelector("#handoff-confirmation").classList.add("hidden");
  document.querySelector("#care-stage-badge").textContent = "Решение врача";
  document.querySelector("#clinician-note").value = "";
  document.querySelector('input[name="review-choice"][value="RECOMMENDED_SPECIALIST"]').checked = true;
  setText("#recommended-choice-title", result.routing_decision.specialty);

  const blocked = !result.safety_result.route_usable;
  elements.confirmReviewButton.disabled = blocked;
  document.querySelector("#review-blocked-message").classList.toggle("hidden", !blocked);
  updateReviewFooter("pending");
}

async function loadCareJourney(analysisId) {
  try {
    const journey = await apiRequest(
      `/api/v1/analyses/${encodeURIComponent(analysisId)}/care-journey`,
    );
    if (state.currentResult?.analysis_id === analysisId) renderCareJourney(journey);
  } catch (error) {
    if (error.code !== "CARE_JOURNEY_NOT_READY") showToast(error.message, true);
  }
}

async function submitClinicianReview() {
  if (!state.currentResult) return;
  const choice = document.querySelector('input[name="review-choice"]:checked')?.value;
  const note = document.querySelector("#clinician-note").value.trim();

  setButtonLoading(elements.confirmReviewButton, true, "Сохраняем решение…");
  try {
    const journey = await apiRequest(
      `/api/v1/analyses/${encodeURIComponent(state.currentResult.analysis_id)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choice, note: note || null }),
      },
    );
    renderCareJourney(journey);
    await loadHistory({ silent: true });
    showToast("Маршрутизация подтверждена — пациент уведомлён");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setButtonLoading(elements.confirmReviewButton, false, "Подтвердить маршрутизацию");
  }
}

function renderCareJourney(journey) {
  state.currentJourney = journey;
  document.querySelector("#clinician-review-step").classList.add("hidden");
  document.querySelector("#handoff-confirmation").classList.remove("hidden");
  document.querySelector("#care-stage-badge").textContent = "Подтверждено";
  setText(
    "#handoff-status",
    journey.booking_status === "BOOKED" ? "Пациент самостоятельно записался" : "Маршрутизация подтверждена",
  );
  setText("#patient-specialty", journey.specialty);
  setText("#patient-notification-message", journey.notification_message);
  updateReviewFooter(journey.booking_status === "BOOKED" ? "booked" : "patient-ready");
}

function updateReviewFooter(stage) {
  const footer = document.querySelector("#review-footer");
  footer.classList.toggle("patient-ready", stage === "patient-ready");
  footer.classList.toggle("booked", stage === "booked");
  setText("#review-lock", stage === "pending" ? "⌁" : "✓");
  setText(
    "#review-footer-title",
    stage === "booked"
      ? "Пациент самостоятельно выбрал время"
      : stage === "patient-ready"
        ? "Маршрутизация подтверждена"
        : "Решение не отправлено пациенту",
  );
  setText(
    "#review-footer-message",
    stage === "booked"
      ? "Статус записи получен из отдельного пациентского контура."
      : stage === "patient-ready"
        ? "Пациент уведомлён и самостоятельно выберет дату и время."
        : "Требуется подтверждение медицинским специалистом.",
  );
}

function setButtonLoading(button, isLoading, label) {
  button.disabled = isLoading;
  button.classList.toggle("loading", isLoading);
  button.setAttribute("aria-busy", String(isLoading));
  button.querySelector(".button-icon").textContent = isLoading ? "◌" : "✓";
  button.querySelector(".button-label").textContent = label;
}

function renderTraceability(study, route, safety) {
  const trace = [
    ...route.trace,
    {
      stage: "SAFETY_CHECK",
      description: safety.route_usable
        ? "Маршрут прошёл автоматические проверки и передан врачу"
        : "Маршрут остановлен до ручной проверки врачом",
      evidence_paths: safety.issues.flatMap((issue) => issue.evidence_paths || []),
    },
  ];

  document.querySelector("#trace-flow").innerHTML = trace
    .map(
      (step, index) => `
        <div class="trace-step ${index === trace.length - 1 ? "final" : ""}">
          <div class="trace-index">${index + 1}</div>
          <div class="trace-step-copy">
            <small>${escapeHtml(traceStageLabels[step.stage] || step.stage)}</small>
            <strong>${escapeHtml(step.description)}</strong>
            ${renderEvidencePaths(step.evidence_paths)}
          </div>
        </div>
      `,
    )
    .join("");

  renderEvidence(study);
  setText("#trace-rule-id", route.rule_id);
  setText("#trace-policy-version", safety.policy_version);
  setText(
    "#trace-human-review",
    route.requires_human_review ? "Обязательная проверка врача" : "Автоматическая обработка",
  );
}

function renderEvidencePaths(paths = []) {
  const uniquePaths = [...new Set(paths)];
  if (uniquePaths.length === 0) return "";
  return `<div class="evidence-paths">${uniquePaths
    .map((path) => `<code>${escapeHtml(path)}</code>`)
    .join("")}</div>`;
}

function renderEvidence(study) {
  const findingEvidence = study.findings.flatMap((finding) =>
    finding.evidence.map((evidence) => ({
      label: finding.display_name,
      source: evidence.source_path,
      value: formatEvidenceValue(evidence.raw_value),
    })),
  );
  const textEvidence = study.text_signals.map((signal) => ({
    label: `${signal.display_name} · ${signal.source === "CONCLUSION" ? "заключение" : "описание"}`,
    source: signal.evidence[0]?.source_path || signal.source,
    value: `«${signal.matched_text}»`,
  }));
  const evidence = [...findingEvidence, ...textEvidence].slice(0, 6);

  document.querySelector("#trace-evidence").innerHTML = evidence.length
    ? evidence
        .map(
          (item) => `
            <div class="evidence-row">
              <span class="evidence-check">✓</span>
              <div>
                <strong>${escapeHtml(item.label)}</strong>
                <p>${escapeHtml(item.value)}</p>
                <code>${escapeHtml(item.source)}</code>
              </div>
            </div>
          `,
        )
        .join("")
    : '<p class="evidence-empty">Структурированные основания не указаны — требуется ручная проверка.</p>';
}

function formatEvidenceValue(value) {
  if (value === null || value === undefined) return "Значение не указано";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function openSourceDetails() {
  const details = document.querySelector("#source-details");
  details.open = true;
  details.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderSafety(safety) {
  const panel = document.querySelector("#safety-panel");
  const blocked = safety.disposition === "BLOCKED_PENDING_REVIEW";
  const escalated = safety.disposition === "ESCALATE_TO_CLINICIAN";
  panel.classList.toggle("blocked", blocked);
  panel.classList.toggle("escalated", escalated);

  setText("#safety-status", safety.disposition);
  setText(
    "#safety-title",
    blocked
      ? "Автоматический маршрут заблокирован"
      : escalated
        ? "Требуется приоритетная проверка врача"
        : "Маршрут готов к проверке врачом",
  );
  setText(
    "#safety-message",
    blocked
      ? safety.fallback_message || "Нужна ручная проверка исходных данных."
      : "Автоматическое уведомление пациента отключено до подтверждения врача.",
  );
  document.querySelector(".safety-icon").textContent = blocked ? "!" : escalated ? "↑" : "✓";
}

async function loadHistory(options = {}) {
  try {
    state.history = await apiRequest("/api/v1/analyses?limit=100&offset=0");
    renderHistory();
    renderRecentAdmissions();
    renderMetrics();
  } catch (error) {
    elements.historyBody.innerHTML = `<tr><td colspan="6" class="empty-cell">${escapeHtml(error.message)}</td></tr>`;
    elements.recentList.innerHTML = `<div class="recent-empty">${escapeHtml(error.message)}</div>`;
    if (!options.silent) showToast(error.message, true);
  }
}

function renderMetrics() {
  const attention = state.history.filter((item) =>
    ["URGENT", "MANUAL_REVIEW"].includes(item.priority),
  ).length;
  const pending = state.history.filter((item) =>
    ["PENDING_CLINICIAN_REVIEW", "ESCALATED_FOR_REVIEW"].includes(item.workflow_status),
  ).length;

  setText("#metric-total", state.history.length);
  setText("#metric-pending", pending);
  setText("#metric-attention", attention);
  setText("#history-nav-count", state.history.length);
  setText("#doctor-case-count", state.history.length);
}

function renderRecentAdmissions() {
  if (state.history.length === 0) {
    elements.recentList.innerHTML = '<div class="recent-empty">Поступлений пока нет. Запустите первый анализ.</div>';
    return;
  }

  elements.recentList.innerHTML = state.history
    .slice(0, 3)
    .map((item) => {
      const date = new Date(item.created_at);
      const day = new Intl.DateTimeFormat("ru-RU", { day: "2-digit" }).format(date);
      const month = new Intl.DateTimeFormat("ru-RU", { month: "long" }).format(date);
      const scanSymbol = item.modality === "MAMMOGRAPHY" ? "◒" : "◎";
      return `
        <article class="recent-item">
          <div class="recent-date"><strong>${escapeHtml(day)}</strong><span>${escapeHtml(month)}</span></div>
          <div class="recent-scan" aria-hidden="true">${scanSymbol}</div>
          <div class="recent-main">
            <strong>${escapeHtml(modalityLabels[item.modality] || item.modality)}</strong>
            <small>${escapeHtml(item.study_id)} · ${escapeHtml(formatTime(item.created_at))}</small>
          </div>
          <span class="recent-badge ${statusClass(item)}">${escapeHtml(workflowLabels[item.workflow_status] || item.workflow_status)}</span>
          <button class="recent-open" type="button" data-analysis-id="${escapeHtml(item.analysis_id)}" aria-label="Открыть исследование">›</button>
        </article>
      `;
    })
    .join("");

  elements.recentList.querySelectorAll(".recent-open").forEach((button) => {
    button.addEventListener("click", () => openHistoryRecord(button.dataset.analysisId));
  });
}

function renderHistory() {
  if (state.history.length === 0) {
    elements.historyBody.innerHTML = '<tr><td colspan="6" class="empty-cell">История пока пуста. Запустите первый анализ.</td></tr>';
    return;
  }

  elements.historyBody.innerHTML = state.history
    .map(
      (item) => `
        <tr>
          <td class="study-cell">
            <strong>${escapeHtml(item.study_id)}</strong>
            <small>${escapeHtml(item.analysis_id)}</small>
          </td>
          <td>${escapeHtml(modalityLabels[item.modality] || item.modality)}</td>
          <td><span class="table-badge ${item.priority.toLowerCase()}">${escapeHtml(priorityLabels[item.priority] || item.priority)}</span></td>
          <td><span class="table-badge ${statusClass(item)}">${escapeHtml(workflowLabels[item.workflow_status] || item.workflow_status)}</span></td>
          <td>${escapeHtml(formatDate(item.created_at))}</td>
          <td><button class="open-record" type="button" data-analysis-id="${escapeHtml(item.analysis_id)}">Открыть</button></td>
        </tr>
      `,
    )
    .join("");

  document.querySelectorAll(".open-record").forEach((button) => {
    button.addEventListener("click", () => openHistoryRecord(button.dataset.analysisId));
  });
}

async function openHistoryRecord(analysisId) {
  try {
    const result = await apiRequest(`/api/v1/analyses/${encodeURIComponent(analysisId)}`);
    state.currentResult = result;
    renderResult(result);
    elements.resultSection.classList.remove("hidden");
    switchView("dashboard");
    elements.resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message, true);
  }
}

async function apiRequest(url, options = {}) {
  let response;
  try {
    response = await fetch(url, {
      headers: { Accept: "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch (_) {
    const error = new Error(
      "Нет связи с локальным сервером. Проверьте терминал и перезапустите сервер.",
    );
    error.code = "NETWORK_ERROR";
    throw error;
  }
  if (!response.ok) {
    let message = `Ошибка сервера: ${response.status}`;
    let code = "HTTP_ERROR";
    try {
      const body = await response.json();
      message = body.detail?.message || message;
      code = body.detail?.code || code;
    } catch (_) {
      // Keep the HTTP fallback when the body is not JSON.
    }
    const error = new Error(message);
    error.code = code;
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function formatMeasurements(measurements = {}) {
  const labels = {
    x_mm: "размер X",
    y_mm: "размер Y",
    volume_mm3: "объём",
    right_volume_ml: "справа",
    left_volume_ml: "слева",
  };
  return Object.entries(measurements)
    .filter(([key]) => key !== "count_class")
    .map(([key, value]) => `${labels[key] || key}: ${value}${key.includes("_ml") ? " мл" : key.includes("_mm") ? " мм" : ""}`)
    .join(" · ");
}

function statusClass(item) {
  if (item.workflow_status === "BLOCKED_PENDING_REVIEW") return "blocked";
  if (item.safety_disposition === "CLEARED_FOR_REVIEW") return "cleared";
  return "priority";
}

function formatDate(value) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatTime(value) {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value ?? "—";
}

function showToast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("show"), 3200);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
