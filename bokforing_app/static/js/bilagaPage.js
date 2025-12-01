document.addEventListener('DOMContentLoaded', function() {
    const tableBody = document.getElementById('bilagor-table-body');
    const bokforBilagaModal = document.getElementById('bokforBilagaModal');
    let lastFocusedElement;

    if (!tableBody || !bokforBilagaModal) {
        return;
    }

    // === PDF.js Viewer State ===
    let pdfDoc = null;
    let pageNum = 1;
    let pageRendering = false;
    let pageNumPending = null;
    let pdfScale = 1.0; // Начальный масштаб
    const pdfCanvas = document.getElementById('pdf-canvas');
    const pdfCtx = pdfCanvas.getContext('2d');
    const pdfViewerContainer = document.getElementById('pdf-viewer-container');
    const zoomPercentSpan = document.getElementById('pdf-zoom-percent');

    const entriesContainer = bokforBilagaModal.querySelector('#bokfor-entries-container');
    const addRowBtn = bokforBilagaModal.querySelector('#bokfor-add-row-btn');
    const saveMetadataBtn = bokforBilagaModal.querySelector('#save-metadata-btn');
    const bokforBtn = bokforBilagaModal.querySelector('#bokfor-btn');
    const modalAlert = bokforBilagaModal.querySelector('#bokfor-modal-alert');
    const rowTemplate = document.getElementById('entry-row-template');

    const multiUploadForm = document.getElementById('multi-bilaga-form');
    const multiUploadBtn = document.getElementById('multi-upload-btn');
    const multiUploadSpinner = document.getElementById('multi-upload-spinner');
    const multiUploadInput = document.getElementById('multi_bilaga_files');
    const inboxListTbody = document.getElementById('bilagor-table-body');

    function showBokforError(message) {
        console.error("Bokforing Error:", message);
        modalAlert.textContent = message;
        modalAlert.style.display = 'block';
        setTimeout(() => { modalAlert.style.display = 'none'; }, 5000);
    }

    function formatCurrency(amount) {
        if (amount === null || amount === undefined || isNaN(amount)) {
            return '';
        }
        const num = parseFloat(amount).toFixed(2);
        let parts = num.split('.');
        let integerPart = parts[0];
        let decimalPart = parts[1];
        integerPart = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
        return integerPart + ',' + decimalPart;
    }

    // === PDF.js Functions ===
    async function renderPdfPage(num) {
        pageRendering = true;
        document.getElementById('pdf-page-num').textContent = num;
        zoomPercentSpan.textContent = `${Math.round(pdfScale * 100)}%`;

        const page = await pdfDoc.getPage(num);
        const viewport = page.getViewport({ scale: pdfScale });

        pdfCanvas.height = viewport.height;
        pdfCanvas.width = viewport.width;

        const renderContext = {
            canvasContext: pdfCtx,
            viewport: viewport
        };
        const renderTask = page.render(renderContext);

        await renderTask.promise;
        pageRendering = false;
        if (pageNumPending !== null) {
            renderPdfPage(pageNumPending);
            pageNumPending = null;
        }
    }

    function queueRenderPage(num) {
        if (pageRendering) {
            pageNumPending = num;
        } else {
            renderPdfPage(num);
        }
    }

    async function loadPdf(url) {
        try {
            const loadingTask = window.pdfjsLib.getDocument(url);
            pdfDoc = await loadingTask.promise;
            document.getElementById('pdf-page-count').textContent = pdfDoc.numPages;
            pageNum = 1;
            pdfScale = 1.0; // Устанавливаем начальный масштаб 100%

            renderPdfPage(pageNum);
        } catch (error) {
            showBokforError(`Kunde inte ladda PDF-filen: ${error.message}`);
        }
    }

    document.getElementById('pdf-prev').addEventListener('click', () => {
        if (pageNum <= 1) return;
        pageNum--;
        queueRenderPage(pageNum);
    });

    document.getElementById('pdf-next').addEventListener('click', () => {
        if (pageNum >= pdfDoc.numPages) return;
        pageNum++;
        queueRenderPage(pageNum);
    });

    document.getElementById('pdf-zoom-in').addEventListener('click', () => {
        if (!pdfDoc) return;
        pdfScale += 0.2;
        queueRenderPage(pageNum);
    });

    document.getElementById('pdf-zoom-out').addEventListener('click', () => {
        if (!pdfDoc || pdfScale <= 0.3) return;
        pdfScale -= 0.2;
        queueRenderPage(pageNum);
    });


    multiUploadForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        if (multiUploadInput.files.length === 0) {
            console.warn('Välj minst en fil.');
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
            showBokforError(`Fel vid uppladdning: ${error.message}`);
        } finally {
            multiUploadBtn.disabled = false;
            multiUploadSpinner.style.display = 'none';
        }
    });

    bokforBilagaModal.addEventListener('show.bs.modal', function(e) {
        lastFocusedElement = e.relatedTarget;
        const button = e.relatedTarget;
        const bilagaId = button.dataset.bilagaId;
        const fileUrl = button.dataset.url;

        if (fileUrl && fileUrl.toLowerCase().endsWith('.pdf')) {
             document.getElementById('pdf-viewer-container').style.display = 'block';
             loadPdf(fileUrl);
        } else {
             document.getElementById('pdf-viewer-container').style.display = 'none';
        }

        entriesContainer.innerHTML = '';
        modalAlert.style.display = 'none';

        bokforBilagaModal.querySelector('#bokfor-bilaga-id').value = bilagaId;

        const brutto = parseFloat(button.dataset.brutto) || 0;
        const netto = parseFloat(button.dataset.netto) || 0;
        const moms = parseFloat(button.dataset.moms) || 0;
        const konto = button.dataset.konto || '';

        document.getElementById('metadata-saljare-namn').value = button.dataset.saljareNamn || '';
        document.getElementById('metadata-saljare-orgnr').value = button.dataset.saljareOrgnr || '';
        document.getElementById('metadata-saljare-momsregnr').value = button.dataset.saljareMomsregnr || '';
        document.getElementById('metadata-saljare-bankgiro').value = button.dataset.saljareBankgiro || '';
        document.getElementById('metadata-kund-namn').value = button.dataset.kundNamn || '';
        document.getElementById('metadata-kund-orgnr').value = button.dataset.kundOrgnr || '';
        document.getElementById('metadata-kund-nummer').value = button.dataset.kundNummer || '';
        document.getElementById('metadata-kund-adress').value = button.dataset.kundAdress || '';
        document.getElementById('metadata-fakturanr').value = button.dataset.fakturanr || '';
        document.getElementById('metadata-ocr').value = button.dataset.ocr || '';
        document.getElementById('metadata-fakturadatum').value = button.dataset.date || '';
        document.getElementById('metadata-forfallodag').value = button.dataset.forfallodag || '';
        document.getElementById('metadata-total-netto').value = button.dataset.totalNetto || '';
        document.getElementById('metadata-total-moms').value = button.dataset.totalMoms || '';
        document.getElementById('metadata-total-brutto').value = button.dataset.totalBrutto || '';
        document.getElementById('metadata-att-betala').value = button.dataset.attBetala || '';

        const costAmount = (netto > 0) ? netto : (brutto - moms);
        createEntryRow(konto || (brutto > 0 ? '4010' : ''), costAmount > 0 ? costAmount.toFixed(2) : null, null);

        if (moms > 0) {
            createEntryRow('2641', moms.toFixed(2), null);
        }

        if (brutto > 0) {
            createEntryRow('2440', null, brutto.toFixed(2));
        }

        calculateBokforTotals();
    });

    bokforBilagaModal.addEventListener('hidden.bs.modal', function() {
        pdfDoc = null;
        pageNum = 1;
        pdfCtx.clearRect(0, 0, pdfCanvas.width, pdfCanvas.height);

        if (lastFocusedElement) {
            lastFocusedElement.focus();
        }
    });

    addRowBtn.addEventListener('click', () => {
        createEntryRow('', null, null);
    });

    saveMetadataBtn.addEventListener('click', async function() {
        const bilagaId = bokforBilagaModal.querySelector('#bokfor-bilaga-id').value;
        const data = {
            fakturadatum: document.getElementById('metadata-fakturadatum').value,
            forfallodag: document.getElementById('metadata-forfallodag').value,
            fakturanr: document.getElementById('metadata-fakturanr').value,
            ocr: document.getElementById('metadata-ocr').value,
            saljare_namn: document.getElementById('metadata-saljare-namn').value,
            saljare_orgnr: document.getElementById('metadata-saljare-orgnr').value,
            saljare_momsregnr: document.getElementById('metadata-saljare-momsregnr').value,
            saljare_bankgiro: document.getElementById('metadata-saljare-bankgiro').value,
            kund_namn: document.getElementById('metadata-kund-namn').value,
            kund_orgnr: document.getElementById('metadata-kund-orgnr').value,
            kund_nummer: document.getElementById('metadata-kund-nummer').value,
            kund_adress: document.getElementById('metadata-kund-adress').value,
            total_netto: document.getElementById('metadata-total-netto').value,
            total_moms: document.getElementById('metadata-total-moms').value,
            total_brutto: document.getElementById('metadata-total-brutto').value,
            att_betala: document.getElementById('metadata-att-betala').value,
            suggested_konto: document.getElementById('bokfor-entries-container').querySelector('.konto-input').value
        };

        try {
            const response = await fetch(`/api/bilaga/${bilagaId}/metadata`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error((await response.json()).error);
            
            // Använd en diskret notifiering istället för alert
            const saveBtn = document.getElementById('save-metadata-btn');
            const originalText = saveBtn.textContent;
            saveBtn.textContent = 'Sparat!';
            setTimeout(() => {
                saveBtn.textContent = originalText;
                location.reload(); // Ladda om sidan för att se ändringar
            }, 1500);

        } catch (error) {
            showBokforError(`Fel vid sparning: ${error.message}`);
        }
    });

    bokforBtn.addEventListener('click', async function() {
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

        bokforBtn.disabled = true;
        bokforBtn.textContent = 'Bokför...';

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
                const editBtn = row.querySelector('.edit-metadata-btn');
                if (editBtn) {
                    editBtn.dataset.status = 'bokford';
                    editBtn.innerHTML = 'Granska / Redigera';
                }
                row.querySelector('.bokfor-bilaga-btn')?.remove();
            }

        } catch (error) {
            showBokforError(error.message);
        } finally {
            bokforBtn.disabled = false;
            bokforBtn.textContent = 'Bokför';
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
                    showBokforError(`Kunde inte ta bort: ${error.message}`);
                }
            }
        }
    });
    
    // ... (rest of the helper functions)
});