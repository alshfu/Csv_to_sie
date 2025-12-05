/**
 * @file mainTable.js
 * @description Hanterar klientsidan-sortering för tabeller.
 * Den letar efter en tabell med klassen .table-hover och gör kolumner med data-sort-index-attributet klickbara för sortering.
 */

document.addEventListener('DOMContentLoaded', function () {
    /**
     * Huvudtabellen på sidan.
     * @type {HTMLTableElement}
     */
    const table = document.querySelector('.table-hover');
    if (!table) {
        return; // Avsluta om ingen tabell finns på sidan.
    }

    /**
     * Alla klickbara kolumnrubriker som kan användas för sortering.
     * @type {NodeListOf<HTMLTableCellElement>}
     */
    const headers = table.querySelectorAll('th[data-sort-index]');
    
    /**
     * Tabellens kropp (tbody) som innehåller raderna som ska sorteras.
     * @type {HTMLElement}
     */
    const tableBody = document.getElementById('transactions-table-body');

    if (tableBody) {
        headers.forEach(header => {
            header.addEventListener('click', () => {
                /**
                 * Index för den kolumn som ska sorteras.
                 * @type {number}
                 */
                const sortIndex = parseInt(header.dataset.sortIndex);
                /**
                 * Datatypen för kolumnen (text, number, date).
                 * @type {string}
                 */
                const sortType = header.dataset.sortType;
                /**
                 * Nuvarande sorteringsriktning ('asc' eller 'desc').
                 * @type {string}
                 */
                const currentDir = header.dataset.sortDir || 'asc';
                /**
                 * Den nya sorteringsriktningen.
                 * @type {string}
                 */
                const newDir = currentDir === 'asc' ? 'desc' : 'asc';

                sortRows(tableBody, sortIndex, sortType, newDir);

                // Återställ och uppdatera UI (sorteringspilar).
                headers.forEach(h => {
                    h.dataset.sortDir = '';
                    h.querySelector('.sort-arrow')?.remove();
                });

                header.dataset.sortDir = newDir;
                const arrow = document.createElement('span');
                arrow.className = 'sort-arrow';
                arrow.innerHTML = newDir === 'asc' ? ' &uarr;' : ' &darr;'; // ↑ eller ↓
                header.appendChild(arrow);
            });
        });
    }
});

/**
 * Sorterar raderna i en tabell baserat på en specifik kolumn.
 * @param {HTMLElement} tbody - Tabellens tbody-element som innehåller raderna.
 * @param {number} colIndex - Index för kolumnen att sortera efter.
 * @param {string} type - Datatypen för värdena i kolumnen ('text', 'number', 'date').
 * @param {string} dir - Sorteringsriktningen ('asc' för stigande, 'desc' för fallande).
 */
function sortRows(tbody, colIndex, type, dir) {
    /**
     * En array av alla rader (TR-element) i tabellkroppen.
     * @type {HTMLTableRowElement[]}
     */
    const rows = Array.from(tbody.querySelectorAll('tr'));
    /**
     * Multiplikator för sorteringsriktning. 1 för stigande, -1 för fallande.
     * @type {number}
     */
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

    // Rensa tabellkroppen och lägg till de sorterade raderna.
    tbody.innerHTML = '';
    sortedRows.forEach(row => {
        tbody.appendChild(row);
    });
}

/**
 * Hämtar och bearbetar värdet från en tabellcell för sortering.
 * @param {HTMLTableRowElement} tr - Raden (TR-element) som cellen tillhör.
 * @param {number} colIndex - Index för cellen (kolumnen) i raden.
 * @param {string} type - Datatypen som värdet ska tolkas som ('text', 'number', 'date').
 * @returns {string|number|Date|null} Det bearbetade värdet redo för jämförelse.
 */
function getCellValue(tr, colIndex, type) {
    const cell = tr.children[colIndex];
    if (!cell) return null;

    const val = cell.innerText.trim();

    switch(type) {
        case 'number':
            // Hanterar svenska nummerformat (mellanslag som tusentalsavgränsare, komma som decimal).
            return parseFloat(val.replace(/\s/g, '').replace(',', '.')) || 0;
        case 'date':
            return new Date(val); // Förutsätter 'YYYY-MM-DD'.
        case 'text':
        default:
            return val.toLowerCase();
    }
}
