document.addEventListener('DOMContentLoaded', function() {

    if (typeof KONTOPLAN === 'undefined') {
        console.error("KONTOPLAN är inte laddad.");
        return;
    }

    // 1. Formatera KONTOPLAN
    const kontoOptions = Object.keys(KONTOPLAN).map(key => {
        return {
            value: key,
            text: `${key} - ${KONTOPLAN[key]}`
        };
    });

    // 2. Skapa en *mall* för inställningar
    const getTomSelectSettings = (parentModalId) => {
        return {
            options: kontoOptions,
            searchField: ['text', 'value'],
            create: false,
            placeholder: 'Välj eller sök konto...',
            
            //
            // ===============================================================
            //  HÄR ÄR FIXEN (Del 2): Dynamisk förälder
            // ===============================================================
            //
            dropdownParent: parentModalId ? document.querySelector(parentModalId) : 'body',
            
            render: {
                option: function(item, escape) {
                    return `<div>
                                <strong>${escape(item.value)}</strong>
                                <span class="text-muted ms-2">${escape(item.text.split(' - ')[1])}</span>
                            </div>`;
                },
                item: function(item, escape) {
                    return `<div>${escape(item.text)}</div>`;
                }
            }
        };
    };

    // 3. Skapa global funktion som tar emot FÖRÄLDERN
    window.initializeKontoAutocomplete = (element, parentModalId) => {
        if (element.tomselect) {
            return; // Redan initierad
        }
        
        const settings = getTomSelectSettings(parentModalId);
        new TomSelect(element, settings);
    };

    // 4. Initiera för huvud-modalen (Bokföring)
    const bokforingModal = document.getElementById('bokforingModal');
    if (bokforingModal) {
        bokforingModal.addEventListener('show.bs.modal', function() {
            const existingInputs = bokforingModal.querySelectorAll('.konto-input:not(.tomselected)');
            existingInputs.forEach(input => {
                if (window.initializeKontoAutocomplete) {
                    // Skicka med ID:t för modalen
                    window.initializeKontoAutocomplete(input, '#bokforingModal');
                }
            });
        });
    }
});