const patientState = {
  history: [],
  journeyPairs: [],
  activeJourney: null,
  activeAnalysis: null,
  recordFilter: "all",
  recordQuery: "",
  initialized: false,
  loading: false,
};

const patientElements = {
  routeCard: document.querySelector("#patient-route-card"),
  appointments: document.querySelector("#appointments-list"),
  timeline: document.querySelector("#medical-timeline"),
  toast: document.querySelector("#patient-toast"),
  notificationButton: document.querySelector(".notification-button"),
  recordsSearch: document.querySelector("#records-search"),
};

const patientModalityLabels = {
  CT_CHEST: "КТ органов грудной клетки",
  MAMMOGRAPHY: "Маммография",
  UNKNOWN: "Медицинское исследование",
};

const patientWorkflowLabels = {
  PENDING_CLINICIAN_REVIEW: "Проверяется врачом",
  ESCALATED_FOR_REVIEW: "Приоритетная проверка",
  BLOCKED_PENDING_REVIEW: "Требуется проверка",
  PATIENT_ACTION_AVAILABLE: "Маршрут готов",
  APPOINTMENT_BOOKED: "Запись подтверждена",
};

document.addEventListener("DOMContentLoaded", initializePatientCabinet);

async function initializePatientCabinet() {
  bindPatientNavigation();
  bindPatientActions();
  await loadPatientData();
  patientState.initialized = true;
}

function bindPatientNavigation() {
  document.querySelectorAll("[data-patient-nav]").forEach((button) => {
    button.addEventListener("click", () => switchPatientView(button.dataset.patientNav));
  });
}

function bindPatientActions() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => handlePatientAction(button.dataset.action));
  });
  document.querySelectorAll("[data-record-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      patientState.recordFilter = button.dataset.recordFilter;
      document.querySelectorAll("[data-record-filter]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderMedicalTimeline();
    });
  });
  patientElements.recordsSearch.addEventListener("input", (event) => {
    patientState.recordQuery = event.target.value.trim().toLocaleLowerCase("ru-RU");
    renderMedicalTimeline();
  });
  patientElements.notificationButton.addEventListener("click", () => {
    if (patientState.activeJourney) {
      patientElements.routeCard.scrollIntoView({ behavior: "smooth", block: "center" });
      showPatientToast(patientState.activeJourney.notification_message);
    } else {
      showPatientToast("Новых уведомлений пока нет");
    }
  });
  document.addEventListener("visibilitychange", refreshPatientState);
  window.addEventListener("pageshow", refreshPatientState);
}

async function refreshPatientState() {
  if (!patientState.initialized || patientState.loading || document.hidden) return;
  await loadPatientData();
}

function switchPatientView(viewName) {
  document.querySelectorAll("[data-patient-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.patientNav === viewName);
  });
  document.querySelectorAll("[data-patient-view]").forEach((view) => {
    view.classList.toggle("active", view.dataset.patientView === viewName);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function handlePatientAction(action) {
  if (action === "records") {
    switchPatientView("card");
    return;
  }
  if (action === "booking") {
    patientElements.routeCard.scrollIntoView({ behavior: "smooth", block: "center" });
    if (!patientState.activeJourney) showPatientToast("Сначала врач должен подтвердить маршрут");
    return;
  }
  if (action === "all-appointments") {
    switchPatientView("profile");
    showPatientToast("Раздел записей открыт в профиле");
    return;
  }
  showPatientToast("Это демонстрационный раздел прототипа");
}

async function loadPatientData() {
  if (patientState.loading) return;
  patientState.loading = true;
  document.querySelector(".patient-app").setAttribute("aria-busy", "true");
  try {
    patientState.history = await patientApiRequest("/api/v1/analyses?limit=100&offset=0");
    patientState.journeyPairs = (
      await Promise.all(
        patientState.history.slice(0, 30).map(async (historyItem) => ({
          historyItem,
          journey: await loadJourneyIfReady(historyItem.analysis_id),
        })),
      )
    ).filter((pair) => pair.journey);

    const activePair = patientState.journeyPairs[0] || null;
    patientState.activeJourney = activePair?.journey || null;
    patientState.activeAnalysis = activePair
      ? await patientApiRequest(`/api/v1/analyses/${encodeURIComponent(activePair.historyItem.analysis_id)}`)
      : null;

    renderPatientRoute();
    renderAppointments();
    renderMedicalTimeline();
    patientElements.notificationButton.classList.toggle(
      "has-notification",
      patientState.activeJourney?.booking_status === "READY_FOR_PATIENT",
    );
  } catch (error) {
    patientElements.routeCard.innerHTML = `<div class="route-card-empty">${escapePatientHtml(error.message)}</div>`;
    patientElements.appointments.innerHTML = '<div class="appointment-empty">Не удалось загрузить расписание.</div>';
    patientElements.timeline.innerHTML = '<div class="appointment-empty">Не удалось загрузить медицинскую карту.</div>';
    showPatientToast(error.message, true);
  } finally {
    patientState.loading = false;
    document.querySelector(".patient-app").removeAttribute("aria-busy");
  }
}

async function loadJourneyIfReady(analysisId) {
  try {
    return await patientApiRequest(`/api/v1/analyses/${encodeURIComponent(analysisId)}/care-journey`);
  } catch (error) {
    if (error.code === "CARE_JOURNEY_NOT_READY") return null;
    throw error;
  }
}

function renderPatientRoute() {
  const journey = patientState.activeJourney;
  const analysis = patientState.activeAnalysis;
  if (!journey || !analysis) {
    patientElements.routeCard.innerHTML = `
      <div class="route-card-top">
        <div class="route-card-label"><span>♡</span><div><small>Новый маршрут</small><strong>Ожидаем решение врача</strong></div></div>
        <span class="route-status">Нет новых</span>
      </div>
      <p class="route-conclusion">После анализа исследования врач проверит рекомендацию системы. Только после подтверждения здесь появится специалист и выбор времени.</p>
    `;
    return;
  }

  const conclusion = analysis.normalized_study?.conclusion || "Заключение исследования доступно в медицинской карте.";
  const isBooked = journey.booking_status === "BOOKED";
  patientElements.routeCard.innerHTML = `
    <div class="route-card-top">
      <div class="route-card-label"><span>♡</span><div><small>Заключение проверено врачом</small><strong>${escapePatientHtml(patientModalityLabels[analysis.normalized_study?.modality] || "Исследование")}</strong></div></div>
      <span class="route-status">${isBooked ? "Запись готова" : "Новый маршрут"}</span>
    </div>
    <p class="route-conclusion">${escapePatientHtml(conclusion)}</p>
    <div class="route-recommendation"><span>▦</span><div><small>Рекомендация</small><strong>${escapePatientHtml(journey.specialty)}</strong><em>${escapePatientHtml(journey.appointment_target)}</em></div></div>
    ${isBooked ? renderBookedState(journey) : renderBookingSlots(journey)}
  `;

  if (!isBooked) {
    const bookingButton = document.querySelector("#patient-confirm-booking");
    patientElements.routeCard.querySelectorAll('input[name="patient-slot"]').forEach((input) => {
      input.addEventListener("change", () => { bookingButton.disabled = false; });
    });
    bookingButton.addEventListener("click", submitPatientBooking);
  }
}

function renderBookingSlots(journey) {
  if (!journey.available_slots.length) {
    return '<div class="route-card-empty">Свободные интервалы появятся после обновления расписания.</div>';
  }
  return `
    <div class="booking-slots" id="patient-booking-slots">
      ${journey.available_slots.map((slot) => `
        <label class="booking-slot">
          <input type="radio" name="patient-slot" value="${escapePatientHtml(slot.slot_id)}" />
          <strong>${escapePatientHtml(slot.date_label)}</strong><small>${escapePatientHtml(slot.time_label)}</small>
        </label>
      `).join("")}
    </div>
    <button class="patient-primary-button" id="patient-confirm-booking" type="button" disabled>Подтвердить запись</button>
  `;
}

function renderBookedState(journey) {
  const slot = journey.booked_slot;
  return `
    <div class="booking-confirmed"><span>✓</span><div><strong>Запись подтверждена</strong><small>${escapePatientHtml(slot?.date_label || "Дата выбрана")} · ${escapePatientHtml(slot?.time_label || "Время выбрано")}</small></div></div>
  `;
}

async function submitPatientBooking() {
  const selectedSlot = document.querySelector('input[name="patient-slot"]:checked');
  const button = document.querySelector("#patient-confirm-booking");
  if (!selectedSlot || !patientState.activeJourney || !button) return;
  button.classList.add("loading");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    patientState.activeJourney = await patientApiRequest(
      `/api/v1/analyses/${encodeURIComponent(patientState.activeJourney.analysis_id)}/book`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot_id: selectedSlot.value }),
      },
    );
    const pair = patientState.journeyPairs.find(
      (item) => item.journey.analysis_id === patientState.activeJourney.analysis_id,
    );
    if (pair) pair.journey = patientState.activeJourney;
    renderPatientRoute();
    renderAppointments();
    patientElements.notificationButton.classList.remove("has-notification");
    showPatientToast("Запись подтверждена. Врач увидит обновлённый статус.");
  } catch (error) {
    button.classList.remove("loading");
    button.disabled = false;
    button.removeAttribute("aria-busy");
    showPatientToast(error.message, true);
  }
}

function renderAppointments() {
  const bookedJourneys = patientState.journeyPairs
    .map((pair) => pair.journey)
    .filter((journey) => journey.booking_status === "BOOKED" && journey.booked_slot);
  if (!bookedJourneys.length) {
    patientElements.appointments.innerHTML = '<div class="appointment-empty">Подтверждённых записей пока нет. После решения врача выберите удобное время выше.</div>';
    return;
  }
  patientElements.appointments.innerHTML = bookedJourneys.slice(0, 4).map((journey) => {
    const date = new Date(journey.booked_slot.starts_at);
    return `
      <article class="appointment-card">
        <div class="appointment-date"><strong>${formatPatientDate(date, { day: "2-digit" })}</strong><span>${formatPatientDate(date, { month: "long" })}</span></div>
        <div class="appointment-icon">♡</div>
        <div class="appointment-copy"><strong>${escapePatientHtml(journey.specialty)}</strong><small>${escapePatientHtml(journey.appointment_target)}<br />${escapePatientHtml(journey.booked_slot.time_label)}</small></div>
        <i>›</i>
      </article>
    `;
  }).join("");
}

function renderMedicalTimeline() {
  const query = patientState.recordQuery;
  const filter = patientState.recordFilter;
  const records = patientState.history.filter((item) => {
    const title = patientModalityLabels[item.modality] || item.modality;
    const matchesQuery = !query || `${title} ${item.study_id}`.toLocaleLowerCase("ru-RU").includes(query);
    const matchesFilter = filter === "all" || filter === "diagnostics";
    return matchesQuery && matchesFilter;
  });
  if (!records.length) {
    patientElements.timeline.innerHTML = '<div class="appointment-empty">По выбранному фильтру записей нет.</div>';
    return;
  }
  patientElements.timeline.innerHTML = records.slice(0, 12).map((item) => {
    const date = new Date(item.created_at);
    return `
      <article class="medical-record">
        <div class="record-date"><strong>${formatPatientDate(date, { day: "2-digit" })}</strong><span>${formatPatientDate(date, { month: "long" })}</span></div>
        <div class="record-icon">${item.modality === "MAMMOGRAPHY" ? "◒" : "◎"}</div>
        <div class="record-copy"><strong>${escapePatientHtml(patientModalityLabels[item.modality] || item.modality)}</strong><span>Диагностическое исследование</span><small>${escapePatientHtml(item.study_id)}</small></div>
        <span class="record-status">${escapePatientHtml(patientWorkflowLabels[item.workflow_status] || item.workflow_status)}</span>
      </article>
    `;
  }).join("");
}

async function patientApiRequest(url, options = {}) {
  let response;
  try {
    response = await fetch(url, {
      headers: { Accept: "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch (_) {
    const error = new Error("Нет связи с локальным сервером. Проверьте, запущен ли Docker.");
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
      // Keep the HTTP fallback.
    }
    const error = new Error(message);
    error.code = code;
    throw error;
  }
  return response.json();
}

function showPatientToast(message, isError = false) {
  patientElements.toast.textContent = message;
  patientElements.toast.classList.toggle("error", isError);
  patientElements.toast.classList.add("visible");
  window.clearTimeout(showPatientToast.timeoutId);
  showPatientToast.timeoutId = window.setTimeout(() => patientElements.toast.classList.remove("visible"), 3600);
}

function formatPatientDate(date, options) {
  return new Intl.DateTimeFormat("ru-RU", options).format(date);
}

function escapePatientHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
