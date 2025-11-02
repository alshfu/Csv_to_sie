document.addEventListener('DOMContentLoaded', function () {
    const table = document.querySelector('.table-hover');
    if (!table) {
        return; // Выходим, если на странице нет таблицы
    }

    const headers = table.querySelectorAll('th[data-sort-index]');
    const tableBody = document.getElementById('transactions-table-body');

    if (tableBody) {
        headers.forEach(header => {
            header.addEventListener('click', () => {
                const sortIndex = parseInt(header.dataset.sortIndex);
                const sortType = header.dataset.sortType;
                const currentDir = header.dataset.sortDir || 'asc';
                const newDir = currentDir === 'asc' ? 'desc' : 'asc';

                sortRows(tableBody, sortIndex, sortType, newDir);

                // Обновляем UI (стрелочки)
                headers.forEach(h => {
                    h.dataset.sortDir = '';
                    h.querySelector('.sort-arrow')?.remove();
                });

                header.dataset.sortDir = newDir;
                const arrow = document.createElement('span');
                arrow.className = 'sort-arrow';
                arrow.innerHTML = newDir === 'asc' ? ' &uarr;' : ' &darr;'; // ↑ или ↓
                header.appendChild(arrow);
            });
        });
    }
});

/**
 * Сортирует строки таблицы
 * @param {HTMLElement} tbody - Тело таблицы (tbody#transactions-table-body)
 * @param {number} colIndex - Индекс колонки для сортировки
 * @param {string} type - Тип данных ('text', 'number', 'date')
 * @param {string} dir - Направление ('asc' or 'desc')
 */
function sortRows(tbody, colIndex, type, dir) {
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const sortDir = dir === 'asc' ? 1 : -1;

    const sortedRows = rows.sort((a, b) => {
        const valA = getCellValue(a, colIndex, type);
        const valB = getCellValue(b, colIndex, type);

        if (valA < valB) {
            return -1 * sortDir;
        }
        if (valA > valB) {
            return 1 * sortDir;
        }
        return 0;
    });

    tbody.innerHTML = '';
    sortedRows.forEach(row => {
        tbody.appendChild(row);
    });
}

/**
 * Получает и парсит значение ячейки для сортировки
 */
function getCellValue(tr, colIndex, type) {
    const cell = tr.children[colIndex];
    if (!cell) return null;

    const val = cell.innerText.trim();

    switch(type) {
        case 'number':
            return parseFloat(val.replace(/\s/g, '').replace(',', '.')) || 0;
        case 'date':
            return new Date(val); // '2025-11-02'
        case 'text':
        default:
            return val.toLowerCase();
    }
}