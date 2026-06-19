/** 资产配置报告 PPT 一键导出 */

const AllocationReportExport = {
  chapters: [],
  _bound: false,

  async loadChapters() {
    if (this.chapters.length) return this.chapters;
    const res = await apiGet('/api/allocation/report_chapters');
    this.chapters = res.data.chapters || [];
    return this.chapters;
  },

  renderChapterList() {
    const listEl = document.getElementById('reportChapterList');
    if (!listEl) return;
    listEl.innerHTML = this.chapters.map((ch) => `
      <label class="report-chapter-item">
        <input type="checkbox" name="reportChapter" value="${ch.id}" checked>
        <span class="report-chapter-badge">${ch.id}</span>
        <span class="report-chapter-title">${ch.title}</span>
      </label>
    `).join('');
  },

  getSelectedChapterIds() {
    return [...document.querySelectorAll('#reportChapterList input[name="reportChapter"]:checked')]
      .map((el) => el.value);
  },

  setAllChecked(checked) {
    document.querySelectorAll('#reportChapterList input[name="reportChapter"]')
      .forEach((el) => { el.checked = checked; });
  },

  async openModal() {
    const modal = document.getElementById('reportExportModal');
    if (!modal) return;
    try {
      await this.loadChapters();
      this.renderChapterList();
      modal.classList.add('open');
    } catch (e) {
      showToast('加载章节失败: ' + e.message);
    }
  },

  closeModal() {
    const modal = document.getElementById('reportExportModal');
    if (modal) modal.classList.remove('open');
  },

  customerDisplayName() {
    if (typeof overviewData !== 'undefined' && overviewData?.customer_name) {
      return overviewData.customer_name;
    }
    const cid = typeof getSelectedCustomerId === 'function' ? getSelectedCustomerId() : '';
    const hit = (typeof CUSTOMERS !== 'undefined' ? CUSTOMERS : [])
      .find((c) => c.id === cid);
    return hit?.displayName || hit?.name || cid || '客户';
  },

  async exportPpt() {
    const chapters = this.getSelectedChapterIds();
    if (!chapters.length) {
      showToast('请至少选择一个章节');
      return;
    }
    const cid = typeof getSelectedCustomerId === 'function' ? getSelectedCustomerId() : '';
    if (!cid) {
      showToast('请先选择客户');
      return;
    }

    const confirmBtn = document.getElementById('reportExportConfirm');
    if (confirmBtn) confirmBtn.disabled = true;
    showToast('正在生成报告…');

    try {
      const res = await fetch('/api/allocation/export_report_ppt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: cid,
          chapters,
        }),
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const err = await res.json();
          detail = err.detail || detail;
        } catch (_) { /* ignore */ }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const name = this.customerDisplayName();
      const filename = `资产配置报告-${name}.pptx`;

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      this.closeModal();
      showToast('报告已导出');
    } catch (e) {
      showToast('导出失败: ' + e.message);
    } finally {
      if (confirmBtn) confirmBtn.disabled = false;
    }
  },

  bind() {
    if (this._bound) return;
    this._bound = true;

    const btn = document.getElementById('btnExportReport');
    if (btn) {
      btn.onclick = () => this.openModal();
    }

    const cancelBtn = document.getElementById('reportExportCancel');
    const confirmBtn = document.getElementById('reportExportConfirm');
    const selectAllBtn = document.getElementById('reportExportSelectAll');
    const clearAllBtn = document.getElementById('reportExportClearAll');
    const modal = document.getElementById('reportExportModal');

    if (cancelBtn) cancelBtn.onclick = () => this.closeModal();
    if (confirmBtn) confirmBtn.onclick = () => this.exportPpt();
    if (selectAllBtn) selectAllBtn.onclick = () => this.setAllChecked(true);
    if (clearAllBtn) clearAllBtn.onclick = () => this.setAllChecked(false);
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) this.closeModal();
      });
    }
  },

  setVisible(visible) {
    const btn = document.getElementById('btnExportReport');
    if (btn) btn.style.display = visible ? '' : 'none';
  },
};
