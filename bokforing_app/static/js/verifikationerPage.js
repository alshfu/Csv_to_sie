document.addEventListener('DOMContentLoaded', function() {
    const accordion = document.getElementById('verifikationerAccordion');
    if (!accordion) return;

    const rowTemplate = document.getElementById('entry-row-template');

    function calculateTotals(editor) {
        const container = editor.querySelector('.entries-container');
        let totalDebet = 0;
        let totalKredit = 0;

        container.querySelectorAll('tr').forEach(row => {
            totalDebet += parseFloat(row.querySelector('.debet-input').value || 0);
            totalKredit += parseFloat(row.querySelector('.kredit-input').value || 0);
        });

        editor.querySelector('.total-debet').textContent = totalDebet.toFixed(2);
        editor.querySelector('.total-kredit').textContent = totalKredit.toFixed(2);

        const diff = totalDebet - totalKredit;
        const diffEl = editor.querySelector('.total-diff');
        diffEl.textContent = diff.toFixed(2);
        diffEl.className = Math.abs(diff) < 0.01 && totalDebet > 0 ? 'total-diff text-success' : 'total-diff text-danger';
        
        return Math.abs(diff) < 0.01 && totalDebet > 0;
    }

    function initializeTomSelectInEditor(editor) {
        editor.querySelectorAll('.konto-input').forEach(input => {
            if (input.classList.contains('ts-hidden-accessible')) return;

            const currentValue = input.value;
            if (window.initializeKontoAutocomplete) {
                const tomselect = window.initializeKontoAutocomplete(input);
                if (tomselect) {
                    tomselect.setValue(currentValue, true); // 'true' för att inte trigga 'change'-event
                }
            }
        });
    }

    // Händelselyssnare för när ett dragspel är helt öppet
    accordion.addEventListener('shown.bs.collapse', function(event) {
        const editor = event.target.querySelector('.verifikation-editor');
        if (editor) {
            initializeTomSelectInEditor(editor);
        }
    });

    // Initiera de som redan är öppna vid sidladdning
    accordion.querySelectorAll('.accordion-collapse.show').forEach(openCollapse => {
        const editor = openCollapse.querySelector('.verifikation-editor');
        if (editor) {
            initializeTomSelectInEditor(editor);
        }
    });
    
    // Beräkna totaler för alla editorer vid start
    accordion.querySelectorAll('.verifikation-editor').forEach(calculateTotals);

    accordion.addEventListener('click', async function(e) {
        const editor = e.target.closest('.verifikation-editor');
        if (!editor) return;

        const transId = editor.dataset.transId;

        if (e.target.classList.contains('add-row-btn')) {
            const newRow = rowTemplate.content.cloneNode(true);
            const newKontoInput = newRow.querySelector('.konto-input');
            editor.querySelector('.entries-container').appendChild(newRow);
            if (window.initializeKontoAutocomplete) {
                window.initializeKontoAutocomplete(newKontoInput);
            }
        }

        if (e.target.classList.contains('remove-row-btn')) {
            const row = e.target.closest('tr');
            row.querySelector('.konto-input').tomselect?.destroy();
            row.remove();
            calculateTotals(editor);
        }

        if (e.target.classList.contains('save-ver-btn')) {
            if (!calculateTotals(editor)) {
                alert("Obalans! Kan inte spara.");
                return;
            }

            const entries = Array.from(editor.querySelectorAll('.entries-container tr')).map(row => ({
                konto: row.querySelector('.konto-input').value,
                debet: row.querySelector('.debet-input').value || 0,
                kredit: row.querySelector('.kredit-input').value || 0
            }));

            try {
                const response = await fetch(`/api/verifikation/${transId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ entries: entries })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || 'Okänt serverfel');

                const feedback = editor.querySelector('.save-feedback');
                feedback.style.display = 'block';
                setTimeout(() => { feedback.style.display = 'none'; }, 2000);

            } catch (error) {
                alert(`Fel: ${error.message}`);
            }
        }

        if (e.target.classList.contains('delete-ver-btn')) {
            if (confirm(`Är du säker på att du vill radera verifikation #${transId}?`)) {
                try {
                    const response = await fetch(`/api/verifikation/${transId}`, {
                        method: 'DELETE'
                    });
                    if (!response.ok) throw new Error((await response.json()).error);
                    
                    document.getElementById(`ver-item-${transId}`).remove();

                } catch (error) {
                    alert(`Fel: ${error.message}`);
                }
            }
        }
    });

    accordion.addEventListener('input', function(e) {
        if (e.target.classList.contains('debet-input') || e.target.classList.contains('kredit-input')) {
            const editor = e.target.closest('.verifikation-editor');
            if (editor) calculateTotals(editor);
        }
    });
});
