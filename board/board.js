// 対戦の盤面。Python から局面（data）を受け取って描き、札が選ばれたら setTriggerValue('play', …) で返す。
// 新しいラウンドの結果が届いたときは「場に出す → めくる → 点が移る → 次の得点カードを配る」を演出する。
const TOTAL = 55;   // 得点カード 1〜10 の合計
const sleep = ms => new Promise(r => setTimeout(r, ms));
const pct = p => `${Math.round(p * 100)}%`;

export default function (component) {
  const { parentElement: root, data, setTriggerValue } = component;
  const $ = id => root.querySelector('#' + id);
  const el = root.querySelector('.table');
  if (!data || !el) return;
  const mem = (root.__yomiai ||= { seen: -1, shownAt: {}, busy: false });
  // データが変わるたびにこの関数が呼び直される（前回の後片付けは呼ばれない）ので、自分で片付ける
  if (mem.cleanup) mem.cleanup();
  let alive = true;

  // ---------- 小さな部品 ----------
  const card = (v, who) =>
    `<div class="pcard ${who}" style="position:absolute;inset:0"><span class="tl">${v}</span><span class="num">${v}</span><span class="br">${v}</span></div>`;
  const flipCard = (v, who) =>
    `<div class="flip"><div class="face back-${who}"></div><div class="face front">${card(v, who)}</div></div>`;
  const back = who => `<div class="flip"><div class="face back-${who}"></div></div>`;
  const opened = (v, who) => flipCard(v, who).replace('class="flip"', 'class="flip open"');

  // 先頭 k ラウンドまでに、相打ちで流れた点
  const burnedAt = k => data.log.slice(0, k).reduce((a, lg) => a + (lg.winner === -1 ? lg.prize : 0), 0);
  // 勝ち確定のライン：流れていない点の過半数
  const lineOf = burned => Math.floor((TOTAL - burned) / 2) + 1;

  // ある時点（log の先頭 k ラウンド）までの、得点カード1〜10の状態
  function chipState(k, showCurrent) {
    const st = {};
    data.log.slice(0, k).forEach(lg => {
      st[lg.prize] = { cls: 'done ' + (lg.winner === 0 ? 'you' : lg.winner === 1 ? 'ai' : 'none'), r: lg.round,
                       tie: lg.winner === -1 };
    });
    if (showCurrent && data.prize != null) st[data.prize] = { cls: 'now', r: k + 1 };
    return st;
  }
  function drawChips(k, showCurrent) {
    const st = chipState(k, showCurrent);
    $('prize-chips').innerHTML = Array.from({ length: 10 }, (_, i) => i + 1).map(v => {
      const s = st[v];
      const tip = !s ? 'まだ出ていない' : s.cls === 'now' ? 'いまの得点カード' : s.tie ? `R${s.r} 相打ちで流れた` : `R${s.r}`;
      const label = s && s.cls !== 'now' ? `<small>${s.tie ? '流れた' : 'R' + s.r}</small>` : '';
      return `<div class="chip ${s ? s.cls : ''}" title="${tip}">${v}${label}</div>`;
    }).join('');
  }
  function drawScore(score, burned) {
    $('pts-you').textContent = score[0];
    $('pts-ai').textContent = score[1];
    const avail = TOTAL - burned, line = lineOf(burned);
    const rest = avail - score[0] - score[1];
    // バー全体＝流れていない点。白線はいつも真ん中＝勝ち確定のライン
    $('seg-you').style.width = `${(score[0] / avail) * 100}%`;
    $('seg-ai').style.width = `${(score[1] / avail) * 100}%`;
    const need = (s, other) => s >= line ? '<b>勝ち確定！</b>'
      : other >= line ? '逆転できない'
      : data.over && rest === 0 ? '' : `<span class="long">勝ち確定まで </span><b>あと ${line - s} 点</b>`;
    $('need-you').innerHTML = need(score[0], score[1]);
    $('need-ai').innerHTML = need(score[1], score[0]);
    $('rest-label').innerHTML = `残り <b>${rest}</b> 点<span class="long"> ｜ <span class="line"></span>＝${line}点で勝ち確定` +
      `${burned ? `（${burned}点流れた）` : ''}</span>`;
  }
  function drawOpp(hand, justCard) {
    const usedAt = {};
    data.log.forEach(lg => (usedAt[lg.cards[1]] = lg.round));
    const best = Math.max(...hand);
    $('opp-hand').innerHTML = Array.from({ length: 10 }, (_, i) => i + 1).map(v => {
      const has = hand.includes(v);
      const cls = ['mini', has ? '' : 'used', has && v === best ? 'best' : '', v === justCard ? 'just' : ''].join(' ');
      const tip = has ? (v === best ? 'AIの最強札' : 'まだ持っている') : `R${usedAt[v]} で使った`;
      return `<div class="${cls}" title="${tip}">${v}${!has && usedAt[v] ? `<small>R${usedAt[v]}使用</small>` : ''}</div>`;
    }).join('');
    const sum = hand.reduce((a, b) => a + b, 0);
    $('opp-sum').innerHTML = hand.length
      ? `<span class="badge">残り<b>${hand.length}</b>枚</span><span class="badge">最強<b>${best}</b></span>` +
        `<span class="badge">8以上<b>${hand.filter(c => c >= 8).length}</b>枚</span><span class="badge">合計<b>${sum}</b></span>`
      : '';
  }
  function drawHistory() {
    $('hist').innerHTML = Array.from({ length: data.n }, (_, i) => {
      const lg = data.log[i];
      if (!lg) return `<div class="h empty"><span class="p">R${i + 1}</span>–</div>`;
      const w = lg.winner;
      return `<div class="h ${w === -1 ? 'tie' : ''}" title="${w === -1 ? '相打ちで流れた' : '得点 ' + lg.prize}"><span class="p">${lg.prize}点</span>` +
        `<span class="y ${w === 0 ? 'w' : ''}">${lg.cards[0]}</span> <span class="a ${w === 1 ? 'w' : ''}">${lg.cards[1]}</span></div>`;
    }).join('');
  }
  // 得点カードと、その下の一言（取れば勝ち確定になるか）
  function drawPrize(prize, score, burned, deal) {
    const p = $('prize');
    $('prize-num').textContent = prize ?? '';
    p.style.visibility = prize == null ? 'hidden' : 'visible';
    p.classList.remove('deal');
    if (deal) { void p.offsetWidth; p.classList.add('deal'); }
    let note = '';
    if (prize != null && score) {
      const line = lineOf(burned);
      const you = score[0] < line && score[0] + prize >= line, ai = score[1] < line && score[1] + prize >= line;
      note = you && ai ? '取った方が勝ち確定！' : you ? 'あなたが取れば勝ち確定！' : ai ? 'AIが取ると勝ち確定…' : '';
    }
    $('carry').textContent = note;
  }
  function drawHand(locked) {
    const hand = data.hands[0];
    const n = hand.length;
    // 札の大きさは前と同じ決め方。まっすぐ一列に並べ、入りきらないときだけ少し重ねる
    const hw = $('hand');
    const avail = hw.clientWidth - 8;
    const w = Math.max(38, Math.min(66, avail / Math.max(n * 0.8, 1)));
    const gap = Math.min(6, (avail - w) / Math.max(n - 1, 1) - w);   // 札と札の間（マイナスなら重なる）
    hw.classList.toggle('locked', locked);
    hw.style.setProperty('--w', `${w}px`);
    hw.style.setProperty('--overlap', `${Math.round(gap)}px`);
    hw.style.height = `${Math.round(w * 1.42 + 22)}px`;   // 札の高さ＋選ぶときに持ち上げる分
    hw.innerHTML = hand.map(v =>
      `<button class="hcard" data-card="${v}" aria-label="${v} を出す" ${locked ? 'tabindex="-1"' : ''}>` +
      `<span class="tl">${v}</span><span class="num">${v}</span></button>`).join('');
    const touch = window.matchMedia('(pointer: coarse)').matches;
    $('hand-hint').textContent = data.over ? '' : locked ? '…'
      : touch ? 'タップして出す' : '出す札をクリック（キーボードの 1〜9・0 でもOK）';
    hw.parentElement.hidden = !!data.over;
  }
  function drawReview() {
    const last = data.last, lg = data.log[data.log.length - 1];
    if (!last || !lg) { $('review').hidden = true; return; }
    $('review').hidden = false;
    const res = lg.winner === 0 ? `<span class="you">あなたが ${lg.prize} 点</span>`
      : lg.winner === 1 ? `<span class="ai">AIが ${lg.prize} 点</span>` : '相打ち → 得点カードは流れた';
    $('review-head').innerHTML = `ラウンド ${lg.round}　得点 ${lg.prize} 点 ｜ あなた <span class="you">${lg.cards[0]}</span> vs AI <span class="ai">${lg.cards[1]}</span> → ${res}`;
    const probs = last.read, maxp = Math.max(...Object.values(probs), 0.01);
    $('read-bars').innerHTML = Array.from({ length: 10 }, (_, i) => i + 1).map(v => {
      const p = probs[v];
      if (p == null) return `<div class="rb na"><em></em><i style="height:0"></i><span>${v}</span></div>`;
      const cls = ['rb', v === lg.cards[0] ? 'played' : '', v === last.top ? 'top' : ''].join(' ');
      return `<div class="${cls}"><em>${p >= 0.05 ? pct(p) : ''}</em><i style="height:${(p / maxp) * 70}px"></i><span>${v}</span></div>`;
    }).join('');
    const forced = Object.keys(probs).length === 1;
    const s = $('stamp');
    s.className = 'stamp ' + (forced ? '' : last.top === lg.cards[0] ? 'hit' : 'miss');
    s.textContent = forced ? '' : last.top === lg.cards[0] ? '読まれた！' : '読みを外した！';
    const best = Math.max(...last.ev.map(e => e[1]), 0.01);
    $('think').innerHTML = forced ? '最後の1枚なので、読むまでもありません。'
      : `AIの読み：あなたは <b>${last.top}</b> を出す（${pct(probs[last.top])}）<br>` +
        `<span style="color:#9aa6bd">AIの札ごとの期待勝率</span>` +
        last.ev.map(([c, v]) => `<div class="ev">${c}：<i style="width:${(v / best) * 60}px"></i>${pct(v)}</div>`).join('') +
        `→ AIは <b>${lg.cards[1]}</b> を選んだ`;
  }
  function drawRibbon() {
    const last = data.last, lg = data.log[data.log.length - 1];
    if (!last || !lg) { $('ribbon').innerHTML = ''; return; }
    const res = lg.winner === 0 ? `<span class="you">あなた +${lg.prize}</span>`
      : lg.winner === 1 ? `<span class="ai">AI +${lg.prize}</span>` : `相打ち・${lg.prize}点は流れた`;
    const forced = Object.keys(last.read).length === 1;
    const read = forced ? '' : last.top === lg.cards[0]
      ? `｜<span class="hit">AIの読み ${last.top} → 読まれた！</span>` : `｜<span class="miss">AIの読み ${last.top} → 外した！</span>`;
    $('ribbon').innerHTML = `R${lg.round}：<span class="you">${lg.cards[0]}</span> vs <span class="ai">${lg.cards[1]}</span> → ${res} ${read}`;
  }
  function drawSlots(mode) {
    // mode: 'wait'（AIだけ伏せてある） / 'empty'
    $('card-you').className = 'slot-card';
    $('card-you').innerHTML = '';
    $('card-ai').className = 'slot-card' + (mode === 'wait' ? ' filled' : '');
    $('card-ai').innerHTML = mode === 'wait' ? back('ai') : '';
    if (mode === 'wait') $('card-ai').classList.add('drop');
  }
  function drawBanner() {
    const b = $('banner');
    if (!data.over) { b.hidden = true; return; }
    const [y, a] = data.score;
    b.hidden = false;
    b.className = 'banner ' + (y > a ? 'win' : y < a ? 'lose' : 'draw');
    b.innerHTML = `<b>${y > a ? 'あなたの勝ち！' : y < a ? 'AIの勝ち' : '引き分け'}</b><span>${y} 点 － ${a} 点</span>`;
  }

  // ---------- 描画の流れ ----------
  function drawSettled() {
    $('round').textContent = Math.min(data.r + 1, data.n);
    const burned = burnedAt(data.log.length);
    drawScore(data.score, burned);
    drawChips(data.log.length, !data.over);
    drawOpp(data.hands[1]);
    drawHistory();
    drawReview();
    drawBanner();
    drawRibbon();
    if (data.over) {
      const lg = data.log[data.log.length - 1];
      drawPrize(lg.prize, null, burned, false);
      $('card-you').className = 'slot-card filled' + (lg.winner === 0 ? ' win' : lg.winner === 1 ? ' lose' : '');
      $('card-you').innerHTML = opened(lg.cards[0], 'you');
      $('card-ai').className = 'slot-card filled' + (lg.winner === 1 ? ' win' : lg.winner === 0 ? ' lose' : '');
      $('card-ai').innerHTML = opened(lg.cards[1], 'ai');
      drawHand(true);
      return;
    }
    drawPrize(data.prize, data.score, burned, false);
    drawSlots('wait');
    drawHand(false);
    if (mem.shownAt[data.r] == null) mem.shownAt[data.r] = performance.now();
  }

  async function animateReveal() {
    mem.busy = true;
    const lg = data.log[data.log.length - 1];
    const before = data.log.length > 1 ? data.log[data.log.length - 2].score : [0, 0];
    const burnedBefore = burnedAt(data.log.length - 1), burnedNow = burnedAt(data.log.length);
    // ① 前のラウンドの場を再現：得点カードと、両者の伏せ札
    $('round').textContent = lg.round;
    drawScore(before, burnedBefore);
    drawChips(lg.round - 1, false);
    $('prize-chips').querySelectorAll('.chip')[lg.prize - 1].className = 'chip now';
    drawOpp([...data.hands[1], lg.cards[1]]);
    drawPrize(lg.prize, before, burnedBefore, false);
    drawHistory();
    $('banner').hidden = true;
    $('review').hidden = true;
    drawHand(true);
    $('card-you').className = 'slot-card filled';
    $('card-you').innerHTML = flipCard(lg.cards[0], 'you');
    $('card-ai').className = 'slot-card filled';
    $('card-ai').innerHTML = flipCard(lg.cards[1], 'ai');
    $('card-you').classList.add('drop');
    $('ribbon').innerHTML = '';
    await sleep(480); if (!alive) return;
    // ② めくる
    $('card-you').firstElementChild.classList.add('open');
    $('card-ai').firstElementChild.classList.add('open');
    await sleep(650); if (!alive) return;
    // ③ 勝敗と、点の移動
    if (lg.winner !== -1) {
      $(lg.winner === 0 ? 'card-you' : 'card-ai').classList.add('win');
      $(lg.winner === 0 ? 'card-ai' : 'card-you').classList.add('lose');
    } else {   // 相打ち：両方の札がぶつかり、得点カードは燃えて流れる
      $('card-you').classList.add('clash');
      $('card-ai').classList.add('clash');
      $('prize').classList.add('burn');
    }
    const f = $('float');
    f.className = 'float';
    f.textContent = lg.winner === -1 ? `相打ち！ ${lg.prize}点は流れた` : `+${lg.prize}`;
    if (lg.winner !== -1) {   // 飛んでいく先＝勝った側の点数の位置
      const from = f.getBoundingClientRect(), to = $(lg.winner === 0 ? 'pts-you' : 'pts-ai').getBoundingClientRect();
      f.style.setProperty('--tx', `${to.left + to.width / 2 - (from.left + from.width / 2)}px`);
      f.style.setProperty('--ty', `${to.top - from.top}px`);
    }
    void f.offsetWidth;
    f.classList.add(lg.winner === 0 ? 'go-you' : lg.winner === 1 ? 'go-ai' : 'go-tie');
    drawReview();
    await sleep(700); if (!alive) return;
    drawScore(data.score, burnedNow);
    if (lg.winner !== -1) {
      const p = $(lg.winner === 0 ? 'pts-you' : 'pts-ai');
      p.classList.remove('bump'); void p.offsetWidth; p.classList.add('bump');
    }
    drawChips(data.log.length, false);
    drawOpp(data.hands[1], lg.cards[1]);
    await sleep(900); if (!alive) return;
    // ④ 次のラウンドへ（終わっていれば結果）
    mem.seen = lg.round;
    mem.busy = false;
    if (data.over) { drawBanner(); drawHand(true); return; }
    $('round').textContent = data.r + 1;
    drawChips(data.log.length, true);
    $('prize').classList.remove('burn');
    drawPrize(data.prize, data.score, burnedNow, true);
    drawSlots('wait');
    drawRibbon();
    drawHand(false);
    mem.shownAt[data.r] = performance.now();
  }

  const lastRound = data.log.length ? data.log[data.log.length - 1].round : 0;
  if (lastRound > mem.seen && data.last) animateReveal();
  else { mem.seen = lastRound; drawSettled(); }

  // ---------- 入力 ----------
  function play(v) {
    if (mem.busy || data.over || !data.hands[0].includes(v) || $('hand').classList.contains('locked')) return;
    const btn = root.querySelector(`.hcard[data-card="${v}"]`);
    $('hand').classList.add('locked');
    btn.classList.add('picked');
    $('card-you').className = 'slot-card filled';
    $('card-you').innerHTML = back('you');
    $('card-you').classList.add('drop');
    $('hand-hint').textContent = 'オープン！';
    const think = Math.round(performance.now() - (mem.shownAt[data.r] ?? performance.now()));
    setTimeout(() => { if (alive) setTriggerValue('play', { card: v, round: data.r, think_ms: think }); }, 260);
  }
  const onClick = e => {
    const b = e.target.closest('.hcard');
    if (b) play(Number(b.dataset.card));
  };
  const onKey = e => {
    if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
    if (/^[0-9]$/.test(e.key)) { play(e.key === '0' ? 10 : Number(e.key)); }
  };
  el.addEventListener('click', onClick);
  window.addEventListener('keydown', onKey);
  mem.cleanup = () => {
    alive = false;
    mem.busy = false;
    el.removeEventListener('click', onClick);
    window.removeEventListener('keydown', onKey);
    mem.cleanup = null;
  };
  return mem.cleanup;
}
