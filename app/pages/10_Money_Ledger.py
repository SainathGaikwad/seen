"""S11 — Money ledger: every sponsorship, tip and payout that went through PayPal, in an AG Grid (Community)
with filters, totals that follow the filter, and CSV export. Real sandbox money unless a row says simulated."""
import json

import streamlit as st
import streamlit.components.v1 as components

from common import CFG, DERIVED, data_banner, inject_css, load_csv, require_run
from money_ui import gateway_caption, refresh_payouts

from seen.money import ledger

st.set_page_config(page_title="SEEN — Money ledger", page_icon="🏏", layout="wide")
inject_css()
st.title("Money ledger")
data_banner()
st.caption(gateway_caption())

AG_GRID_JS = "https://cdn.jsdelivr.net/npm/ag-grid-community@36.1.0/dist/ag-grid-community.min.js"

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<script src="__JS__"></script>
<style>
  body { margin: 0; font-family: "Source Sans Pro", -apple-system, "Segoe UI", sans-serif; color: #1f2937; }
  .bar { display: flex; gap: .6rem; align-items: center; margin: 0 0 .5rem 0; flex-wrap: wrap; }
  .bar input { flex: 1; min-width: 220px; padding: .45rem .6rem; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; }
  .bar button { padding: .45rem .8rem; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; cursor: pointer; font-size: 14px; }
  .bar button:hover { background: #f1f5f9; }
  .bar .n { color: #64748b; font-size: 13px; }
  h4 { margin: 1rem 0 .4rem 0; font-weight: 600; }
  .badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; line-height: 18px; }
  .ok { background: #dcfce7; color: #166534; } .wait { background: #fef9c3; color: #854d0e; } .bad { background: #fee2e2; color: #991b1b; } .na { background: #e2e8f0; color: #334155; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
  .kind-sponsorship { color: #1d4ed8; font-weight: 600; } .kind-tip { color: #be185d; font-weight: 600; } .kind-payout { color: #047857; font-weight: 600; } .kind-invoice { color: #6d28d9; font-weight: 600; }
  .sharebar { position: relative; height: 16px; background: #eef2ff; border-radius: 3px; overflow: hidden; margin-top: 7px; }
  .sharebar > div { position: absolute; left: 0; top: 0; bottom: 0; background: #6366f1; }
  .ag-row-pinned .ag-cell { font-weight: 700; background: #f8fafc; }
</style></head>
<body>
<div class="bar">
  <input id="q" placeholder="Quick filter — athlete, sponsor, PayPal id, status…">
  <button id="csv">Export CSV</button>
  <button id="reset">Reset filters</button>
  <span class="n" id="count"></span>
</div>
<div id="ledger" style="height: 430px;"></div>
<h4>By athlete — money raised for her story, and where it goes</h4>
<div id="athletes" style="height: 250px;"></div>
<script>
const rows = __ROWS__;
const athletes = __ATHLETES__;
if (window.agGrid && agGrid.ModuleRegistry && agGrid.AllCommunityModule) { agGrid.ModuleRegistry.registerModules([agGrid.AllCommunityModule]); }
const money = p => (p.value === null || p.value === undefined || p.value === '') ? '' : '$' + Number(p.value).toFixed(2);
const statusClass = s => { s = String(s || '').toUpperCase();
  if (['COMPLETED','PAID','SUCCESS'].includes(s)) return 'ok';
  if (['CREATED','PAYER_ACTION_REQUIRED','SENT','PENDING','PROCESSING','UNCLAIMED','APPROVED'].includes(s)) return 'wait';
  if (['FAILED','DENIED','CANCELED','CANCELLED','VOIDED','BLOCKED','RETURNED'].includes(s) || s.startsWith('FAILED')) return 'bad';
  return 'na'; };
const badge = p => p.node.rowPinned ? '' : `<span class="badge ${statusClass(p.value)}">${p.value || '—'}</span>`;
const columnDefs = [
  { field: 'ts', headerName: 'When (UTC)', width: 165, filter: 'agDateColumnFilter', filterValueGetter: p => p.data && p.data.ts ? new Date(p.data.ts) : null,
    valueFormatter: p => p.value ? String(p.value).replace('T', ' ').replace('+00:00', '') : '', sort: 'desc' },
  { field: 'kind', headerName: 'Kind', width: 125, cellClass: p => 'kind-' + p.value },
  { field: 'athlete', headerName: 'Athlete', flex: 1, minWidth: 150 },
  { field: 'team', headerName: 'Team', width: 120 },
  { field: 'languages', headerName: 'Lang', width: 95, valueFormatter: p => String(p.value || '').toUpperCase() },
  { field: 'payer', headerName: 'From', width: 170 },
  { field: 'amount', headerName: 'USD', width: 105, type: 'numericColumn', filter: 'agNumberColumnFilter', valueFormatter: money },
  { headerName: 'Split by policy', children: [
    { field: 'split_athlete', headerName: 'Athlete fund', width: 115, type: 'numericColumn', valueFormatter: money },
    { field: 'split_creator', headerName: 'Creator', width: 100, type: 'numericColumn', valueFormatter: money },
    { field: 'split_seen', headerName: 'SEEN', width: 90, type: 'numericColumn', valueFormatter: money, columnGroupShow: 'open' } ] },
  { field: 'status', headerName: 'Status', width: 150, cellRenderer: badge },
  { field: 'payout_status', headerName: 'Payout', width: 125, cellRenderer: badge },
  { field: 'ref', headerName: 'PayPal id', width: 210, cellClass: 'mono' },
  { field: 'simulated', headerName: 'Money', width: 100, valueFormatter: p => p.node.rowPinned ? '' : (String(p.value).toLowerCase() === 'true' ? 'simulated' : 'sandbox') },
  { field: 'item', headerName: 'Item', width: 320, columnGroupShow: 'open' },
];
const grid = agGrid.createGrid(document.getElementById('ledger'), {
  theme: agGrid.themeQuartz, columnDefs, rowData: rows,
  defaultColDef: { sortable: true, filter: true, resizable: true, floatingFilter: true },
  pagination: true, paginationPageSize: 20, paginationPageSizeSelector: [20, 50, 100],
  animateRows: true, enableCellTextSelection: true,
  getRowId: p => p.data.kind + ':' + p.data.ref + ':' + p.data.player_id + ':' + p.data.ts + ':' + p.data.item,
  onFilterChanged: totals, onFirstDataRendered: totals,
});
function totals() {
  let n = 0, t = { ts: '', kind: 'TOTAL', athlete: '', amount: 0, split_athlete: 0, split_creator: 0, split_seen: 0, status: '', payout_status: '', ref: '' };
  grid.forEachNodeAfterFilter(nd => { n++; const d = nd.data; const paid = ['COMPLETED','PAID'].includes(String(d.status).toUpperCase()) && d.kind !== 'payout';
    if (paid) { t.amount += +d.amount || 0; t.split_athlete += +d.split_athlete || 0; t.split_creator += +d.split_creator || 0; t.split_seen += +d.split_seen || 0; } });
  t.athlete = 'paid rows in view';
  grid.setGridOption('pinnedBottomRowData', [t]);
  document.getElementById('count').textContent = n + ' of ' + rows.length + ' rows';
}
document.getElementById('q').addEventListener('input', e => grid.setGridOption('quickFilterText', e.target.value));
document.getElementById('csv').onclick = () => grid.exportDataAsCsv({ fileName: 'seen_money_ledger.csv' });
document.getElementById('reset').onclick = () => { grid.setFilterModel(null); document.getElementById('q').value = ''; grid.setGridOption('quickFilterText', ''); };
const maxRaised = Math.max(1, ...athletes.map(a => +a.raised || 0));
agGrid.createGrid(document.getElementById('athletes'), {
  theme: agGrid.themeQuartz, rowData: athletes,
  columnDefs: [
    { field: 'athlete', headerName: 'Athlete', flex: 1, minWidth: 150 },
    { field: 'team', headerName: 'Team', width: 120 },
    { field: 'raised', headerName: 'Raised', width: 110, type: 'numericColumn', valueFormatter: money, sort: 'desc' },
    { headerName: 'Share of all money raised', width: 220, valueGetter: p => +p.data.raised || 0,
      cellRenderer: p => `<div class="sharebar" title="${(100 * p.value / maxRaised).toFixed(0)}% of the top athlete"><div style="width:${(100 * p.value / maxRaised).toFixed(1)}%"></div></div>` },
    { field: 'sponsorships', headerName: 'Sponsorships', width: 120, type: 'numericColumn' },
    { field: 'tips', headerName: 'Tips', width: 80, type: 'numericColumn' },
    { field: 'to_athlete', headerName: 'To athlete fund', width: 130, type: 'numericColumn', valueFormatter: money },
    { field: 'to_creator', headerName: 'To creator', width: 110, type: 'numericColumn', valueFormatter: money },
    { field: 'sponsors', headerName: 'Presented by', flex: 1, minWidth: 160 },
  ],
  defaultColDef: { sortable: true, filter: true, resizable: true },
});
</script>
</body></html>"""

if require_run():
    c1, c2 = st.columns([6, 1])
    if c2.button("Refresh payouts", help="Ask PayPal for the status of pending payout batches"):
        n = refresh_payouts()
        st.toast(f"Updated {n} payout row(s)")
    df = ledger.load(DERIVED)
    if df.empty:
        st.info("Nothing has moved yet. Sponsor a story on the **Sponsor Desk** page or tip one in the **Fan feed**; every PayPal order, invoice and payout lands here.")
        st.stop()
    t = ledger.totals(df)
    m = st.columns(6)
    m[0].metric("Raised", f"${t['raised']:,.2f}")
    m[1].metric("Sponsorships", t["sponsorships"])
    m[2].metric("Tips", t["tips"])
    m[3].metric("To athlete fund", f"${t['to_athletes']:,.2f}")
    m[4].metric("To creators", f"${t['to_creators']:,.2f}")
    m[5].metric("Paid out", f"${t['paid_out']:,.2f}", f"{t['pending']} awaiting payment" if t["pending"] else None, delta_color="off")
    st.caption(("All rows are PayPal **sandbox** test money." if not t["simulated"] else "Some rows are **simulated** (no PayPal credentials when they were made).")
               + " Split policy: sponsorships 60 / 30 / 10 and tips 70 / 20 / 10 — athlete fund / creator / SEEN. Totals in the grid follow the filters.")
    xi = load_csv("unseen_xi.csv")
    by = ledger.by_athlete(df)
    rows = df.sort_values("ts", ascending=False).to_dict(orient="records")
    html = HTML.replace("__JS__", AG_GRID_JS).replace("__ROWS__", json.dumps(rows, default=str)).replace("__ATHLETES__", json.dumps(by.to_dict(orient="records"), default=str))
    components.html(html, height=800, scrolling=False)
    with st.expander("Raw CSV"):
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button("Download money_ledger.csv", df.to_csv(index=False).encode("utf-8"), "money_ledger.csv", "text/csv",
                           help="The hosted demo's disk is reset on every deploy: download after a sandbox session and commit it to keep the history")
        sp = json.dumps(ledger.sponsorships(DERIVED), indent=1, ensure_ascii=False)
        st.download_button("Download sponsorships.json", sp.encode("utf-8"), "sponsorships.json", "application/json")
