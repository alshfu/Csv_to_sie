document.addEventListener('DOMContentLoaded', function() {
    const tableBody = document.getElementById('bilagor-table-body');
    const bokforBilagaModal = document.getElementById('bokforBilagaModal');
    let lastFocusedElement;

    if (!tableBody || !bokforBilagaModal) {
        return;
    }

    const entriesContainer = bokforBilagaModal.querySelector('#bokfor-entries-container');
    const addRowBtn = bokforBilagaModal.querySelector('#bokfor-add-row-btn');
    const saveBtn = bokforBilagaModal.querySelector('#bokfor-save-btn');
    const modalAlert = bokforBilagaModal.querySelector('#bokfor-modal-alert');
    const rowTemplate = document.getElementById('entry-row-template');

    const multiUploadForm = document.getElementById('multi-bilaga-form');
    const multiUploadBtn = document.getElementById('multi-upload-btn');
    const multiUploadSpinner = document.getElementById('multi-upload-spinner');
    const multiUploadInput = document.getElementById('multi_bilaga_files');
    const inboxListTbody = document.getElementById('bilagor-table-body');

    // Helper function to format currency with space as thousand separator and comma as decimal
    function formatCurrency(amount) {
        if (amount === null || amount === undefined || isNaN(amount)) {
            return '';
        }
        // Convert to number and fix to 2 decimal places
        const num = parseFloat(amount).toFixed(2);
        // Replace dot with comma for decimal separator
        let parts = num.split('.');
        let integerPart = parts[0];
        let decimalPart = parts[1];

        // Add space as thousand separator
        integerPart = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

        return integerPart + ',' + decimalPart;
    }

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

    bokforBilagaModal.addEventListener('show.bs.modal', function(e) {
        lastFocusedElement = e.relatedTarget;
        const button = e.relatedTarget;
        const bilagaId = button.dataset.bilagaId;

        entriesContainer.innerHTML = '';
        modalAlert.style.display = 'none';

        bokforBilagaModal.querySelector('#bokfor-bilaga-id').value = bilagaId;

        const date = button.dataset.date || new Date().toISOString().split('T')[0];
        const filename = button.dataset.filename || "Okänd Bilaga";
        const brutto = parseFloat(button.dataset.brutto) || 0;
        const netto = parseFloat(button.dataset.netto) || 0;
        const moms = parseFloat(button.dataset.moms) || 0;
        const konto = button.dataset.konto || '';

        bokforBilagaModal.querySelector('#bokfor-datum').value = date;
        bokforBilagaModal.querySelector('#bokfor-ver-text').value = filename;
        
        document.getElementById('metadata-saljare-namn').value = button.dataset.saljareNamn || '';
        document.getElementById('metadata-saljare-orgnr').value = button.dataset.saljareOrgnr || '';
        document.getElementById('metadata-kund-namn').value = button.dataset.kundNamn || '';
        document.getElementById('metadata-kund-orgnr').value = button.dataset.kundOrgnr || '';
        document.getElementById('metadata-fakturanr').value = button.dataset.fakturanr || '';
        document.getElementById('metadata-ocr').value = button.dataset.ocr || '';
        document.getElementById('metadata-fakturadatum').value = button.dataset.fakturadatum || '';
        document.getElementById('metadata-forfallodag').value = button.dataset.forfallodag || '';
        document.getElementById('metadata-total-amount').value = brutto > 0 ? brutto.toFixed(2) : '';
        document.getElementById('metadata-moms-amount').value = moms > 0 ? moms.toFixed(2) : '';

        const costAmount = (netto > 0) ? netto : (brutto - moms);
        createEntryRow(konto || (brutto > 0 ? '1799' : '1798'), costAmount > 0 ? costAmount.toFixed(2) : null, null);

        if (moms > 0) {
            createEntryRow('2641', moms.toFixed(2), null);
        }

        if (brutto > 0) {
            createEntryRow('2440', null, brutto.toFixed(2));
        }

        calculateBokforTotals();
    });

    bokforBilagaModal.addEventListener('hidden.bs.modal', function() {
        if (lastFocusedElement) {
            lastFocusedElement.focus();
        }
    });

    addRowBtn.addEventListener('click', () => {
        createEntryRow('', null, null);
    });

    saveBtn.addEventListener('click', async function() {
        const bilagaId = bokforBilagaModal.querySelector('#bokfor-bilaga-id').value;
        const entries = [];
        entriesContainer.querySelectorAll('tr').forEach(row => {
            entries.push({
                konto: row.querySelector('.konto-input').value,
                debet: row.querySelector('.debet-input').value.replace(/\s/g, '').replace(',', '.') || 0,
                kredit: row.querySelector('.kredit-input').value.replace(/\s/g, '').replace(',', '.') || 0
            });
        });

        if (!validateBokforBalance()) {
            showBokforError('Obalans! Debet och Kredit måste vara lika (och inte noll).');
            return;
        }

        saveBtn.disabled = true;
        saveBtn.textContent = 'Sparar...';

        try {
            const response = await fetch(`/api/bilaga/${bilagaId}/bokfor`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ entries: entries })
            });

            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error);
            }

            bootstrap.Modal.getInstance(bokforBilagaModal).hide();

            const row = document.getElementById(`bilaga-card-${bilagaId}`);
            if (row) {
                row.querySelector('td:nth-child(5)').innerHTML = '<span class="badge bg-success">Bokförd</span>';
                const actionCell = row.querySelector('td:nth-child(6)');
                actionCell.innerHTML = '';
            }

        } catch (error) {
            showBokforError(error.message);
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Spara & Bokför';
        }
    });

    entriesContainer.addEventListener('click', function(e) {
        if (e.target.classList.contains('remove-row-btn')) {
             const row = e.target.closest('tr');
             const tomselectInstance = row.querySelector('.konto-input').tomselect;
             if(tomselectInstance) tomselectInstance.destroy();
             row.remove();
             calculateBokforTotals();
        }
    });

    tableBody.addEventListener('click', async function(e) {
        if (e.target.classList.contains('delete-bilaga-btn')) {
            const bilagaId = e.target.dataset.bilagaId;
            if (confirm('Är du säker på att du vill ta bort denna bilaga?')) {
                try {
                    const response = await fetch(`/api/bilaga/${bilagaId}`, {
                        method: 'DELETE'
                    });
                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.error);
                    }
                    document.getElementById(`bilaga-card-${bilagaId}`).remove();
                } catch (error) {
                    alert('Fel: ' + error.message);
                }
            }
        }
    });

    function createEntryRow(konto, debet, kredit) {
        const newRow = rowTemplate.content.cloneNode(true).firstElementChild;
        const kontoInput = newRow.querySelector('.konto-input');

        newRow.querySelector('.debet-input').value = formatCurrency(debet);
        newRow.querySelector('.kredit-input').value = formatCurrency(kredit);

        newRow.querySelectorAll('input').forEach(input => {
            input.addEventListener('input', calculateBokforTotals);
        });

        entriesContainer.appendChild(newRow);

        if (window.initializeKontoAutocomplete) {
            setTimeout(() => {
                const tomselect = window.initializeKontoAutocomplete(kontoInput, '#bokforBilagaModal');
                if (tomselect) {
                    tomselect.setValue(konto);
                    tomselect.on('change', calculateBokforTotals);
                }
            }, 0);
        }
    }

    function calculateBokforTotals() {
        let totalDebet = 0;
        let totalKredit = 0;
        entriesContainer.querySelectorAll('tr').forEach(row => {
            totalDebet += parseFloat(row.querySelector('.debet-input').value.replace(/\s/g, '').replace(',', '.') || 0);
            totalKredit += parseFloat(row.querySelector('.kredit-input').value.replace(/\s/g, '').replace(',', '.') || 0);
        });

        bokforBilagaModal.querySelector('#bokfor-total-debet').textContent = formatCurrency(totalDebet);
        bokforBilagaModal.querySelector('#bokfor-total-kredit').textContent = formatCurrency(totalKredit);
        validateBokforBalance();
    }

    function validateBokforBalance() {
        const totalDebetText = bokforBilagaModal.querySelector('#bokfor-total-debet').textContent;
        const totalKreditText = bokforBilagaModal.querySelector('#bokfor-total-kredit').textContent;
        const totalDebet = parseFloat(totalDebetText.replace(/\s/g, '').replace(',', '.'));
        const totalKredit = parseFloat(totalKreditText.replace(/\s/g, '').replace(',', '.'));
        const diff = totalDebet - totalKredit;
        const diffEl = bokforBilagaModal.querySelector('#bokfor-total-diff');
        diffEl.textContent = formatCurrency(diff);

        if (Math.abs(diff) < 0.01 && totalDebet > 0) {
            diffEl.className = 'text-success';
            return true;
        } else {
            diffEl.className = 'text-danger';
            return false;
        }
    }

    function showBokforError(message) {
        modalAlert.textContent = message;
        modalAlert.style.display = 'block';
    }

    function createBilagaRowHTML(file) {
        const brutto = parseFloat(file.brutto_amount) || 0;
        const moms = parseFloat(file.moms_amount) || 0;
        const netto = parseFloat(file.netto_amount) || 0;

        const bruttoStr = brutto > 0 ? formatCurrency(brutto) : '';
        const momsStr = moms > 0 ? formatCurrency(moms) : '';
        const nettoStr = netto > 0 ? formatCurrency(netto) : '';
        const dateStr = file.fakturadatum || '';

        const kontoStr = file.suggested_konto || '';
        const kontoName = KONTOPLAN[kontoStr] || '';

        const saljareNamn = file.saljare_namn || '';
        const saljareOrgnr = file.saljare_orgnr || '';
        const saljareBankgiro = file.saljare_bankgiro || '';
        const fakturanr = file.fakturanr || '';
        const ocr = file.ocr || '';
        const forfallodagStr = file.forfallodag || '';
        
        const kundNamn = file.kund_namn || '';
        const kundOrgnr = file.kund_orgnr || '';
        const kundNummer = file.kund_nummer || '';

        return `
        <tr id="bilaga-card-${file.id}">
            <td>
                <a href="#" class="bilaga-preview-link" data-url="${file.url}" data-bs-toggle="modal" data-bs-target="#previewModal">
                    <strong>${saljareNamn || file.filename}</strong>
                </a>
                ${saljareNamn ? `<br><small class="text-muted">${file.filename}</small>` : ''}
            </td>
            <td>${dateStr || '---'}</td>
            <td class="amount-cell">${bruttoStr || '---'}</td>
            <td>
                ${kontoName ? `<span class="badge bg-light text-dark" style="border: 1px solid #ccc;" title="${kontoStr}">${kontoName}</span>` : '---'}
            </td>
            <td>
                <span class="badge bg-warning text-dark">Obokförd</span>
            </td>
            <td>
                <button class="btn btn-secondary btn-sm edit-metadata-btn" 
                        data-bs-toggle="modal" 
                        data-bs-target="#bokforBilagaModal"
                        data-bilaga-id="${file.id}"
                        data-filename="${saljareNamn || file.filename}"
                        data-date="${dateStr}"
                        data-brutto="${brutto}"
                        data-netto="${netto}"
                        data-moms="${moms}"
                        data-konto="${kontoStr}"
                        data-fakturanr="${fakturanr}"
                        data-ocr="${ocr}"
                        data-forfallodag="${forfallodagStr}"
                        data-saljare-namn="${saljareNamn}"
                        data-saljare-orgnr="${saljareOrgnr}"
                        data-saljare-bankgiro="${saljareBankgiro}"
                        data-kund-namn="${kundNamn}"
                        data-kund-orgnr="${kundOrgnr}"
                        data-kund-nummer="${kundNummer}">
                    Redigera
                </button>
                <button class="btn btn-success btn-sm bokfor-bilaga-btn" 
                        data-bs-toggle="modal"
                        data-bs-target="#bokforBilagaModal"
                        data-bilaga-id="${file.id}"
                        data-filename="${saljareNamn || file.filename}"
                        data-date="${dateStr}"
                        data-brutto="${brutto}"
                        data-netto="${netto}"
                        data-moms="${moms}"
                        data-konto="${kontoStr}">
                    Bokför
                </button>
                <button class="btn btn-danger btn-sm delete-bilaga-btn" data-bilaga-id="${file.id}">Ta bort</button>
            </td>
        </tr>
        `;
    }
});