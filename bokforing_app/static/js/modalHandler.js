document.addEventListener('DOMContentLoaded', function () {
    const bokforingModalEl = document.getElementById('bokforingModal');
    if (!bokforingModalEl) {
        return;
    }

    const bokforingModal = new bootstrap.Modal(bokforingModalEl);
    const entriesContainer = document.getElementById('entries-container');
    const rowTemplate = document.getElementById('entry-row-template');
    const addRowBtn = document.getElementById('add-row-btn');
    const saveBtn = document.getElementById('save-entries-btn');
    const modalAlert = document.getElementById('modal-alert');
    const transactionsTableBody = document.getElementById('transactions-table-body');
    const attachedBilagaList = document.getElementById('bilaga-list');
    
    const batchBookBtn = document.getElementById('batch-book-btn');
    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    const selectedCountSpan = document.getElementById('selected-count');

    let currentTransId = null;
    let currentBankAmount = 0;

    function showModalError(message) {
        console.error("Modal Fel:", message);
        modalAlert.textContent = message;
        modalAlert.style.display = 'block';
        setTimeout(() => { modalAlert.style.display = 'none'; }, 5000);
    }

    async function openModalForTransaction(transId, prefilledEntries = null) {
        const row = document.getElementById(`trans-row-${transId}`);
        if (!row) return;

        currentTransId = transId;
        const cells = row.querySelectorAll('td');
        currentBankAmount = parseFloat(cells[3].textContent);

        document.getElementById('modal-trans-id').value = currentTransId;
        document.getElementById('modal-date').textContent = cells[1].textContent;
        document.getElementById('modal-referens').textContent = cells[2].textContent;
        document.getElementById('modal-amount').textContent = currentBankAmount.toFixed(2);

        modalAlert.style.display = 'none';
        entriesContainer.innerHTML = '';
        attachedBilagaList.innerHTML = '<li>Laddar...</li>';

        bokforingModal.show();

        entriesContainer.innerHTML = '';
        if (prefilledEntries) {
            prefilledEntries.forEach(entry => createEntryRow(entry.konto, entry.debet, entry.kredit));
        } else {
            try {
                const response = await fetch(`/api/entries/${currentTransId}`);
                if (!response.ok) throw new Error('Kunde inte ladda bokföringsrader.');
                const entries = await response.json();
                entries.forEach(entry => createEntryRow(entry.konto, entry.debet, entry.kredit));
            } catch (error) {
                showModalError(error.message);
            }
        }
        lockBankRow();
        calculateTotals();
    }

    transactionsTableBody.addEventListener('click', async function(e) {
        const target = e.target;
        const row = target.closest('tr');
        if (!row) return;
        
        const transId = row.querySelector('.transaction-checkbox')?.dataset.transId;
        if (!transId) return;

        if (target.closest('.ask-ai-btn')) {
            const aiButton = target.closest('.ask-ai-btn');
aiButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            aiButton.disabled = true;
            try {
                const response = await fetch(`/api/transaction/${transId}/ask_gemini`, { method: 'POST' });
                const data = await response.json();
                console.log('Svar från Gemini:', data);
                if (!response.ok) throw new Error(data.error || 'Okänt AI-fel');
                await openModalForTransaction(transId, data.entries);
            } catch (error) {
                showModalError(`AI-fel: ${error.message}`);
            } finally {
                aiButton.innerHTML = '<i class="bi bi-robot"></i> AI';
                aiButton.disabled = false;
            }
        } else if (target.classList.contains('open-modal-cell')) {
            await openModalForTransaction(transId);
        } else if (target.classList.contains('transaction-checkbox')) {
            updateSelectedCount();
        }
    });

    function updateSelectedCount() {
        const selectedCheckboxes = transactionsTableBody.querySelectorAll('.transaction-checkbox:checked');
        const count = selectedCheckboxes.length;
        selectedCountSpan.textContent = count;
        batchBookBtn.disabled = count === 0;
    }

    selectAllCheckbox.addEventListener('change', function() {
        const checkboxes = transactionsTableBody.querySelectorAll('.transaction-checkbox');
        checkboxes.forEach(checkbox => {
            checkbox.checked = selectAllCheckbox.checked;
        });
        updateSelectedCount();
    });

    batchBookBtn.addEventListener('click', async function() {
        const selectedCheckboxes = transactionsTableBody.querySelectorAll('.transaction-checkbox:checked');
        const transactionIds = Array.from(selectedCheckboxes).map(cb => cb.dataset.transId);

        if (transactionIds.length === 0) return;

        const originalButtonText = batchBookBtn.innerHTML;
        batchBookBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Bokför...';
        batchBookBtn.disabled = true;

        try {
            const response = await fetch('/api/batch_book_with_ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ transaction_ids: transactionIds })
            });
            const result = await response.json();

            if (result.success_ids) {
                result.success_ids.forEach(id => {
                    const row = document.getElementById(`trans-row-${id}`);
                    if (row) {
                        row.style.transition = 'opacity 0.5s ease';
                        row.style.opacity = '0';
                        setTimeout(() => row.remove(), 500);
                    }
                });
            }
            if (result.errors && result.errors.length > 0) {
                console.error('Följande transaktioner kunde inte bokföras:', result.errors);
                alert(`Kunde inte bokföra ${result.errors.length} av ${transactionIds.length} transaktioner. Se konsolen för detaljer.`);
            }
        } catch (error) {
            console.error('Fel vid massbokföring:', error);
            alert('Ett allvarligt fel inträffade vid massbokföring.');
        } finally {
            batchBookBtn.innerHTML = originalButtonText;
            updateSelectedCount();
        }
    });
    
    function createEntryRow(konto, debet, kredit) {
        const newRow = rowTemplate.content.cloneNode(true).firstElementChild;
        const kontoInput = newRow.querySelector('.konto-input');
        newRow.querySelector('.debet-input').value = debet || '';
        newRow.querySelector('.kredit-input').value = kredit || '';
        newRow.querySelectorAll('input[type="number"]').forEach(input => input.addEventListener('input', calculateTotals));
        entriesContainer.appendChild(newRow);

        if (window.initializeKontoAutocomplete) {
            const tomselect = window.initializeKontoAutocomplete(kontoInput);
            if (tomselect) {
                tomselect.setValue(konto);
                tomselect.on('change', calculateTotals);
                if (konto === '1930') tomselect.lock();
            }
        }
    }
    
    function lockBankRow() {
        entriesContainer.querySelectorAll('tr').forEach(row => {
            const kontoInput = row.querySelector('.konto-input');
            if (kontoInput.value === '1930') {
                if(kontoInput.tomselect) kontoInput.tomselect.lock();
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
        diffEl.className = Math.abs(diff) < 0.01 && totalDebet > 0 ? 'text-success' : 'text-danger';
        return Math.abs(diff) < 0.01 && totalDebet > 0;
    }

    saveBtn.addEventListener('click', async function() {
        const entries = Array.from(entriesContainer.querySelectorAll('tr')).map(row => {
            const kontoInput = row.querySelector('.konto-input');
            const kontoValue = kontoInput.tomselect ? kontoInput.tomselect.getValue() : kontoInput.value;
            return {
                konto: kontoValue,
                debet: row.querySelector('.debet-input').value || 0,
                kredit: row.querySelector('.kredit-input').value || 0
            };
        }).filter(e => e.konto);

        if (!validateBalance()) {
            showModalError('Obalans! Debet och Kredit måste vara lika.');
            return;
        }

        try {
            const response = await fetch(`/api/save_entries/${currentTransId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entries: entries })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Okänt serverfel');

            bokforingModal.hide();
            const processedRow = document.getElementById(`trans-row-${currentTransId}`);
            if (processedRow) {
                processedRow.style.transition = 'opacity 0.5s ease';
                processedRow.style.opacity = '0';
                setTimeout(() => processedRow.remove(), 500);
            }
        } catch (error) {
            showModalError(error.message);
        }
    });

    addRowBtn.addEventListener('click', () => createEntryRow('', '', ''));
});
