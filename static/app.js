const positionsBody = document.querySelector("#positions-body");
const addPositionForm = document.querySelector("#add-position-form");
const positionNameInput = document.querySelector("#position-name");
const saveButton = document.querySelector("#save-button");
const loadButton = document.querySelector("#load-button");
const fileInput = document.querySelector("#file-input");
const notice = document.querySelector("#notice");
const rulesDialog = document.querySelector("#rules-dialog");
const rulesForm = document.querySelector("#rules-form");
const rulesTitle = document.querySelector("#rules-title");
const rulesBody = document.querySelector("#rules-body");
const closeDialogButton = document.querySelector("#close-dialog");
const cancelRulesButton = document.querySelector("#cancel-rules");

let state = { positions: [], dependencies: [] };
let editedPosition = null;
let noticeTimer = null;

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatNumber(value) {
    return new Intl.NumberFormat("uk-UA", {
        maximumFractionDigits: 6,
    }).format(value);
}

function describeApiError(detail) {
    if (Array.isArray(detail)) {
        return detail.map((item) => item.msg || "Некоректні дані").join("; ");
    }
    return String(detail || "Невідома помилка сервера");
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(describeApiError(payload.detail));
    }
    return payload;
}

function showNotice(message, isError = false) {
    clearTimeout(noticeTimer);
    notice.textContent = message;
    notice.classList.toggle("error", isError);
    notice.hidden = false;
    noticeTimer = window.setTimeout(() => {
        notice.hidden = true;
    }, 6000);
}

function renderState() {
    if (!state.positions.length) {
        positionsBody.innerHTML = `
            <tr>
                <td class="empty-state" colspan="14">
                    Посад ще немає. Додайте першу посаду у формі вище.
                </td>
            </tr>`;
        return;
    }

    positionsBody.innerHTML = state.positions.map((position) => {
        const cells = position.levels.flatMap((level) => [
            `<td>${formatNumber(level.base_salary)}</td>`,
            `<td>${formatNumber(level.bonus)}</td>`,
            `<td><strong>${formatNumber(level.total)}</strong></td>`,
        ]).join("");
        const safeName = escapeHtml(position.name);
        return `
            <tr>
                <td>${safeName}</td>
                ${cells}
                <td class="actions-cell">
                    <div class="row-actions">
                        <button class="button button-secondary button-small edit-rules" data-position="${safeName}" type="button">Правила</button>
                        <button class="button button-danger button-small delete-position" data-position="${safeName}" type="button">Видалити</button>
                    </div>
                </td>
            </tr>`;
    }).join("");
}

async function refreshState() {
    state = await requestJson("/api/state");
    renderState();
}

function positionOptions(selectedPosition) {
    const options = ['<option value="">Без залежності</option>'];
    for (const position of state.positions) {
        const selected = position.name === selectedPosition ? " selected" : "";
        const safeName = escapeHtml(position.name);
        options.push(`<option value="${safeName}"${selected}>${safeName}</option>`);
    }
    return options.join("");
}

function syncRuleRow(row) {
    const sourcePosition = row.querySelector(".source-position").value;
    const dependent = Boolean(sourcePosition);
    row.querySelector(".base-salary").readOnly = dependent;
    row.querySelector(".bonus").readOnly = dependent;
    row.querySelector(".source-level").disabled = !dependent;
    row.querySelector(".salary-formula").disabled = !dependent;
    row.querySelector(".bonus-formula").disabled = !dependent;
}

function openRules(positionName) {
    const position = state.positions.find((item) => item.name === positionName);
    if (!position) {
        showNotice("Посаду не знайдено. Оновіть сторінку.", true);
        return;
    }

    editedPosition = position.name;
    rulesTitle.textContent = position.name;
    rulesBody.innerHTML = position.levels.map((level) => {
        const sourceLevelOptions = [1, 2, 3, 4].map((sourceLevel) => {
            const selected = sourceLevel === level.from_level ? " selected" : "";
            return `<option value="${sourceLevel}"${selected}>${sourceLevel}</option>`;
        }).join("");
        return `
            <tr data-level="${level.level}">
                <td><strong>${level.level}</strong></td>
                <td><input class="base-salary" type="number" step="any" value="${level.base_salary}" required></td>
                <td><input class="bonus" type="number" step="any" value="${level.bonus}" required></td>
                <td>
                    <select class="source-position">${positionOptions(level.from_position)}</select>
                </td>
                <td>
                    <select class="source-level">${sourceLevelOptions}</select>
                </td>
                <td><input class="salary-formula formula-input" value="${escapeHtml(level.formula_salary || "S")}" required></td>
                <td><input class="bonus-formula formula-input" value="${escapeHtml(level.formula_bonus || "B")}" required></td>
            </tr>`;
    }).join("");

    for (const row of rulesBody.querySelectorAll("tr")) {
        row.querySelector(".source-position").addEventListener("change", () => syncRuleRow(row));
        syncRuleRow(row);
    }
    rulesDialog.showModal();
}

addPositionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = positionNameInput.value.trim();
    try {
        state = await requestJson("/api/positions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name }),
        });
        positionNameInput.value = "";
        renderState();
        showNotice(`Посаду «${name}» додано.`);
    } catch (error) {
        showNotice(error.message, true);
    }
});

positionsBody.addEventListener("click", async (event) => {
    const editButton = event.target.closest(".edit-rules");
    if (editButton) {
        openRules(editButton.dataset.position);
        return;
    }

    const deleteButton = event.target.closest(".delete-position");
    if (!deleteButton) {
        return;
    }
    const positionName = deleteButton.dataset.position;
    if (!window.confirm(`Видалити посаду «${positionName}» та пов’язані залежності?`)) {
        return;
    }
    try {
        state = await requestJson(`/api/positions/${encodeURIComponent(positionName)}`, {
            method: "DELETE",
        });
        renderState();
        showNotice(`Посаду «${positionName}» видалено.`);
    } catch (error) {
        showNotice(error.message, true);
    }
});

rulesForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!rulesForm.reportValidity() || !editedPosition) {
        return;
    }

    const rules = [...rulesBody.querySelectorAll("tr")].map((row) => {
        const fromPosition = row.querySelector(".source-position").value || null;
        return {
            level: Number(row.dataset.level),
            base_salary: Number(row.querySelector(".base-salary").value),
            bonus: Number(row.querySelector(".bonus").value),
            from_position: fromPosition,
            from_level: fromPosition ? Number(row.querySelector(".source-level").value) : null,
            formula_salary: fromPosition ? row.querySelector(".salary-formula").value.trim() : "",
            formula_bonus: fromPosition ? row.querySelector(".bonus-formula").value.trim() : "",
        };
    });

    try {
        state = await requestJson(`/api/positions/${encodeURIComponent(editedPosition)}/rules`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rules }),
        });
        renderState();
        rulesDialog.close();
        showNotice(`Правила посади «${editedPosition}» збережено та перераховано.`);
        editedPosition = null;
    } catch (error) {
        showNotice(error.message, true);
    }
});

function closeRules() {
    rulesDialog.close();
    editedPosition = null;
}

closeDialogButton.addEventListener("click", closeRules);
cancelRulesButton.addEventListener("click", closeRules);
rulesDialog.addEventListener("cancel", () => {
    editedPosition = null;
});

saveButton.addEventListener("click", async () => {
    try {
        const response = await fetch("/api/export");
        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(describeApiError(payload.detail));
        }
        const blob = await response.blob();
        const downloadUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = downloadUrl;
        link.download = "salary_dependency_manager.csv";
        document.body.append(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(downloadUrl);
        showNotice("CSV-файл збережено.");
    } catch (error) {
        showNotice(error.message, true);
    }
});

loadButton.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", async () => {
    const [file] = fileInput.files;
    if (!file) {
        return;
    }
    if (state.positions.length && !window.confirm("Завантаження замінить поточні дані. Продовжити?")) {
        fileInput.value = "";
        return;
    }

    try {
        const response = await fetch("/api/import", {
            method: "POST",
            headers: { "Content-Type": "text/csv" },
            body: await file.arrayBuffer(),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(describeApiError(payload.detail));
        }
        state = payload;
        renderState();
        showNotice(`Файл «${file.name}» завантажено.`);
    } catch (error) {
        showNotice(error.message, true);
    } finally {
        fileInput.value = "";
    }
});

refreshState().catch((error) => showNotice(error.message, true));
