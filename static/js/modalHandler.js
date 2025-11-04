document.addEventListener('DOMContentLoaded', function () {
    const bokforingModal = document.getElementById('bokforingModal');
    if (!bokforingModal) {
        return; // Vi är inte på en sida med ett modal-fönster, avsluta.
    }

    // Element som finns på BÅDA sidorna
    const entriesContainer = document.getElementById('entries-container');
    const rowTemplate = document.getElementById('entry-row-template');
    const addRowBtn = document.getElementById('add-row-btn');
    const saveBtn = document.getElementById('save-entries-btn');
    const modalAlert = document.getElementById('modal-alert');
    const momsBtnGroup = document.getElementById('moms-btn-group');
    const attachedBilagaList = document.getElementById('bilaga-list');

    // Element som BARA finns på transactions.html (Inkorgen)
    const linkableBilagaList = document.getElementById('link-bilaga-list');

    let currentTransId = null;
    let activeRowForMoms = null;
    let currentBankAmount = 0;

    // 1. Händelse: Modal-fönstret "Bokföring" öppnas
    bokforingModal.addEventListener('show.bs.modal', async function (event) {
        const triggerElement = event.relatedTarget;
        currentTransId = triggerElement.getAttribute('data-trans-id');
        currentBankAmount = parseFloat(triggerElement.getAttribute('data-amount')) || 0;

        document.getElementById('modal-trans-id').value = currentTransId;
        document.getElementById('modal-date').textContent = triggerElement.getAttribute('data-date');
        document.getElementById('modal-referens').textContent = triggerElement.getAttribute('data-referens');
        document.getElementById('modal-amount').textContent = currentBankAmount.toFixed(2);

        // Återställ
        modalAlert.style.display = 'none';
        entriesContainer.innerHTML = '';
        disableMomsButtons();

        // Kontrollera om listorna finns innan vi återställer dem
        if (attachedBilagaList) {
            attachedBilagaList.innerHTML = '<li>Laddar...</li>';
        }
        if (linkableBilagaList) {
            linkableBilagaList.innerHTML = '<li>Laddar...</li>';
        }

        //
        // ===============================================================
        //  HÄR ÄR FIXEN (Del 1):
        //  Hämta förhandsgranskaren lokalt och KONTROLLERA om den finns.
        // ===============================================================
        //
        const bilagaPreview = document.getElementById('bilaga-preview');
        const bilagaPreviewPlaceholder = document.getElementById('bilaga-preview-placeholder');

        if (bilagaPreview && bilagaPreviewPlaceholder) {
            bilagaPreview.setAttribute('src', 'about:blank'); // <- Detta var rad 43
            bilagaPreview.style.display = 'none';
            bilagaPreviewPlaceholder.style.display = 'flex';
        }

        // Ladda data
        try {
            const [entriesResponse, bilagorResponse] = await Promise.all([
                fetch(`/get_entries/${currentTransId}`),
                fetch(`/get_bilagor/${currentTransId}`)
            ]);

            if (!entriesResponse.ok) throw new Error('Kunde inte ladda bokföringsrader.');
            if (!bilagorResponse.ok) throw new Error('Kunde inte ladda bilagor.');

            const entries = await entriesResponse.json();
            entriesContainer.innerHTML = '';
            entries.forEach(entry => createEntryRow(entry.konto, entry.debet, entry.kredit));
            lockBankRow();
            calculateTotals();

            const bilagor = await bilagorResponse.json();
            updateAttachedBilagaList(bilagor);

            updateLinkableBilagaList(); // Denna funktion har en egen kontroll

        } catch (error) {
            showModalError(error.message);
        }
    });

    // 2. Händelse: Koppla Bilaga från Inkorg (Körs BARA om listan finns)
    if (linkableBilagaList) {
        linkableBilagaList.addEventListener('click', async function(e) {
            if (!e.target.classList.contains('link-bilaga-btn')) return;

            const bilagaId = e.target.dataset.bilagaId;
            const filename = e.target.dataset.filename;
            const url = e.target.dataset.url;

            // --- 1. Auto-kontering ---
            const editBtn = document.querySelector(`.edit-metadata-btn[data-bilaga-id="${bilagaId}"]`);
            if (editBtn) {
                const netto = parseFloat(editBtn.dataset.nettoAmount) || 0;
                const moms = parseFloat(editBtn.dataset.momsAmount) || 0;
                const kontoToUse = editBtn.dataset.suggestedKonto || null;

                const isDebet = currentBankAmount < 0;
                const isKredit = currentBankAmount > 0;

                // Rensa standardrader (1798/1799)
                entriesContainer.querySelectorAll('tr').forEach(row => {
                    const konto = row.querySelector('.konto-input').value;
                    if (konto === '1798' || konto === '1799') {
                        const tomselectInstance = row.querySelector('.konto-input').tomselect;
                        if(tomselectInstance) tomselectInstance.destroy();
                        row.remove();
                    }
                });

                // Skapa nya, korrekta rader
                if (isDebet && (netto > 0 || moms > 0)) {
                    createEntryRow(kontoToUse || '1799', netto.toFixed(2), 0);
                    if (moms > 0) createEntryRow('2641', moms.toFixed(2), 0);
                } else if (isKredit && (netto > 0 || moms > 0)) {
                    createEntryRow(kontoToUse || '1798', 0, netto.toFixed(2));
                    if (moms > 0) createEntryRow('2611', 0, moms.toFixed(2));
                } else {
                     const defaultKonto = isDebet ? '1799' : '1798';
                     const totalBankAmount = Math.abs(currentBankAmount);
                     createEntryRow(
                        kontoToUse || defaultKonto,
                        isDebet ? totalBankAmount.toFixed(2) : 0,
                        isKredit ? totalBankAmount.toFixed(2) : 0
                    );
                }
                calculateTotals();
            }
            // --- Slut Auto-kontering ---

            // 2. Koppla bilagan
            try {
                const response = await fetch(`/link_bilaga`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        bilaga_id: bilagaId,
                        transaction_id: currentTransId
                    })
                });
                if (!response.ok) throw new Error('Kunde inte koppla.');

                e.target.closest('li').remove();
                document.getElementById(`bilaga-card-${bilagaId}`)?.remove();
                appendBilagaToList(filename, url, bilagaId);

            } catch (error) {
                showModalError(error.message);
            }
        });
    }

    // 3. Händelse: Lossa Bilaga / Förhandsgranska
    if (attachedBilagaList) {
        attachedBilagaList.addEventListener('click', async function(e) {
            // Förhandsgranskning
            if (e.target.classList.contains('bilaga-preview-link')) {
                e.preventDefault();

                //
                // ===============================================================
                //  HÄR ÄR FIXEN (Del 2):
                //  Hämta och kontrollera elementen IGEN här inne.
                // ===============================================================
                //
                const bilagaPreview = document.getElementById('bilaga-preview');
                const bilagaPreviewPlaceholder = document.getElementById('bilaga-preview-placeholder');

                if (bilagaPreview && bilagaPreviewPlaceholder) {
                    const url = e.target.dataset.url;
                    bilagaPreview.setAttribute('src', url);
                    bilagaPreview.style.display = 'block';
                    bilagaPreviewPlaceholder.style.display = 'none';
                    attachedBilagaList.querySelectorAll('a').forEach(a => a.classList.remove('fw-bold'));
                    e.target.classList.add('fw-bold');
                }
            }

            // Lossa (TODO)
            if (e.target.classList.contains('unlink-bilaga-btn')) {
                alert('Funktionen "Koppla från" är inte implementerad än.');
            }
        });
    }

    // 4. Knappen: Lägg till rad
    addRowBtn.addEventListener('click', () => createEntryRow('', '', ''));

    // 5. Knappen: Spara
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
            if (modalInstance) { modalInstance.hide(); }

            const processedRow = document.getElementById(`trans-row-${currentTransId}`);
            if (processedRow) {
                // Kolla om vi är på Bokföring-sidan (där inkorgen finns)
                if (document.getElementById('multi-bilaga-form')) {
                    // Vi är på 'transactions.html', ta bort raden
                    processedRow.style.transition = 'opacity 0.5s ease';
                    processedRow.style.opacity = '0';
                    setTimeout(() => { processedRow.remove(); }, 500);
                } else {
                    // Vi är på 'verifikationer.html', uppdatera status
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

    // 6. Knappar: Moms
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

    // 7. Händelse: Klick i konteringstabellen
    entriesContainer.addEventListener('click', function(e) {
        if (e.target.classList.contains('remove-row-btn')) {
             const row = e.target.closest('tr');
             const tomselectInstance = row.querySelector('.konto-input').tomselect;
             if(tomselectInstance) {
                tomselectInstance.destroy();
             }
             row.remove();
             calculateTotals();
             return;
        }
        if (e.target.tagName === 'INPUT' || e.target.classList.contains('ts-control')) {
            const row = e.target.closest('tr');
            if (!row) return;
            const kontoInput = row.querySelector('.konto-input');
            const kontoVal = kontoInput ? kontoInput.value : '';

            if (e.target.classList.contains('debet-input') || e.target.classList.contains('kredit-input')) {
                if (kontoVal !== '1930') {
                    activeRowForMoms = row;
                    enableMomsButtons();
                } else {
                    activeRowForMoms = null;
                    disableMomsButtons();
                }
            }
            else if (e.target.classList.contains('konto-input') || e.target.classList.contains('ts-control')) {
                activeRowForMoms = null;
                disableMomsButtons();
            }
        }
    });

    // --- Hjälpfunktioner ---

    function createEntryRow(konto, debet, kredit) {
        const newRow = rowTemplate.content.cloneNode(true).firstElementChild;
        const kontoInput = newRow.querySelector('.konto-input');

        kontoInput.value = konto;
        newRow.querySelector('.debet-input').value = debet || '';
        newRow.querySelector('.kredit-input').value = kredit || '';

        newRow.querySelectorAll('input[type="number"]').forEach(input => {
            input.addEventListener('input', calculateTotals);
        });

        entriesContainer.appendChild(newRow);

        if (window.initializeKontoAutocomplete) {
            setTimeout(() => {
                // Skicka med modal-fönstrets ID
                const tomselect = window.initializeKontoAutocomplete(kontoInput, '#bokforingModal');
                if (tomselect) {
                    tomselect.on('change', calculateTotals);
                    if (konto === '1930') {
                        tomselect.lock();
                    }
                }
            }, 0);
        } else {
            console.error("initializeKontoAutocomplete is not defined.");
        }
    }

    function updateAttachedBilagaList(bilagor) {
        if (!attachedBilagaList) return; // Kontrollera om elementet finns
        attachedBilagaList.innerHTML = '';
        if (bilagor.length === 0) {
            attachedBilagaList.innerHTML = '<li class="list-group-item text-muted" id="no-attached-bilaga-item"><i>Inga bilagor kopplade.</i></li>';
        } else {
            bilagor.forEach(b => {
                const fileUrl = getStaticUrl(b.url);
                appendBilagaToList(b.filename, fileUrl, b.id);
            });
        }
    }

    function appendBilagaToList(filename, url, id) {
        if (!attachedBilagaList) return; // Kontrollera om elementet finns
        document.getElementById('no-attached-bilaga-item')?.remove();
        const li = document.createElement('li');
        li.className = 'list-group-item d-flex justify-content-between align-items-center';
        li.setAttribute('id', `attached-bilaga-item-${id}`);
        li.innerHTML = `
            <a href="#" class="bilaga-preview-link" data-url="${url}">${filename}</a>
            <button type="button" class="btn btn-warning btn-sm unlink-bilaga-btn" data-bilaga-id="${id}">Koppla från</button>
        `;
        attachedBilagaList.appendChild(li);
    }

    function updateLinkableBilagaList() {
        if (!linkableBilagaList) return; // Kontrollera om elementet finns

        linkableBilagaList.innerHTML = '';
        const unassignedCards = document.querySelectorAll('#unassigned-bilagor-list .card');

        if (unassignedCards.length === 0) {
            linkableBilagaList.innerHTML = '<li class="list-group-item text-muted" id="no-bilagor-in-inbox"><i>Inkorgen är tom.</i></li>';
            return;
        }

        unassignedCards.forEach(card => {
            const bilagaId = card.id.replace('bilaga-card-', '');
            const link = card.querySelector('a');
            const editBtn = card.querySelector('.edit-metadata-btn');
            if (!link || !editBtn) return;

            const filename = link.textContent.trim();
            const url = link.dataset.url;

            const total = editBtn.dataset.bruttoAmount;
            const kontoNum = editBtn.dataset.suggestedKonto;
            const typ = KONTOPLAN[kontoNum] || '';

            let displayText = filename;
            if (typ && total) {
                displayText = `${typ} - ${total} SEK`;
            } else if (total) {
                displayText = `${filename} - ${total} SEK`;
            } else if (typ) {
                displayText = `${typ} - (Okänt belopp)`;
            }

            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            li.innerHTML = `
                <span>${displayText}</span>
                <button type="button" class="btn btn-success btn-sm link-bilaga-btn" 
                        data-bilaga-id="${bilagaId}" 
                        data-filename="${filename}" 
                        data-url="${url}">
                    Koppla
                </button>
            `;
            linkableBilagaList.appendChild(li);
        });
    }

    function getStaticUrl(urlPath) {
        return urlPath;
    }

    function lockBankRow() {
        entriesContainer.querySelectorAll('tr').forEach(row => {
            const kontoInput = row.querySelector('.konto-input');
            if (kontoInput.value === '1930') {
                if(kontoInput.tomselect) {
                    kontoInput.tomselect.lock();
                } else {
                    kontoInput.readOnly = true;
                }
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

        if (Math.abs(diff) < 0.01 && (totalDebet > 0 || totalKredit > 0) ) {
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
        if (isDebet) { // Ingående moms (Köp)
            if (rate === 25) return '2641';
            if (rate === 12) return '2642';
            if (rate === 6) return '2643';
        } else { // Utgående moms (Sälj)
            if (rate === 25) return '2611';
            if (rate === 12) return '2612';
            if (rate === 6) return '2613';
        }
        return '2641'; // Standard
    }

    function findKontoByValue(valueToFind) {
        if (!valueToFind || typeof KONTOPLAN === 'undefined') return null;
        const lowerValue = valueToFind.toLowerCase();
        for (const key in KONTOPLAN) {
            if (KONTOPLAN[key].toLowerCase() === lowerValue) {
                return key;
            }
        }
        return null;
    }

    function findKontoByKey(keyToFind) {
         if (!keyToFind || typeof ASSOCIATION_MAP === 'undefined') return null;
         const lowerKey = keyToFind.toLowerCase();
         if (ASSOCIATION_MAP[lowerKey]) {
            return ASSOCIATION_MAP[lowerKey];
         }
         return null;
    }
});