document.addEventListener('DOMContentLoaded', function() {

    // Убедимся, что KONTOPLAN существует (теперь он точно должен быть)
    if (typeof KONTOPLAN === 'undefined') {
        console.error("KONTOPLAN не найден. Убедитесь, что он определен в HTML.");
        return;
    }

    // 1. Форматируем KONTOPLAN для Tom-Select
    // (Из {'1613': 'Lön'} в [{value: '1613', text: '1613 - Lön'}])
    const kontoOptions = Object.keys(KONTOPLAN).map(key => {
        return {
            value: key,
            text: `${key} - ${KONTOPLAN[key]}`
        };
    });

    // 2. Создаем общие настройки Tom-Select
    const tomSelectSettings = {
        options: kontoOptions,
        searchField: ['text', 'value'], // Искать по номеру и по имени
        create: false, // Не разрешаем создавать новые счета
        placeholder: 'Välj eller sök konto...',
        // Важно: Tom-Select должен работать внутри Bootstrap Modal
        dropdownParent: 'body',
        render: {
            // Улучшаем рендеринг, чтобы в списке было видно и номер, и имя
            option: function(item, escape) {
                return `<div>
                            <strong>${escape(item.value)}</strong>
                            <span class="text-muted ms-2">${escape(item.text.split(' - ')[1])}</span>
                        </div>`;
            },
            item: function(item, escape) {
                // Как будет выглядеть выбранный элемент
                return `<div>${escape(item.text)}</div>`;
            }
        }
    };

    // 3. Создаем глобальную функцию-инициализатор
    // Мы вешаем ее на 'window', чтобы modalHandler.js мог ее вызвать
    window.initializeKontoAutocomplete = (element) => {
        if (element.tomselect) {
            // Уже инициализирован, ничего не делаем
            return;
        } else {
            // Создаем новый
            new TomSelect(element, tomSelectSettings);
        }
    };

    // 4. Находим модальное окно и слушаем его открытие
    const bokforingModal = document.getElementById('bokforingModal');
    if (bokforingModal) {
        bokforingModal.addEventListener('show.bs.modal', function() {
            // Находим ВСЕ .konto-input, которые УЖЕ существуют (загружены с сервера)
            // и инициализируем их
            const existingInputs = bokforingModal.querySelectorAll('.konto-input:not(.tomselected)');
            existingInputs.forEach(input => {
                if (window.initializeKontoAutocomplete) {
                    window.initializeKontoAutocomplete(input);
                }
            });
        });
    }

}); // <-- Вот закрывающая скобка 'DOMContentLoaded'