/**
 * Visar ett Bootstrap Alert-meddelande.
 * @param {string} message Meddelandet som ska visas.
 * @param {string} type Typ av meddelande ('success', 'danger', 'warning', 'info').
 * @param {number} duration Hur länge meddelandet ska visas i ms (0 för ingen auto-stängning).
 */
function showBootstrapAlert(message, type = 'info', duration = 5000) {
    const alertContainer = document.getElementById('alert-container');
    if (!alertContainer) {
        console.error('Alert container not found!');
        return;
    }

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.role = 'alert';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Stäng"></button>
    `;

    alertContainer.appendChild(alertDiv);

    if (duration > 0) {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getInstance(alertDiv) || new bootstrap.Alert(alertDiv);
            bsAlert.close();
        }, duration);
    }
}

/**
 * Visar en generisk bekräftelsemodal.
 * @param {string} message Meddelandet som ska visas i modalen.
 * @param {function} callback Funktionen som ska anropas med resultatet (true/false).
 */
function showConfirm(message, callback) {
    const confirmModalElement = document.getElementById('confirmModal');
    if (!confirmModalElement) {
        console.error('Confirm modal not found!');
        callback(false);
        return;
    }

    const confirmModal = new bootstrap.Modal(confirmModalElement);
    document.getElementById('confirmMessage').textContent = message;
    const confirmBtn = document.getElementById('confirmBtn');
    const cancelBtn = confirmModalElement.querySelector('[data-bs-dismiss="modal"]');

    // Rensa gamla event listeners
    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

    const newCancelBtn = cancelBtn.cloneNode(true);
    cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

    newConfirmBtn.onclick = () => { callback(true); confirmModal.hide(); };
    newCancelBtn.onclick = () => { callback(false); confirmModal.hide(); };

    confirmModal.show();
}


/**
 * Skapar en ny rad för en bokföringspost i en modal.
 * @param {HTMLElement} container - Elementet där raden ska läggas till.
 * @param {object} kontoplan - Kontoplanen för att fylla select-elementet.
 * @param {object} entry - Ett objekt med data för posten (konto, debet, kredit).
 */
function createEntryRow(container, kontoplan, entry = {}) {
    const row = document.createElement('div');
    row.className = 'row g-2 mb-2 entry-row';
    row.innerHTML = `
        <div class="col-md-5"><select class="form-select konto-select" name="konto">${Object.entries(kontoplan).map(([nr, desc]) => `<option value="${nr}" ${entry.konto == nr ? 'selected' : ''}>${nr} - ${desc}</option>`).join('')}</select></div>
        <div class="col-md-3"><input type="number" class="form-control debet-input" name="debet" placeholder="Debet" value="${entry.debet || ''}" step="0.01"></div>
        <div class="col-md-3"><input type="number" class="form-control kredit-input" name="kredit" placeholder="Kredit" value="${entry.kredit || ''}" step="0.01"></div>
        <div class="col-md-1"><button type="button" class="btn btn-sm btn-outline-danger remove-entry-row"><i class="bi bi-trash"></i></button></div>
    `;
    container.appendChild(row);
    new TomSelect(row.querySelector('.konto-select'), { create: false, sortField: { field: "text", direction: "asc" } });
}

/**
 * Beräknar och uppdaterar totalsummorna för debet och kredit samt balansen i en modal.
 * @param {HTMLElement} container - Elementet som innehåller entry-rows.
 */
function updateTotals(container) {
    let totalDebet = 0, totalKredit = 0;
    container.querySelectorAll('.entry-row').forEach(row => {
        totalDebet += parseFloat(row.querySelector('.debet-input').value) || 0;
        totalKredit += parseFloat(row.querySelector('.kredit-input').value) || 0;
    });

    document.getElementById('total-debet').textContent = totalDebet.toFixed(2);
    document.getElementById('total-kredit').textContent = totalKredit.toFixed(2);
    
    const balance = totalDebet - totalKredit;
    const balanceEl = document.getElementById('balance');
    balanceEl.textContent = balance.toFixed(2);
    balanceEl.classList.toggle('text-danger', Math.abs(balance) > 0.01);
    balanceEl.classList.toggle('text-success', Math.abs(balance) <= 0.01);
}


/* --- Tema-hantering --- */
const getStoredTheme = () => localStorage.getItem('theme');
const setStoredTheme = (theme) => localStorage.setItem('theme', theme);

const getPreferredTheme = () => {
    const storedTheme = getStoredTheme();
    if (storedTheme) return storedTheme;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

const setTheme = (theme) => {
    if (theme === 'auto') {
        const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        document.documentElement.setAttribute('data-bs-theme', systemTheme);
    } else {
        document.documentElement.setAttribute('data-bs-theme', theme);
    }
};

// Körs direkt för att undvika "flash of unthemed content"
setTheme(getPreferredTheme());

window.addEventListener('DOMContentLoaded', () => {
    // Lyssna på systemförändringar
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        const storedTheme = getStoredTheme();
        if (!storedTheme || storedTheme === 'auto') {
            setTheme(getPreferredTheme());
        }
    });

    // Hantera toggle-knappar
    document.querySelectorAll('[data-bs-theme-value]').forEach((toggle) => {
        toggle.addEventListener('click', () => {
            const theme = toggle.getAttribute('data-bs-theme-value');
            setStoredTheme(theme);
            setTheme(theme);
        });
    });
});
