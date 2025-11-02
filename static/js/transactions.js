document.addEventListener('DOMContentLoaded', function () {
    const bokforingModal = document.getElementById('bokforingModal');
    if (!bokforingModal) {
        return; // Выходим, если мы не на той странице
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
        bilagaPreviewPlaceholder.style.display = 'flex'; // (или 'block')

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

    //
    // ===============================================================
    //  НОВЫЙ ЕДИНЫЙ СЛУШАТЕЛЬ ДЛЯ СПИСКА BILAGOR
    //  (Обрабатывает и просмотр, и удаление)
    // ===============================================================
    //
    bilagaList.addEventListener('click', async function(e) {
        // Останавливаем переход по ссылке (e.g. <a href="#">)
        e.preventDefault();

        // СЛУЧАЙ 1: Клик по ссылке для предпросмотра
        if (e.target.classList.contains('bilaga-preview-link')) {
            const url = e.target.dataset.url;

            // Показываем embed, скрываем заглушку
            bilagaPreview.setAttribute('src', url);
            bilagaPreview.style.display = 'block';
            bilagaPreviewPlaceholder.style.display = 'none';

            // Выделяем активный файл
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

                // Удаляем элемент из списка
                listItem.remove();

                // Если это был просматриваемый файл, очищаем предпросмотр
                if (bilagaPreview.src.includes(listItem.querySelector('a').dataset.url)) {
                    bilagaPreview.setAttribute('src', 'about:blank');
                    bilagaPreview.style.display = 'none';
                    bilagaPreviewPlaceholder.style.display = 'flex';
                }

                // Проверяем, не пустой ли список
                if (bilagaList.children.length === 0) {
                    updateBilagaList([]); // Показываем "Inga bilagor"
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
        // ... (Код сохранения без изменений) ...
        const entries = [];
        const rows = entriesContainer.querySelectorAll('tr');
        rows.forEach(row => { /* ... */ });
        if (!validateBalance()) { /* ... */ }

        try {
            const response = await fetch(`/save_entries/${currentTransId}`, { /* ... */ });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Okänt serverfel');

            const modalInstance = bootstrap.Modal.getInstance(bokforingModal);
            modalInstance.hide();

            const processedRow = document.getElementById(`trans-row-${result.processed_id}`);
            if (processedRow) {
                const statusBadge = processedRow.querySelector('.badge');
                if (statusBadge) {
                    statusBadge.textContent = 'processed';
                    statusBadge.className = 'badge bg-success';
                }
            }

        } catch (error) {
            showModalError(error.message);
        }
    });

    // 6. Кнопки НДС (Moms)
    momsBtnGroup.addEventListener('click', function(event) {
        // ... (Код Moms без изменений) ...
    });

    // 7. Единый слушатель кликов по таблице записей
    entriesContainer.addEventListener('click', function(e) {
        // ... (Код слушателя таблицы без изменений) ...
    });

    // --- Вспомогательные функции ---

    function createEntryRow(konto, debet, kredit) {
        // ... (Код без изменений) ...
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

    //
    // ===============================================================
    //  ОБНОВЛЕННАЯ ФУНКЦИЯ: appendBilagaToList
    //  (Ссылка теперь - это 'a href="#"')
    // ===============================================================
    //
    function appendBilagaToList(filename, url, id) {
        const noBilagaItem = document.getElementById('no-bilaga-item');
        if (noBilagaItem) noBilagaItem.remove();

        const li = document.createElement('li');
        li.className = 'list-group-item d-flex justify-content-between align-items-center';
        li.setAttribute('id', `bilaga-item-${id}`);
        li.innerHTML = `
            <a href="#" class="bilaga-preview-link" data-url="${url}">${filename}</a>
            <button type="button" class="btn btn-danger btn-sm remove-bilaga-btn" data-bilaga-id="${id}">Ta bort</Hbutton>
        `;
        bilagaList.appendChild(li);
    }

    function getStaticUrl(urlPath) {
        // urlPath = '/static/uploads/company_1/faktura.pdf'
        // Мы НЕ используем window.location.origin, так как url_for уже дает правильный относительный путь
        return urlPath;
    }

    // ... (Остальные функции: lockBankRow, calculateTotals, validateBalance, ...)
    // ... (showModalError, enable/disableMomsButtons, round, getMomsKonto)
});

// Глобальная функция removeRow (без изменений)
function removeRow(button) {
    button.closest('tr').remove();
    document.getElementById('entries-container').dispatchEvent(new Event('input', { bubbles: true }));
}