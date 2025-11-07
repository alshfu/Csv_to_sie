document.addEventListener('DOMContentLoaded', function() {

    if (typeof KONTOPLAN === 'undefined') {
        console.error("KONTOPLAN är inte laddad.");
        return;
    }

    const kontoOptions = Object.keys(KONTOPLAN).map(key => ({
        value: key,
        text: `${key} - ${KONTOPLAN[key]}`
    }));

    // Accept a DOM element directly for dropdownParent
    const getTomSelectSettings = (parentElement) => ({
        options: kontoOptions,
        searchField: ['text', 'value'],
        create: false,
        placeholder: 'Välj eller sök konto...',
        dropdownParent: parentElement || 'body', // Use the passed element
        render: {
            option: function(item, escape) {
                return `<div><strong>${escape(item.value)}</strong><span class="text-muted ms-2">${escape(item.text.split(' - ')[1])}</span></div>`;
            },
            item: function(item, escape) {
                return `<div>${escape(item.text)}</div>`;
            }
        }
    });

    // This function now expects a DOM element for the parent
    window.initializeKontoAutocomplete = (element, parentElement) => {
        if (element.tomselect) {
            return element.tomselect;
        }
        const settings = getTomSelectSettings(parentElement);
        return new TomSelect(element, settings);
    };

    // This part remains for other modals that might use a selector string approach
    const bokforingModal = document.getElementById('bokforingModal');
    if (bokforingModal) {
        bokforingModal.addEventListener('show.bs.modal', function() {
            const existingInputs = bokforingModal.querySelectorAll('.konto-input:not(.tomselected)');
            existingInputs.forEach(input => {
                if (window.initializeKontoAutocomplete) {
                    // Pass the modal element directly
                    window.initializeKontoAutocomplete(input, bokforingModal);
                }
            });
        });
    }
});
