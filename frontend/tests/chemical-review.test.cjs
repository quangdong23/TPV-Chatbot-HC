const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function screen() {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {value:'', style:{}, dataset:{}, disabled:false, innerHTML:'', textContent:'',
      events:{}, addEventListener(name, fn) {this.events[name]=fn;}, querySelectorAll(){return [];}});
    return nodes.get(id);
  };
  const alerts = [];
  const window = {API:{}};
  const document = {readyState:'loading', getElementById:node, addEventListener(){}};
  const context = {window, document, console, alert: message => alerts.push(message)};
  let source = fs.readFileSync(path.join(__dirname,'../js/chemicals.js'),'utf8');
  source = source.replace('  global.tpvChemicals = {', '  global.reviewTest = {state, bindEvents, handleExtractAi, handleRunDocumentReview, renderReviewResult, reviewStatus};\n  global.tpvChemicals = {');
  vm.runInNewContext(source,context);
  const api = window.API;
  const code = window.reviewTest;
  code.bindEvents();
  return {node, api, code, alerts};
}

test('file preview requires a separate confirmation and submits edited values', async () => {
  const {node,api,code,alerts}=screen();
  let previews=0, reviews=0, sent;
  code.state.selectedFile={name:'scan.png'};
  api.chemicalPreviewFile=async () => {previews++;return {file_name:'scan.png',items:[{room_code:'R01',chemical_code:'001',metric:'Quantity_mL',value:1500,unit:'mL'}]};};
  api.chemicalReviewDoc=async payload => {reviews++;sent=payload;return {results:[]};};
  await code.handleRunDocumentReview();assert.equal(reviews,0);
  await code.handleExtractAi();assert.equal(previews,1);assert.equal(reviews,0);
  assert.equal(node('chemRevSubmitBtn').disabled,false);
  node('chemExtractedTable').events.input({target:{dataset:{row:'0',field:'value'},value:'0'}});
  await code.handleRunDocumentReview();assert.equal(reviews,1);
  assert.equal(sent.items[0].value,'0');assert.equal(sent.items[0].chemical_code,'001');assert.equal(alerts.length,0);
  node('chemRevText').events.input();
  await code.handleRunDocumentReview();assert.equal(reviews,1);assert.equal(node('chemRevSubmitBtn').disabled,true);
});

test('invalid edited values are stopped before querying SQL', async () => {
  const {code,alerts}=screen();
  code.state.extractedItems=[{room_code:'R01',metric:'Quantity_mL',value:'not a number'}];
  await code.handleRunDocumentReview();assert.equal(alerts.length,1);
});

test('status totals and filters agree, snapshots count as matched, missing is not zero', () => {
  const {code,node}=screen();
  const results=['matched','matched_latest_snapshot','value_mismatch','missing_in_database','timestamp_mismatch'].map((status,i)=>({status,room_code:i===2?'<script>':'' ,metric:'Quantity_mL',report_value:0,db_value:status==='missing_in_database'?null:0,report_unit:'mL',db_unit:'mL',abs_diff:i===2?10:null}));
  const data={results,summary:{counts_by_status:{matched:99},db_coverage:{max_measured_at:'2026-11-07T08:00:00Z'}}};
  code.renderReviewResult(data);
  const html=node('chemRevResult').innerHTML;
  assert.match(html,/Khớp<\/span><b[^>]*>2/);assert.match(html,/Sai lệch<\/span><b[^>]*>1/);
  assert.match(html,/Cần chú ý \(3\)/);assert.match(html,/Không có dữ liệu/);assert.match(html,/0 mL/);
  assert.match(html,/Chênh lệch/);assert.doesNotMatch(html,/<script>|28\/29|chốt 28/);
  code.state.reviewFilter='matched';code.renderReviewResult(data);
  assert.match(node('chemRevResult').innerHTML,/Khớp bản ghi chốt gần nhất/);
  assert.doesNotMatch(node('chemRevResult').innerHTML,/Lệch số liệu/);
});
