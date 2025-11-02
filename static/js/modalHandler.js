document.addEventListener('DOMContentLoaded', function () {
    const bokforingModal = document.getElementById('bokforingModal');
    if (!bokforingModal) {
        return; // Выходим, если на странице нет модального окна
    }

    // Элементы модального окна
    const entriesContainer = document.getElementById('entries-container');
    const rowTemplate = document.getElementById('entry-row-template');
    const addRowBtn = document.getElementById('add-row-btn');
    const saveBtn = document.getElementById('save-entries-btn');
    const modalAlert = document.getElementById('modal-alert');
    const momsBtnGroup = document.getElementById('moms-btn-group');

    // Элементы Bilagor
    const bilagaForm = document.getElementById('bilaga-form');
    const bilagaList = document.getElementById('bilaga-list');
    const bilagaFileInput = document.getElementById('bilaga_file_input');
    const bilagaUploadBtn = document.getElementById('bilaga-upload-btn');
    const bilagaLoadingPlaceholder = document.getElementById('bilaga-loading-placeholder');
    const bilagaPreview = document.getElementById('bilaga-preview');
    const bilagaPreviewPlaceholder = document.getElementById('bilaga-preview-placeholder');

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

        // Сбрасываем предпросмотр
        bilagaPreview.setAttribute('src', 'about:blank');
        bilagaPreview.style.display = 'none';
        bilagaPreviewPlaceholder.style.display = 'flex';

        // Загружаем данные
        try {
            bilagaLoadingPlaceholder.style.display = 'block';

            const [entriesResponse, bilagorResponse] = await Promise.all([
                fetch(`/get_entries/${currentTransId}`),
                fetch(`/get_bilagor/${currentTransId}`)
            ]);

            if (!entriesResponse.ok) throw new Error('Kunde inte ladda bokföringsrader.');
            if (!bilagorResponse.ok) throw new Error('Kunde inte ladda bilagor.');

            const entries = await entriesResponse.json();
            entries.forEach(entry => createEntryRow(entry.konto, entry.debet, entry.kredit));
            lockBankRow();
            calculateTotals();

            const bilagor = await bilagorResponse.json();
            bilagaLoadingPlaceholder.style.display = 'none';
            updateBilagaList(bilagor);

        } catch (error) {
            bilagaLoadingPlaceholder.style.display = 'none';
            showModalError(error.message);
        }
    });

    // 2. Форма загрузки Bilaga
    bilagaForm.addEventListener('submit', async function(e) {
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

            const fileUrl = getStaticUrl(result.url);
            appendBilagaToList(result.filename, fileUrl, result.id);
            bilagaFileInput.value = '';

        } catch (error) {
            showModalError(error.message);
        } finally {
            bilagaUploadBtn.disabled = false;
            bilagaUploadBtn.textContent = 'Ladda upp';
        }
    });

    // 3. Единый слушатель для списка BILAGOR (Просмотр и Удаление)
    bilagaList.addEventListener('click', async function(e) {
        e.preventDefault();

        // СЛУЧАЙ 1: Клик по ссылке для предпросмотра
        if (e.target.classList.contains('bilaga-preview-link')) {
            const url = e.target.dataset.url;

            bilagaPreview.setAttribute('src', url);
            bilagaPreview.style.display = 'block';
            bilagaPreviewPlaceholder.style.display = 'none';

            bilagaList.querySelectorAll('a').forEach(a => a.classList.remove('fw-bold'));
            e.target.classList.add('fw-bold');
        }

        // СЛУЧАЙ 2: Клик по кнопке "Ta bort"
        if (e.target.classList.contains('remove-bilaga-btn')) {
            if (!confirm('Är du säker på att du vill ta bort denna bilaga?')) {
                return;
            }

            const bilagaId = e.target.dataset.bilagaId;
            const listItem = document.getElementById(`bilaga-item-${bilagaId}`);

            try {
                const response = await fetch(`/delete_bilaga/${bilagaId}`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error);

                listItem.remove();

                if (bilagaPreview.src.includes(listItem.querySelector('a').dataset.url)) {
                    bilagaPreview.setAttribute('src', 'about:blank');
                    bilagaPreview.style.display = 'none';
                    bilagaPreviewPlaceholder.style.display = 'flex';
                }

                if (bilagaList.children.length === 0) {
                    updateBilagaList([]);
                }

            } catch (error) {
                showModalError('Kunde inte ta bort filen: ' + error.message);
            }
        }
    });

    // 4. Кнопка: Добавить новый ряд
    addRowBtn.addEventListener('click', () => createEntryRow('', '', ''));

    // 5. Кнопка: Сохранить
    saveBtn.addEventListener('click', async function() {
        const entries = [];
        const rows = entriesContainer.querySelectorAll('tr');

        rows.forEach(row => {
            const konto = row.querySelector('.konto-input').value;
            const debet = row.querySelector('.debet-input').value;
            const kredit = row.querySelector('.kredit-input').value;

            if (konto) { entries.push({ konto: konto, debet: debet || 0, kredit: kredit || 0 }); }
        });

        if (!validateBalance()) {
            showModalError('Obalans! Debet och Kredit måste vara lika.');
            return;
        }

        try {
            const response = await fetch(`/save_entries/${currentTransId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entries: entries })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Okänt serverfel');

            const modalInstance = bootstrap.Modal.getInstance(bokforingModal);
            if (modalInstance) {
                modalInstance.hide();
            }

            // Логика удаления строки со страницы (для "Bokföring")
            const processedRow = document.getElementById(`trans-row-${result.processed_id}`);
            if (processedRow) {
                // Проверяем, на какой мы странице. Если это "verifikationer", мы не удаляем.
                if (document.body.contains(document.getElementById('bilaga-form'))) {
                    // Мы на странице 'transactions.html', удаляем строку
                    processedRow.style.transition = 'opacity 0.5s ease';
                    processedRow.style.opacity = '0';
                    setTimeout(() => {
                        processedRow.remove();
                    }, 500);
                } else {
                    // Мы на странице 'verifikationer.html', просто обновляем значок
                    const statusBadge = processedRow.querySelector('.badge');
                    if (statusBadge) {
                        statusBadge.textContent = 'processed';
                        statusBadge.className = 'badge bg-success';
                    }
                }
            }
        } catch (error) {
            showModalError(error.message);
        }
    });

    // 6. Кнопки НДС (Moms)
    momsBtnGroup.addEventListener('click', function(event) {
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

    // 7. Единый слушатель для кликов ВНУТРИ таблицы записей (Bookkeeping)
    entriesContainer.addEventListener('click', function(e) {
        // Обработка кнопки "X" (Удалить ряд)
        if (e.target.classList.contains('remove-row-btn')) {
             e.target.closest('tr').remove();
             calculateTotals();
             return;
        }

        // Обработка кликов по полям ввода
        if (e.target.tagName === 'INPUT') {
            const row = e.target.closest('tr');
            if (!row) return;

            const kontoVal = row.querySelector('.konto-input').value;

            if (e.target.classList.contains('debet-input') || e.target.classList.contains('kredit-input')) {
                if (kontoVal !== '1930') {
                    activeRowForMoms = row;
                    enableMomsButtons();
                } else {
                    activeRowForMoms = null;
                    disableMomsButtons();
                }
            }
            else if (e.target.classList.contains('konto-input')) {
                activeRowForMoms = null;
                disableMomsButtons();
            }
        }
    });

    function createEntryRow(konto, debet, kredit) {
        // 1. Клонируем <template>
        const newRow = rowTemplate.content.cloneNode(true).firstElementChild;
        const kontoInput = newRow.querySelector('.konto-input');

        // 2. Заполняем значения
        kontoInput.value = konto;
        newRow.querySelector('.debet-input').value = debet || '';
        newRow.querySelector('.kredit-input').value = kredit || '';

        // 3. Добавляем слушателей для подсчета
        newRow.querySelectorAll('input').forEach(input => {
            input.addEventListener('input', calculateTotals);
        });

        // 4. Добавляем ряд в DOM
        entriesContainer.appendChild(newRow);

        // 5. ВЫЗЫВАЕМ НОВУЮ ГЛОБАЛЬНУЮ ФУНКЦИЮ
        // из 'kontoAutocomplete.js', чтобы превратить
        // этот input в "умный" dropdown.
        if (window.initializeKontoAutocomplete) {
            // Мы даем ему небольшую задержку (0ms), чтобы
            // DOM успел обновиться перед инициализацией Tom-Select
            setTimeout(() => {
                window.initializeKontoAutocomplete(kontoInput);
            }, 0);
        } else {
            console.error("initializeKontoAutocomplete is not defined.");
        }
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
            <a href="#" class="bilaga-preview-link" data-url="${url}">${filename}</a>
            <button type="button" class="btn btn-danger btn-sm remove-bilaga-btn" data-bilaga-id="${id}">Ta bort</button>
        `;
        bilagaList.appendChild(li);
    }

    function getStaticUrl(urlPath) {
        return urlPath; // url_for() уже дает правильный путь
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