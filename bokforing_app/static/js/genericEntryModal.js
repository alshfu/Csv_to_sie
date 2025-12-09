class GenericEntryModal {
    constructor(config) {
        this.config = config;
        this.companyId = config.companyId;
        this.kontoplan = config.kontoplan;
        this.fetchUrls = config.fetchUrls;

        // Core modal elements
        this.modal = new bootstrap.Modal(document.getElementById('genericEntryModal'));
        this.form = document.getElementById('genericEntryForm');
        this.entriesContainer = document.getElementById('entries-container');
        this.modalEntryId = document.getElementById('modal-entry-id');
        this.modalEntryType = document.getElementById('modal-entry-type');
        this.modalLabel = document.getElementById('genericEntryModalLabel');
        this.deleteBtn = document.getElementById('delete-entry-btn-modal');
        this.saveBtn = document.getElementById('save-entry-btn');
        this.saveBtnSpinner = this.saveBtn.querySelector('.spinner-border');
        
        // Optional elements - these might not exist on every page
        this.omvandCheckbox = document.getElementById('modal-omvand-skattskyldighet');
        this.invoiceSelectEl = document.getElementById('invoice-select');
        this.attachmentSelectEl = document.getElementById('attachment-select');
        this.underlagList = document.getElementById('underlag-list');

        this.invoiceTomSelect = null;
        this.attachmentTomSelect = null;
        this.availableInvoices = [];
        this.availableAttachments = [];

        this.init();
    }

    async init() {
        // Only fetch underlag if the selectors exist
        if (this.invoiceSelectEl && this.attachmentSelectEl) {
            await this.fetchUnderlag();
            this.initializeUnderlagSelectors();
        }
        this.addEventListeners();
    }

    async fetchUnderlag() {
        try {
            const [invoicesRes, attachmentsRes] = await Promise.all([
                fetch(`/api/company/${this.companyId}/invoices?booked=false`),
                fetch(`/api/company/${this.companyId}/attachments?assigned=false`)
            ]);
            this.availableInvoices = await invoicesRes.json();
            this.availableAttachments = await attachmentsRes.json();
        } catch (error) {
            console.error("Kunde inte ladda underlag:", error);
            showToast("Kunde inte ladda tillgängliga fakturor och bilagor.", "danger");
        }
    }

    initializeUnderlagSelectors() {
        if (!this.invoiceSelectEl || !this.attachmentSelectEl) return;

        if (this.invoiceTomSelect) this.invoiceTomSelect.destroy();
        if (this.attachmentTomSelect) this.attachmentTomSelect.destroy();

        this.invoiceTomSelect = new TomSelect(this.invoiceSelectEl, {
            valueField: 'id',
            labelField: 'display_name',
            searchField: ['display_name'],
            options: this.availableInvoices,
            plugins: ['remove_button'],
            onChange: () => this.updateUnderlagListAndHiddenInput(),
        });

        this.attachmentTomSelect = new TomSelect(this.attachmentSelectEl, {
            valueField: 'id',
            labelField: 'filename',
            searchField: ['filename'],
            options: this.availableAttachments,
            plugins: ['remove_button'],
            onChange: () => this.updateUnderlagListAndHiddenInput(),
        });
    }

    updateUnderlagListAndHiddenInput() {
        if (!this.underlagList) return;
        this.underlagList.innerHTML = '';
        const selectedInvoiceIds = this.invoiceTomSelect.getValue();
        const selectedAttachmentIds = this.attachmentTomSelect.getValue();

        selectedInvoiceIds.forEach(id => {
            const item = this.availableInvoices.find(i => i.id == id);
            if (item) this.underlagList.innerHTML += `<li class="list-group-item">Faktura: ${item.display_name}</li>`;
        });
        selectedAttachmentIds.forEach(id => {
            const item = this.availableAttachments.find(a => a.id == id);
            if (item) this.underlagList.innerHTML += `<li class="list-group-item">Bilaga: <a href="${item.url}" target="_blank">${item.filename}</a></li>`;
        });

        document.getElementById('modal-invoice-ids').value = selectedInvoiceIds.join(',');
        document.getElementById('modal-attachment-ids').value = selectedAttachmentIds.join(',');
    }

    createEntryRow(entry = {}) {
        // This function is now in utils.js
        createEntryRow(this.entriesContainer, this.kontoplan, entry);
    }

    updateTotals() {
        // This function is now in utils.js
        updateTotals(this.entriesContainer);
    }

    async populateModal(entryId, type, prefillData = {}) {
        this.form.reset();
        this.entriesContainer.innerHTML = '';
        this.modalEntryId.value = entryId;
        this.modalEntryType.value = type;

        // Hide all optional sections by default
        document.getElementById('modal-invoice-info')?.style.setProperty('display', 'none', 'important');
        document.getElementById('modal-bank-event-info')?.style.setProperty('display', 'none', 'important');
        document.getElementById('modal-underlag-section')?.style.setProperty('display', 'none', 'important');

        let data;
        if (entryId) {
            this.modalLabel.textContent = `Redigera ${type} ${entryId}`;
            const response = await fetch(this.fetchUrls.get.replace('{id}', entryId));
            data = await response.json();
            this.deleteBtn.style.display = 'block';
        } else {
            this.modalLabel.textContent = `Skapa ny ${type}`;
            data = {
                bokforingsdag: prefillData.fakturadatum || new Date().toISOString().slice(0, 10),
                referens: prefillData.referens || '',
                entries: prefillData.entries || [],
                invoice_ids: prefillData.invoice_ids || [],
                attachment_ids: prefillData.attachment_ids || [],
                omvand_skattskyldighet: prefillData.omvand_skattskyldighet || false
            };
            this.deleteBtn.style.display = 'none';
        }

        document.getElementById('modal-bokforingsdag').value = data.bokforingsdag;
        document.getElementById('modal-referens').value = data.referens;
        if (this.omvandCheckbox) {
            this.omvandCheckbox.checked = data.omvand_skattskyldighet || false;
        }

        this.entriesContainer.innerHTML = '';
        if (data.entries && data.entries.length > 0) {
            data.entries.forEach(entry => this.createEntryRow(entry));
        } else {
            this.generateDefaultEntries();
        }
        this.updateTotals();
        
        const bankEventInfo = document.getElementById('modal-bank-event-info');
        if (data.bank_event && bankEventInfo) {
            document.getElementById('bank-event-date').textContent = data.bank_event.date;
            document.getElementById('bank-event-ref').textContent = data.bank_event.ref;
            document.getElementById('bank-event-amount').textContent = data.bank_event.amount;
            bankEventInfo.style.display = 'block';
        }

        if (this.invoiceTomSelect && this.attachmentTomSelect) {
            document.getElementById('modal-underlag-section').style.display = 'block';
            this.invoiceTomSelect.setValue(data.invoice_ids || []);
            this.attachmentTomSelect.setValue(data.attachment_ids || []);
            this.updateUnderlagListAndHiddenInput();
        }
        
        this.modal.show();
    }

    generateDefaultEntries() {
        this.entriesContainer.innerHTML = '';
        const isOmvand = this.omvandCheckbox ? this.omvandCheckbox.checked : false;
        const brutto = parseFloat(document.getElementById('metadata-total-brutto')?.value) || 0;
        const moms = parseFloat(document.getElementById('metadata-total-moms')?.value) || 0;
        const kostnadskonto = document.getElementById('metadata-suggested-konto')?.value || '5410';

        if (isOmvand) {
            this.createEntryRow({ konto: kostnadskonto, debet: brutto });
            this.createEntryRow({ konto: '2641', debet: moms });
            this.createEntryRow({ konto: '2440', kredit: brutto });
            this.createEntryRow({ konto: '2611', kredit: moms });
        } else {
            this.createEntryRow({ konto: kostnadskonto, debet: brutto - moms });
            if (moms > 0) {
                this.createEntryRow({ konto: '2641', debet: moms });
            }
            this.createEntryRow({ konto: '2440', kredit: brutto });
        }
        this.updateTotals();
    }

    addEventListeners() {
        document.getElementById('add-entry-row').addEventListener('click', () => this.createEntryRow());

        if (this.omvandCheckbox) {
            this.omvandCheckbox.addEventListener('change', () => this.generateDefaultEntries());
        }

        this.entriesContainer.addEventListener('click', e => {
            if (e.target.closest('.remove-entry-row')) {
                e.target.closest('.entry-row').remove();
                this.updateTotals();
            }
        });

        this.entriesContainer.addEventListener('input', e => {
            if (e.target.classList.contains('debet-input') || e.target.classList.contains('kredit-input')) {
                this.updateTotals();
            }
        });

        this.deleteBtn.addEventListener('click', () => this.handleDelete());
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
    }

    async handleDelete() {
        const entryId = this.modalEntryId.value;
        if (!entryId) {
            showToast('Kan inte radera en verifikation som inte sparats.', 'warning');
            return;
        }

        if (!confirm(`Är du säker på att du vill radera verifikation ${entryId}?`)) {
            return;
        }

        try {
            const url = this.fetchUrls.delete.replace('{id}', entryId);
            const response = await fetch(url, { method: 'DELETE' });
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || 'Ett fel inträffade vid radering.');
            }

            this.modal.hide();
            showToast('Verifikationen har raderats!', 'success');
            setTimeout(() => location.reload(), 1500); // Reload to update the list
        } catch (error) {
            showToast(`Kunde inte radera verifikationen: ${error.message}`, 'danger');
        }
    }

    async handleSubmit(e) {
        e.preventDefault();
        
        this.saveBtn.disabled = true;
        this.saveBtnSpinner.classList.remove('d-none');

        const entryId = this.modalEntryId.value;
        const url = entryId ? this.fetchUrls.put.replace('{id}', entryId) : this.fetchUrls.post;
        const method = entryId ? 'PUT' : 'POST';

        const data = {
            bokforingsdag: document.getElementById('modal-bokforingsdag').value,
            referens: document.getElementById('modal-referens').value,
            invoice_ids: document.getElementById('modal-invoice-ids')?.value.split(',').filter(id => id) || [],
            attachment_ids: document.getElementById('modal-attachment-ids')?.value.split(',').filter(id => id) || [],
            entries: []
        };

        this.entriesContainer.querySelectorAll('.entry-row').forEach(row => {
            const konto = row.querySelector('.konto-select').value;
            const debet = parseFloat(row.querySelector('.debet-input').value) || 0;
            const kredit = parseFloat(row.querySelector('.kredit-input').value) || 0;
            if (konto && (debet > 0 || kredit > 0)) {
                data.entries.push({ konto, debet, kredit });
            }
        });

        // Balance check (assuming 'balance' element exists in the modal)
        const balanceElement = document.getElementById('balance');
        if (balanceElement && Math.abs(parseFloat(balanceElement.textContent)) > 0.01) {
            showToast('Fel: Debet och Kredit måste vara i balans.', 'danger');
            this.saveBtn.disabled = false;
            this.saveBtnSpinner.classList.add('d-none');
            return;
        }
        if (data.entries.length < 2) {
            showToast('Fel: Du måste ha minst två bokföringsposter.', 'danger');
            this.saveBtn.disabled = false;
            this.saveBtnSpinner.classList.add('d-none');
            return;
        }

        try {
            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Ett fel inträffade.');

            this.modal.hide();
            showToast('Verifikationen har sparats!', 'success');
            setTimeout(() => location.reload(), 1500); // Reload to update the list
        } catch (error) {
            showToast(`Kunde inte spara verifikationen: ${error.message}`, 'danger');
        } finally {
            this.saveBtn.disabled = false;
            this.saveBtnSpinner.classList.add('d-none');
        }
    }
    
    openModal(entryId = null, type = 'verifikation', prefillData = {}) {
        this.populateModal(entryId, type, prefillData);
    }
}
