document.addEventListener('DOMContentLoaded', function() {
    const multiUploadForm = document.getElementById('multi-bilaga-form');
    if (!multiUploadForm) {
        return; 
    }
    
    const multiUploadBtn = document.getElementById('multi-upload-btn');
    const multiUploadSpinner = document.getElementById('multi-upload-spinner');
    const multiUploadInput = document.getElementById('multi_bilaga_files');
    const inboxListTbody = document.getElementById('bilagor-table-body');
    
    const bilagaModal = document.getElementById('bilagaModal');
    const saveMetadataBtn = document.getElementById('save-metadata-btn');

    // 1. Hantera multi-uppladdning
    multiUploadForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        if (multiUploadInput.files.length === 0) {
            alert('Välj minst en fil.');
            return;
        }

        multiUploadBtn.disabled = true;
        multiUploadSpinner.style.display = 'inline-block';
        const formData = new FormData(multiUploadForm);

        try {
            const response = await fetch(`/api/company/${COMPANY_ID}/multi_upload_bilagor`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Något gick fel vid uppladdningen.');
            }

            const uploadedFiles = await response.json();
            document.getElementById('no-bilagor-in-inbox')?.remove();

            uploadedFiles.forEach(file => {
                // 'file' теперь содержит ПРАВИЛЬНЫЕ, вычисленные суммы
                inboxListTbody.insertAdjacentHTML('afterbegin', createBilagaRowHTML(file));
            });
            multiUploadInput.value = '';

        } catch (error) {
            alert('Fel: ' + error.message);
        } finally {
            multiUploadBtn.disabled = false;
            multiUploadSpinner.style.display = 'none';
        }
    });

    // 2. Öppna metadata-modalen
    bilagaModal.addEventListener('show.bs.modal', function(e) {
        const button = e.relatedTarget;
        const bilagaId = button.dataset.bilagaId;
        
        // Заполняем форму
        document.getElementById('metadata-bilaga-id').value = bilagaId;
        document.getElementById('metadata-saljare-namn').value = button.dataset.saljareNamn || '';
        document.getElementById('metadata-saljare-orgnr').value = button.dataset.saljareOrgnr || '';
        document.getElementById('metadata-fakturanr').value = button.dataset.fakturanr || '';
        document.getElementById('metadata-ocr').value = button.dataset.ocr || '';
        document.getElementById('metadata-fakturadatum').value = button.dataset.fakturadatum || '';
        document.getElementById('metadata-forfallodag').value = button.dataset.forfallodag || '';
        
        //
        // ===============================================================
        //  ИСПРАВЛЕНИЕ: Отображаем ПРАВИЛЬНЫЕ суммы
        // ===============================================================
        //
        document.getElementById('metadata-total-amount').value = button.dataset.bruttoAmount || '';
        document.getElementById('metadata-moms-amount').value = button.dataset.momsAmount || '';
        
        // Инициализируем Tom-Select
        const kontoInput = document.getElementById('metadata-suggested-konto');
        if (kontoInput.tomselect) {
            kontoInput.tomselect.destroy();
        }
        if (window.initializeKontoAutocomplete) {
             window.initializeKontoAutocomplete(kontoInput, '#bilagaModal');
        }
        const savedKonto = button.dataset.suggestedKonto || '';
        if (kontoInput.tomselect) {
            kontoInput.tomselect.setValue(savedKonto);
        }
    });

    // 3. Spara metadata
    saveMetadataBtn.addEventListener('click', async function() {
        const bilagaId = document.getElementById('metadata-bilaga-id').value;
        const kontoInput = document.getElementById('metadata-suggested-konto');
        
        const data = {
            fakturadatum: document.getElementById('metadata-fakturadatum').value,
            forfallodag: document.getElementById('metadata-forfallodag').value,
            fakturanr: document.getElementById('metadata-fakturanr').value,
            ocr: document.getElementById('metadata-ocr').value,
            saljare_namn: document.getElementById('metadata-saljare-namn').value,
            saljare_orgnr: document.getElementById('metadata-saljare-orgnr').value,
            brutto_amount: document.getElementById('metadata-total-amount').value,
            moms_amount: document.getElementById('metadata-moms-amount').value,
            suggested_konto: kontoInput.tomselect ? kontoInput.tomselect.getValue() : kontoInput.value
        };
        
        //
        // ===============================================================
        //  ИСПРАВЛЕНИЕ: Вычисляем Netto ПЕРЕД отправкой
        // ===============================================================
        //
        const brutto = parseFloat(data.brutto_amount) || 0;
        const moms = parseFloat(data.moms_amount) || 0;
        const netto = brutto - moms;

        try {
            const response = await fetch(`/api/bilaga/${bilagaId}/metadata`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data) // 'netto' вычисляется на сервере
            });
            if (!response.ok) throw new Error((await response.json()).error);

            // Обновляем data-атрибуты на ОБЕИХ кнопках
            const buttons = document.querySelectorAll(`.btn[data-bilaga-id="${bilagaId}"]`);
            buttons.forEach(editBtn => {
                editBtn.dataset.fakturadatum = data.fakturadatum;
                editBtn.dataset.forfallodag = data.forfallodag;
                editBtn.dataset.fakturanr = data.fakturanr;
                editBtn.dataset.ocr = data.ocr;
                editBtn.dataset.saljareNamn = data.saljare_namn;
                editBtn.dataset.saljareOrgnr = data.saljare_orgnr;
                editBtn.dataset.bruttoAmount = data.brutto_amount;
                editBtn.dataset.momsAmount = data.moms_amount;
                editBtn.dataset.suggestedKonto = data.suggested_konto;
                editBtn.dataset.nettoAmount = netto.toFixed(2); // <-- Обновляем 'netto'
                editBtn.dataset.filename = data.saljare_namn || editBtn.dataset.filename;
            });
            
            // Обновляем текст в строке таблицы
            const row = document.getElementById(`bilaga-card-${bilagaId}`);
            if (row) {
                const kontoName = KONTOPLAN[data.suggested_konto] || '';
                row.querySelector('td:nth-child(1) a').innerHTML = `<strong>${data.saljare_namn || row.querySelector('td:nth-child(1) a').textContent}</strong>`;
                row.querySelector('td:nth-child(2)').textContent = data.fakturadatum || '---';
                row.querySelector('td:nth-child(3)').textContent = brutto > 0 ? brutto.toFixed(2) : '---';
                row.querySelector('td:nth-child(4)').innerHTML = kontoName ? 
                    `<span class="badge bg-light text-dark" style="border: 1px solid #ccc;" title="${data.suggested_konto}">${kontoName}</span>` : '---';
            }
            
            bootstrap.Modal.getInstance(bilagaModal).hide();

        } catch (error) {
            alert('Fel: ' + error.message);
        }
    });

    // Вспомогательная функция для создания HTML-СТРОКИ
    function createBilagaRowHTML(file) {
        // file = {id, filename, url, brutto_amount, moms_amount, suggested_konto, ...}
        
        //
        // ===============================================================
        //  ИСПРАВЛЕНИЕ: Используем ПРАВИЛЬНЫЕ, вычисленные суммы
        // ===============================================================
        //
        const brutto = parseFloat(file.brutto_amount) || 0;
        const moms = parseFloat(file.moms_amount) || 0;
        const netto = parseFloat(file.netto_amount) || 0; // Используем вычисленный 'netto'

        const bruttoStr = brutto > 0 ? brutto.toFixed(2) : '';
        const momsStr = moms > 0 ? moms.toFixed(2) : '';
        const nettoStr = netto > 0 ? netto.toFixed(2) : ''; // (netto = brutto - moms)
        
        const dateStr = file.fakturadatum || '';
        const forfallodagStr = file.forfallodag || '';
        
        const kontoStr = file.suggested_konto || '';
        const kontoName = KONTOPLAN[kontoStr] || '';
        
        const saljareNamn = file.saljare_namn || '';
        const saljareOrgnr = file.saljare_orgnr || '';
        const fakturanr = file.fakturanr || '';
        const ocr = file.ocr || '';

        // Skapa HTML för den nya tabellraden
        return `
        <tr id="bilaga-card-${file.id}">
            <td>
                <a href="#" class="bilaga-preview-link" data-url="${file.url}" data-bs-toggle="modal" data-bs-target="#previewModal">
                    <strong>${saljareNamn || file.filename}</strong>
                </a>
                ${saljareNamn ? `<br><small class="text-muted">${file.filename}</small>` : ''}
            </td>
            <td>${dateStr || '---'}</td>
            <td>${bruttoStr || '---'}</td>
            <td>
                ${kontoName ? `<span class="badge bg-light text-dark" style="border: 1px solid #ccc;" title="${kontoStr}">${kontoName}</span>` : '---'}
            </td>
            <td>
                <span class="badge bg-warning text-dark">Obokförd</span>
            </td>
            <td>
                <button class="btn btn-secondary btn-sm edit-metadata-btn" 
                        data-bs-toggle="modal" 
                        data-bs-target="#bilagaModal"
                        data-bilaga-id="${file.id}"
                        data-saljare-namn="${saljareNamn}"
                        data-saljare-orgnr="${saljareOrgnr}"
                        data-fakturanr="${fakturanr}"
                        data-fakturadatum="${dateStr}"
                        data-forfallodag="${forfallodagStr}"
                        data-ocr="${ocr}"
                        data-brutto-amount="${bruttoStr}"
                        data-netto-amount="${nettoStr}"
                        data-moms-amount="${momsStr}"
                        data-suggested-konto="${kontoStr}">
                    Redigera
                </button>
                <button class="btn btn-success btn-sm bokfor-bilaga-btn" 
                        data-bs-toggle="modal"
                        data-bs-target="#bokforBilagaModal"
                        data-bilaga-id="${file.id}"
                        data-filename="${saljareNamn || file.filename}"
                        data-date="${dateStr}"
                        data-brutto="${bruttoStr}"
                        data-netto="${nettoStr}"
                        data-moms="${momsStr}"
                        data-konto="${kontoStr}">
                    Bokför
                </button>
            </td>
        </tr>
        `;
    }
});