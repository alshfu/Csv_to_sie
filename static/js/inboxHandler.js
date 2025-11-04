document.addEventListener('DOMContentLoaded', function() {
    const multiUploadForm = document.getElementById('multi-bilaga-form');
    if (!multiUploadForm) { return; } // Мы не на той странице

    const multiUploadBtn = document.getElementById('multi-upload-btn');
    const multiUploadSpinner = document.getElementById('multi-upload-spinner');
    const multiUploadInput = document.getElementById('multi_bilaga_files');
    const inboxList = document.getElementById('unassigned-bilagor-list');

    const bilagaModal = document.getElementById('bilagaModal');
    const saveMetadataBtn = document.getElementById('save-metadata-btn');

    // 1. Обработка мульти-загрузки
    multiUploadForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        if (multiUploadInput.files.length === 0) {
            alert('Välj en eller flera filer.');
            return;
        }

        multiUploadBtn.disabled = true;
        multiUploadSpinner.style.display = 'inline-block';

        const formData = new FormData();
        for (const file of multiUploadInput.files) {
            formData.append('files', file);
        }

        try {
            const response = await fetch(`/multi_upload_bilagor/${COMPANY_ID}`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Något gick fel vid uppladdningen');
            }

            const uploadedFiles = await response.json();
            document.getElementById('no-bilagor-in-inbox')?.remove();

            uploadedFiles.forEach(file => {
                inboxList.insertAdjacentHTML('afterbegin', createBilagaCardHTML(file));
            });
            multiUploadInput.value = '';

        } catch (error) {
            alert('Fel: ' + error.message);
        } finally {
            multiUploadBtn.disabled = false;
            multiUploadSpinner.style.display = 'none';
        }
    });

    // 2. Открытие модального окна метаданных
    bilagaModal.addEventListener('show.bs.modal', function(e) {
        const button = e.relatedTarget;
        const bilagaId = button.dataset.bilagaId;

        document.getElementById('metadata-bilaga-id').value = bilagaId;
        document.getElementById('metadata-bilaga-date').value = button.dataset.bilagaDate || '';
        document.getElementById('metadata-brutto-amount').value = button.dataset.bruttoAmount || '';
        document.getElementById('metadata-moms-amount').value = button.dataset.momsAmount || '';

        const kontoInput = document.getElementById('metadata-suggested-konto');

        if (kontoInput.tomselect) {
            kontoInput.tomselect.destroy();
        }

        if (window.initializeKontoAutocomplete) {
            //
            // ===============================================================
            //  HÄR ÄR FIXEN (Del 3): Skicka med ID för BILAGA-modalen
            // ===============================================================
            //
             window.initializeKontoAutocomplete(kontoInput, '#bilagaModal');
        }

        const savedKonto = button.dataset.suggestedKonto || '';
        if (kontoInput.tomselect) {
            kontoInput.tomselect.setValue(savedKonto);
        }
    });

    // 3. Сохранение метаданных
    saveMetadataBtn.addEventListener('click', async function() {
        const bilagaId = document.getElementById('metadata-bilaga-id').value;
        const kontoInput = document.getElementById('metadata-suggested-konto');

        const data = {
            bilaga_date: document.getElementById('metadata-bilaga-date').value,
            brutto_amount: document.getElementById('metadata-brutto-amount').value,
            moms_amount: document.getElementById('metadata-moms-amount').value,
            suggested_konto: kontoInput.tomselect ? kontoInput.tomselect.getValue() : kontoInput.value
        };

        const brutto = parseFloat(data.brutto_amount) || 0;
        const moms = parseFloat(data.moms_amount) || 0;
        const netto = brutto - moms;

        try {
            const response = await fetch(`/update_bilaga_metadata/${bilagaId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error((await response.json()).error);

            const editBtn = document.querySelector(`.edit-metadata-btn[data-bilaga-id="${bilagaId}"]`);
            if (editBtn) {
                editBtn.dataset.bilagaDate = data.bilaga_date;
                editBtn.dataset.bruttoAmount = data.brutto_amount;
                editBtn.dataset.momsAmount = data.moms_amount;
                editBtn.dataset.suggestedKonto = data.suggested_konto;
                editBtn.dataset.nettoAmount = netto.toFixed(2);
            }

            const card = document.getElementById(`bilaga-card-${bilagaId}`);
            if (card) {
                card.querySelector('.bilaga-card-info').innerHTML =
                    createBilagaInfoHTML(data.brutto_amount, data.bilaga_date, data.suggested_konto);
            }

            bootstrap.Modal.getInstance(bilagaModal).hide();

        } catch (error) {
            alert('Fel: ' + error.message);
        }
    });

// Вспомогательная функция для создания HTML карточки
    function createBilagaCardHTML(file) {
        // file = {id, filename, url, brutto_amount, moms_amount, suggested_konto, ...}

        const brutto = parseFloat(file.brutto_amount) || 0;
        const moms = parseFloat(file.moms_amount) || 0;
        const netto = brutto - moms;

        const bruttoStr = brutto > 0 ? brutto.toFixed(2) : '';
        const momsStr = moms > 0 ? moms.toFixed(2) : '';
        const nettoStr = netto > 0 ? netto.toFixed(2) : '';
        const dateStr = file.bilaga_date || '';

        //
        // ===============================================================
        //  ИСПРАВЛЕНИЕ: Читаем 'suggested_konto' и ищем имя в KONTOPLAN
        // ===============================================================
        //
        const kontoStr = file.suggested_konto || '';
        const kontoName = KONTOPLAN[kontoStr] || ''; // KONTOPLAN определен в HTML

        return `
        <div class="card card-body mb-2" id="bilaga-card-${file.id}">
            <a href="#" class="bilaga-preview-link" data-url="${file.url}">
                ${file.filename}
            </a>
            <div class="bilaga-card-info" style="font-size: 0.9em;">
                ${createBilagaInfoHTML(file.brutto_amount, file.bilaga_date, kontoName)}
            </div>
            <button class="btn btn-secondary btn-sm mt-2 edit-metadata-btn" 
                    data-bs-toggle="modal" 
                    data-bs-target="#bilagaModal"
                    data-bilaga-id="${file.id}"
                    data-bilaga-date="${dateStr}"
                    data-brutto-amount="${bruttoStr}"
                    data-netto-amount="${nettoStr}"
                    data-moms-amount="${momsStr}"
                    data-suggested-konto="${kontoStr}"> Redigera info
            </button>
        </div>
        `;
    }
    // Вспомогательная функция для генерации инфо-строки
    function createBilagaInfoHTML(brutto, date, konto) {
        let parts = [];
        if (date) parts.push(`<strong>Datum:</strong> ${date}`);
        if (parseFloat(brutto)) parts.push(`<strong>Belopp:</strong> ${brutto} SEK`);
        if (konto && KONTOPLAN[konto]) parts.push(`<strong>Konto:</strong> ${KONTOPLAN[konto]}`);

        if (parts.length > 0) {
            return parts.join(' | ');
        }
        return '<small class="text-muted">Status: unassigned</small>';
    }
});