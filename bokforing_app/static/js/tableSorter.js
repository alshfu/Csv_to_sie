/**
 * Gör en HTML-tabell sorterbar.
 *
 * Användning:
 * 1. Ge din tabell en klass, t.ex. 'sortable-table'.
 * 2. Ge varje <th>-element som ska vara sorterbart klassen 'sortable'.
 * 3. Lägg till ett data-sort-attribut till varje sorterbar <th>,
 *    t.ex. data-sort="name" eller data-sort="date".
 * 4. Se till att varje <tr> i <tbody> har motsvarande data-attribut,
 *    t.ex. data-name="..." eller data-date="...".
 * 5. Anropa `new TableSorter('sortable-table');`
 */
class TableSorter {
    constructor(tableClass) {
        this.table = document.querySelector(`.${tableClass}`);
        if (!this.table) {
            console.warn(`Sorterbar tabell med klassen '${tableClass}' hittades inte.`);
            return;
        }
        this.tbody = this.table.querySelector('tbody');
        this.headers = this.table.querySelectorAll('thead .sortable');
        this.addEventListeners();
    }

    addEventListeners() {
        this.headers.forEach(header => {
            header.addEventListener('click', () => this.sortColumn(header));
        });
    }

    sortColumn(header) {
        const sortProperty = header.dataset.sort;
        const currentDirection = header.dataset.sortDirection || 'desc';
        const newDirection = currentDirection === 'desc' ? 'asc' : 'desc';

        // Återställ andra headers
        this.headers.forEach(h => {
            h.dataset.sortDirection = '';
            const icon = h.querySelector('i');
            if (icon) {
                icon.className = 'bi bi-arrow-up-down ms-1';
            }
        });

        // Sätt riktning på den klickade headern
        header.dataset.sortDirection = newDirection;
        const icon = header.querySelector('i');
        if (icon) {
            icon.className = newDirection === 'asc' ? 'bi bi-sort-up ms-1' : 'bi bi-sort-down ms-1';
        }


        const rows = Array.from(this.tbody.querySelectorAll('tr'));

        rows.sort((a, b) => {
            let valA = a.dataset[this.toCamelCase(sortProperty)];
            let valB = b.dataset[this.toCamelCase(sortProperty)];

            // Försök konvertera till nummer om det är möjligt
            const numA = parseFloat(valA);
            const numB = parseFloat(valB);

            if (!isNaN(numA) && !isNaN(numB)) {
                valA = numA;
                valB = numB;
            } else if (this.isDate(valA) && this.isDate(valB)) {
                valA = new Date(valA);
                valB = new Date(valB);
            }


            if (valA < valB) {
                return newDirection === 'asc' ? -1 : 1;
            }
            if (valA > valB) {
                return newDirection === 'asc' ? 1 : -1;
            }
            return 0;
        });

        // Rensa och lägg till de sorterade raderna
        this.tbody.innerHTML = '';
        rows.forEach(row => this.tbody.appendChild(row));
    }
    
    toCamelCase(str) {
        return str.replace(/([-_][a-z])/ig, ($1) => {
            return $1.toUpperCase()
                .replace('-', '')
                .replace('_', '');
        });
    }

    isDate(str) {
        // Enkel kontroll om strängen liknar ett datum (YYYY-MM-DD)
        return /^\d{4}-\d{2}-\d{2}$/.test(str);
    }
}
