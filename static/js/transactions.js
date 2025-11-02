document.addEventListener('DOMContentLoaded', function () {
    const bokforingModal = document.getElementById('bokforingModal');
    // Проверяем, существует ли модальное окно на этой странице. Если нет, выходим.
    if (!bokforingModal) {
        return;
    }

    const entriesContainer = document.getElementById('entries-container');
    const rowTemplate = document.getElementById('entry-row-template');
    const addRowBtn = document.getElementById('add-row-btn');
    const saveBtn = document.getElementById('save-entries-btn');
    const modalAlert = document.getElementById('modal-alert');
    const momsBtnGroup = document.getElementById('moms-btn-group');

    const bilagaForm = document.getElementById('bilaga-form');
    const bilagaList = document.getElementById('bilaga-list');
    const bilagaFileInput = document.getElementById('bilaga_file_input');
    const bilagaUploadBtn = document.getElementById('bilaga-upload-btn');
    const bilagaLoadingPlaceholder = document.getElementById('bilaga-loading-placeholder');

    let currentTransId = null;
    let activeRowForMoms = null;

    // 1. Событие: Модальное окно открывается
    bokforingModal.addEventListener('show.bs.modal', async function (event) {
        const triggerElement = event.relatedTarget;
        currentTransId = triggerElement.getAttribute('data-trans-id');

        // Заполняем инфо
        document.getElementById('modal-trans-id').value = currentTransId;
        document.getElementById('modal-date').textContent = triggerElement.getAttribute('data-date');
        document.getElementById('modal-referens').textContent = triggerElement.getAttribute('data-referens');
        document.getElementById('modal-amount').textContent = triggerElement.getAttribute('data-amount');

        // Сбрасываем состояние
        modalAlert.style.display = 'none';
        entriesContainer.innerHTML = '';
        disableMomsButtons();
        bilagaList.innerHTML = '';
        bilagaFileInput.value = '';

        // Загружаем данные
        try {
            bilagaLoadingPlaceholder.style.display = 'block';

            // Параллельные запросы
            const [entriesResponse, bilagorResponse] = await Promise.all([
                fetch(`/get_entries/${currentTransId}`),
                fetch(`/get_bilagor/${currentTransId}`)
            ]);

            if (!entriesResponse.ok) throw new Error('Kunde inte ladda bokföringsrader.');
            if (!bilagorResponse.ok) throw new Error('Kunde inte ladda bilagor.');

            // Обработка записей
            const entries = await entriesResponse.json();
            entries.forEach(entry => createEntryRow(entry.konto, entry.debet, entry.kredit));
            lockBankRow();
            calculateTotals();

            // Обработка bilagor
            const bilagor = await bilagorResponse.json();
            bilagaLoadingPlaceholder.style.display = 'none';
            updateBilagaList(bilagor);

        } catch (error) {
            bilagaLoadingPlaceholder.style.display = 'none';
            showModalError(error.message);
        }
    });

    // 2. Форма загрузки Bilaga
    bilagaForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        if (!bilagaFileInput.files || bilagaFileInput.files.length === 0) {
            showModalError("Välj en fil att ladda upp.");
            return;
        }

        const formData = new FormData();
        formData.append('bilaga_file', bilagaFileInput.files[0]);

        bilagaUploadBtn.disabled = true;
        bilagaUploadBtn.textContent = 'Laddar upp...';

        try {
            const response = await fetch(`/upload_bilaga/${currentTransId}`, {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Kunde inte ladda upp filen.');

            // Используем 'result.url', который уже содержит /static/...
            const fileUrl = getStaticUrl(result.url);
            appendBilagaToList(result.filename, fileUrl, result.id);
            bilagaFileInput.value = '';

        } catch (error) {
            showModalError(error.message);
        } finally {
            bilagaUploadBtn.disabled = false;
            bilagaUploadBtn.textContent = 'Ladda upp bilaga';
        }
    });


    // 3. Кнопка: Добавить новый ряд
    addRowBtn.addEventListener('click', () => createEntryRow('', '', ''));

    // 4. Кнопка: Сохранить
    // 4. Кнопка: Сохранить
    saveBtn.addEventListener('click', async function () {
        const entries = [];
        const rows = entriesContainer.querySelectorAll('tr');

        rows.forEach(row => {
            const konto = row.querySelector('.konto-input').value;
            const debet = row.querySelector('.debet-input').value;
            const kredit = row.querySelector('.kredit-input').value;

            if (konto) {
                entries.push({
                    konto: konto,
                    debet: debet || 0,
                    kredit: kredit || 0
                });
            }
        });

        if (!validateBalance()) {
            showModalError('Obalans! Debet och Kredit måste vara lika.');
            return;
        }

        try {
            const response = await fetch(`/save_entries/${currentTransId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({entries: entries})
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Okänt serverfel');

            const modalInstance = bootstrap.Modal.getInstance(bokforingModal);
            modalInstance.hide();

            // Обновляем строку в главной таблице
            const processedRow = document.getElementById(`trans-row-${result.processed_id}`);
            if (processedRow) {
                // Находим значок
                const statusBadge = processedRow.querySelector('.badge');
                if (statusBadge) {
                    // Просто меняем его текст и цвет
                    statusBadge.textContent = 'processed';
                    statusBadge.className = 'badge bg-success';
                }
                // Строка остается кликабельной, чтобы ее можно было редактировать.
            }

        } catch (error) {
            showModalError(error.message);
        }
    });

    // 5. Кнопки НДС (Moms)
    momsBtnGroup.addEventListener('click', function (event) {
        if (!event.target.classList.contains('moms-btn') || event.target.disabled) return;
        if (!activeRowForMoms) {
            showModalError('Klicka i en debet- eller kredit-ruta (ej 1930) först.');
            return;
        }

        const rate = parseInt(event.target.dataset.rate, 10);

        const debetInput = activeRowForMoms.querySelector('.debet-input');
        const kreditInput = activeRowForMoms.querySelector('.kredit-input');

        const totalAmount = parseFloat(debetInput.value || 0) || parseFloat(kreditInput.value || 0);
        if (totalAmount === 0) return;

        const isDebet = parseFloat(debetInput.value || 0) > 0;

        const momsKonto = getMomsKonto(rate, isDebet);
        const momsAmount = round(totalAmount * (rate / (100 + rate)), 2);
        const baseAmount = round(totalAmount - momsAmount, 2);

        if (isDebet) {
            debetInput.value = baseAmount;
            createEntryRow(momsKonto, momsAmount, 0);
        } else {
            kreditInput.value = baseAmount;
            createEntryRow(momsKonto, 0, momsAmount);
        }

        calculateTotals();
        activeRowForMoms = null;
        disableMomsButtons();
    });

    // 6. ЕДИНЫЙ слушатель для кликов ВНУТРИ таблицы (Делегирование событий)
    entriesContainer.addEventListener('click', function (e) {
        // Обработка кнопки "X" (Удалить ряд)
        if (e.target.classList.contains('remove-row-btn')) {
            e.target.closest('tr').remove();
            calculateTotals(); // Пересчитываем
            return; // Останавливаем
        }

        // Обработка кликов по полям ввода
        if (e.target.tagName === 'INPUT') {
            const row = e.target.closest('tr');
            if (!row) return;

            const kontoVal = row.querySelector('.konto-input').value;

            // Если кликнули на поле суммы (Debet/Kredit)
            if (e.target.classList.contains('debet-input') || e.target.classList.contains('kredit-input')) {
                if (kontoVal !== '1930') {
                    activeRowForMoms = row;
                    enableMomsButtons();
                } else {
                    activeRowForMoms = null;
                    disableMomsButtons();
                }
            }
            // Если кликнули на поле Konto
            else if (e.target.classList.contains('konto-input')) {
                activeRowForMoms = null;
                disableMomsButtons();
            }
        }
    });

    // --- Вспомогательные функции ---

    function createEntryRow(konto, debet, kredit) {
        const newRow = rowTemplate.content.cloneNode(true).firstElementChild;
        newRow.querySelector('.konto-input').value = konto;
        newRow.querySelector('.debet-input').value = debet || '';
        newRow.querySelector('.kredit-input').value = kredit || '';

        newRow.querySelectorAll('input').forEach(input => {
            input.addEventListener('input', calculateTotals);
        });

        entriesContainer.appendChild(newRow);
    }

    function updateBilagaList(bilagor) {
        bilagaList.innerHTML = '';
        if (bilagor.length === 0) {
            bilagaList.innerHTML = '<li class="list-group-item text-muted" id="no-bilaga-item"><i>Inga bilagor uppladdade.</i></li>';
        } else {
            bilagor.forEach(b => {
                const fileUrl = getStaticUrl(b.url);
                appendBilagaToList(b.filename, fileUrl, b.id);
            });
        }
    }

    function appendBilagaToList(filename, url, id) {
        const noBilagaItem = document.getElementById('no-bilaga-item');
        if (noBilagaItem) noBilagaItem.remove();

        const li = document.createElement('li');
        li.className = 'list-group-item d-flex justify-content-between align-items-center';
        li.setAttribute('id', `bilaga-item-${id}`);
        li.innerHTML = `
            <a href="${url}" target="_blank">${filename}</a>
            <button type="button" class="btn btn-danger btn-sm remove-bilaga-btn" data-bilaga-id="${id}">Ta bort</button>
        `;
        bilagaList.appendChild(li);
    }

    function getStaticUrl(urlPath) {
        // window.location.origin = 'http://127.0.0.1:5000'
        // urlPath = '/static/uploads/company_1/faktura.pdf'
        return window.location.origin + urlPath;
    }

    function lockBankRow() {
        entriesContainer.querySelectorAll('tr').forEach(row => {
            const kontoInput = row.querySelector('.konto-input');
            if (kontoInput.value === '1930') {
                kontoInput.readOnly = true;
                row.querySelector('.debet-input').readOnly = true;
                row.querySelector('.kredit-input').readOnly = true;
                const removeBtn = row.querySelector('.remove-row-btn');
                if (removeBtn) removeBtn.style.display = 'none';
            }
        });
    }

    function calculateTotals() {
        let totalDebet = 0;
        let totalKredit = 0;
        entriesContainer.querySelectorAll('tr').forEach(row => {
            totalDebet += parseFloat(row.querySelector('.debet-input').value || 0);
            totalKredit += parseFloat(row.querySelector('.kredit-input').value || 0);
        });
        document.getElementById('total-debet').textContent = totalDebet.toFixed(2);
        document.getElementById('total-kredit').textContent = totalKredit.toFixed(2);
        validateBalance();
    }

    function validateBalance() {
        const totalDebet = parseFloat(document.getElementById('total-debet').textContent);
        const totalKredit = parseFloat(document.getElementById('total-kredit').textContent);
        const diff = totalDebet - totalKredit;
        const diffEl = document.getElementById('total-diff');
        diffEl.textContent = diff.toFixed(2);

        if (Math.abs(diff) < 0.01 && totalDebet > 0) {
            diffEl.className = 'text-success';
            return true;
        } else {
            diffEl.className = 'text-danger';
            return false;
        }
    }

    function showModalError(message) {
        modalAlert.textContent = message;
        modalAlert.style.display = 'block';
    }

    function enableMomsButtons() {
        momsBtnGroup.querySelectorAll('button').forEach(btn => btn.disabled = false);
    }

    function disableMomsButtons() {
        momsBtnGroup.querySelectorAll('button').forEach(btn => btn.disabled = true);
    }

    function round(value, decimals) {
        return Number(Math.round(value + 'e' + decimals) + 'e-' + decimals);
    }

    function getMomsKonto(rate, isDebet) {
        if (isDebet) { // Ingående moms (покупка)
            if (rate === 25) return '2641';
            if (rate === 12) return '2642';
            if (rate === 6) return '2643';
        } else { // Utgående moms (продажа)
            if (rate === 25) return '2611';
            if (rate === 12) return '2612';
            if (rate === 6) return '2613';
        }
        return '2641'; // По умолчанию
    }
});

// Глобальная функция `removeRow` больше не нужна, так как мы
// используем 'event delegation' (делегирование событий) в слушателе 'entriesContainer'.
// Но мы оставим ее на всякий случай, если `template` будет
// по-старому использовать `onclick`.
function removeRow(button) {
    button.closest('tr').remove();
    document.getElementById('entries-container').dispatchEvent(new Event('input', {bubbles: true}));
}