from __future__ import annotations
import random, time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

import streamlit as st

# ================= 기본 세팅 =================
st.set_page_config(page_title="Cool Choi Amazons", layout="wide")

SIZE = 10
EMPTY, HUM, CPU, BLOCK = 0, 1, 2, 3
DIRS = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]

# 이모지
EMO_HUM = "🔵"   # 플레이어
EMO_CPU = "🟡"   # 컴퓨터
EMO_BLK = "⬛"   # 블록
EMO_EMP = "·"   # 빈칸
EMO_MOVE = "🟩"  # 이동 가능
EMO_SHOT = "🟥"  # 사격 가능

# 보드 칸 크기(정사각형)
CELL_PX = 44

# 보드 전용 CSS + 타이머 박스(가로 1.5배 확대: 180px)
st.markdown(
    f"""
    <style>
    .board-grid div[data-testid="column"] {{
        padding: 2px !important;
    }}
    .board-grid .stButton > button {{
        width: {CELL_PX}px !important;
        height: {CELL_PX}px !important;
        margin: 0 !important;
        padding: 0 !important;
        line-height: {CELL_PX}px !important;
        border-radius: 10px !important;
        font-size: {int(CELL_PX*0.45)}px !important;
        display: inline-flex; align-items: center; justify-content: center;
    }}
    .board-grid .stButton > button:disabled {{
        opacity: 1.0 !important;
    }}
    .timer-row {{
        display:flex; align-items:center; gap:10px; flex-wrap:wrap;
    }}
    .timer-box {{
        display: inline-block; padding: 10px 14px; border-radius: 12px;
        font-weight: 700; font-size: 20px; border: 1px solid #e5e7eb;
        background: #f9fafb; color: #111827; min-width: 180px; /* 가로 확대 */
    }}
    .timer-active {{ background: #eef2ff; border-color:#c7d2fe; }}
    .timer-low {{ background:#fef2f2; border-color:#fecaca; color:#991b1b; }}
    .timer-name {{ font-size: 13px; font-weight:600; display:block; opacity:.8; margin-bottom:4px; }}
    .timer-time {{ font-variant-numeric: tabular-nums; }}
    </style>
    """,
    unsafe_allow_html=True,
)

@dataclass
class Move:
    fr: Tuple[int,int]
    to: Tuple[int,int]
    shot: Tuple[int,int]

Board = List[List[int]]

# ================= 보드/규칙 유틸 =================
def in_bounds(r:int,c:int)->bool:
    return 0 <= r < SIZE and 0 <= c < SIZE

def clone(b:Board)->Board:
    return [row[:] for row in b]

def iter_ray(b:Board, r:int,c:int, dr:int,dc:int):
    nr, nc = r+dr, c+dc
    while in_bounds(nr,nc) and b[nr][nc]==EMPTY:
        yield (nr,nc)
        nr += dr; nc += dc

def piece_positions(b:Board, side:int)->List[Tuple[int,int]]:
    token = HUM if side==HUM else CPU
    return [(r,c) for r in range(SIZE) for c in range(SIZE) if b[r][c]==token]

def legal_dests_from(b:Board, r:int,c:int)->List[Tuple[int,int]]:
    out=[]
    for dr,dc in DIRS:
        out.extend(iter_ray(b,r,c,dr,dc))
    return out

def legal_shots_from(b:Board, r:int,c:int)->List[Tuple[int,int]]:
    return legal_dests_from(b,r,c)

def apply_move(b:Board, mv:Move, side:int)->Board:
    nb = clone(b)
    (r1,c1),(r2,c2),(rs,cs) = mv.fr, mv.to, mv.shot
    nb[r1][c1] = EMPTY
    nb[r2][c2] = side
    nb[rs][cs] = BLOCK
    return nb

def has_any_move(b:Board, side:int)->bool:
    return any(legal_dests_from(b,r,c) for r,c in piece_positions(b, side))

# ================= 평가/AI(간결) =================
def mobility(b:Board, side:int)->int:
    return sum(len(legal_dests_from(b,r,c)) for r,c in piece_positions(b, side))

def liberties(b:Board, side:int)->int:
    s=0
    for r,c in piece_positions(b, side):
        for dr,dc in DIRS:
            nr,nc=r+dr,c+dc
            if in_bounds(nr,nc) and b[nr][nc]==EMPTY:
                s+=1
    return s

def center_score(b:Board, side:int)->int:
    cx, cy = (SIZE-1)/2, (SIZE-1)/2
    tot=0
    for r,c in piece_positions(b, side):
        tot -= int(abs(r-cx)+abs(c-cy))
    return tot

def evaluate(b:Board)->int:
    return 10*(mobility(b,CPU)-mobility(b,HUM)) + 2*(liberties(b,CPU)-liberties(b,HUM)) + (center_score(b,CPU)-center_score(b,HUM))

def gen_moves_limited(b:Board, side:int, k_dest:int, k_shot:int, cap:int)->List[Move]:
    out=[]
    for r,c in piece_positions(b, side):
        dests=legal_dests_from(b,r,c)
        scored=[]
        for tr,tc in dests:
            tmp = clone(b); tmp[r][c]=EMPTY; tmp[tr][tc]=side
            sc = mobility(tmp, side) - mobility(tmp, HUM if side==CPU else CPU)
            scored.append(((tr,tc), sc))
        scored.sort(key=lambda x:x[1], reverse=True)
        for (tr,tc),_ in scored[:k_dest]:
            tmp = clone(b); tmp[r][c]=EMPTY; tmp[tr][tc]=side
            shots = legal_shots_from(tmp,tr,tc)
            s2=[]
            for sr,sc in shots:
                tmp2 = clone(tmp); tmp2[sr][sc]=BLOCK
                s2.append(((sr,sc), mobility(tmp2, side)-mobility(tmp2, HUM if side==CPU else CPU)))
            s2.sort(key=lambda x:x[1], reverse=True)
            for (sr,sc),_ in s2[:k_shot]:
                out.append(Move((r,c),(tr,tc),(sr,sc)))
                if len(out)>=cap: return out
    return out

def search(b:Board, depth:int, a:int, bb:int, side:int, P:Dict[str,int])->int:
    if depth==0 or not has_any_move(b, side):
        if not has_any_move(b, side):
            return 10_000 if side==HUM else -10_000
        return evaluate(b)

    k_d = P[f"k_dest_d{depth}"]; k_s = P[f"k_shot_d{depth}"]; cap = P[f"cap_d{depth}"]
    moves = gen_moves_limited(b, side, k_d, k_s, cap)
    if not moves: return 10_000 if side==HUM else -10_000

    if side==CPU:
        best=-1_000_000
        for mv in moves:
            val = search(apply_move(b,mv,CPU), depth-1, a, bb, HUM, P)
            best = max(best,val); a=max(a,val)
            if bb<=a: break
        return best
    else:
        best=1_000_000
        for mv in moves:
            val = search(apply_move(b,mv,HUM), depth-1, a, bb, CPU, P)
            best = min(best,val); bb=min(bb,val)
            if bb<=a: break
        return best

def ai_move(b:Board, difficulty:int)->Optional[Move]:
    """난이도 1~15"""
    if difficulty <= 3:
        depth=1
        P=dict(
            k_dest_d1=6 + difficulty*3,
            k_shot_d1=5 + difficulty*2,
            cap_d1=40 + difficulty*20
        )
    elif difficulty <= 7:
        depth=2
        P=dict(
            k_dest_d2=8 + (difficulty-3)*2,
            k_shot_d2=6 + (difficulty-3),
            cap_d2=40 + 10*(difficulty-3),
            k_dest_d1=10, k_shot_d1=8, cap_d1=80
        )
    elif difficulty <= 12:
        depth=3
        s = difficulty-7  # 1~5
        P=dict(
            k_dest_d3=5 + s,         # 6~10
            k_shot_d3=4 + s//2,      # 4~6
            cap_d3=18 + 4*s,         # 22~38
            k_dest_d2=9 + s,         # 10~14
            k_shot_d2=7 + s//2,      # 7~9
            cap_d2=42 + 8*s,         # 50~82
            k_dest_d1=10, k_shot_d1=8, cap_d1=80
        )
    else:
        depth=4
        s = difficulty-12  # 1~3
        P=dict(
            k_dest_d4=3 + s,         # 4~6
            k_shot_d4=3 + (s//2),    # 3~4
            cap_d4=10 + 2*s,         # 12~16
            k_dest_d3=6 + s,         # 7~9
            k_shot_d3=5 + (s//2),    # 5~6
            cap_d3=20 + 4*s,         # 24~32
            k_dest_d2=10 + s,        # 11~13
            k_shot_d2=7 + (s//2),    # 7~8
            cap_d2=50 + 6*s,         # 56~68
            k_dest_d1=10, k_shot_d1=8, cap_d1=80
        )

    root = gen_moves_limited(b, CPU, P[f"k_dest_d{depth}"], P[f"k_shot_d{depth}"], P[f"cap_d{depth}"])
    if not root: return None
    best=None; val_best=-1_000_000
    for mv in root:
        v = search(apply_move(b,mv,CPU), depth-1, -1_000_000, 1_000_000, HUM, P)
        if v>val_best: val_best=v; best=mv
    return best

# ================= 초기 보드 =================
def initial_board()->Board:
    b = [[EMPTY for _ in range(SIZE)] for _ in range(SIZE)]
    # 사람(백) d1,g1,a4,j4  => (9,3),(9,6),(6,0),(6,9)
    b[9][3]=HUM; b[9][6]=HUM; b[6][0]=HUM; b[6][9]=HUM
    # 컴퓨터(흑) a7,j7,d10,g10 => (3,0),(3,9),(0,3),(0,6)
    b[3][0]=CPU; b[3][9]=CPU; b[0][3]=CPU; b[0][6]=CPU
    return b

# ================= 상태 =================
def reset_game():
    st.session_state.board = initial_board()
    st.session_state.turn = HUM
    st.session_state.phase = "select"  # select -> move -> shoot
    st.session_state.sel_from = None
    st.session_state.sel_to = None
    st.session_state.legal = set()
    st.session_state.difficulty = st.session_state.get("difficulty", 5)
    # 하이라이트/엔드 상태
    st.session_state.last_human_move = None
    st.session_state.last_cpu_move = None
    st.session_state.last_shot_pos = None
    st.session_state.highlight_to = None
    st.session_state.game_over = False
    st.session_state.winner = None
    st.session_state.show_dialog = False
    # --- 타이머(각 10분 = 600초), 시작 버튼 대기 ---
    st.session_state.remain_hum = 600.0
    st.session_state.remain_cpu = 600.0
    st.session_state.last_update = time.time()
    st.session_state.timer_started = False  # ▶ 게임 시작 버튼 눌러야 카운트다운

if "board" not in st.session_state:
    reset_game()

# ========= 타임 포맷 & 카운트다운 틱 =========
def fmt_time(sec: float) -> str:
    if sec < 0: sec = 0
    m = int(sec) // 60
    s = int(sec) % 60
    return f"{m:02d}:{s:02d}"

def tick_human_time():
    """게임이 시작되었고 인간 턴일 때만 시간 차감."""
    if st.session_state.game_over or not st.session_state.timer_started:
        return
    if st.session_state.turn == HUM:
        now = time.time()
        dt = now - st.session_state.last_update
        if dt > 0:
            st.session_state.remain_hum -= dt
        st.session_state.last_update = now

def check_flag_fall():
    """시간 초과 체크."""
    if st.session_state.remain_hum <= 0 and not st.session_state.game_over:
        announce_and_set("컴퓨터(시간초과 승)", ok=False)
        end_game("컴퓨터(시간초과 승)", human_win=False)
    if st.session_state.remain_cpu <= 0 and not st.session_state.game_over:
        announce_and_set("플레이어(시간초과 승)", ok=True)
        end_game("플레이어(시간초과 승)", human_win=True)

# 먼저 인간시간을 틱
tick_human_time()
check_flag_fall()

# ========== 팝업(모달) ==========
@st.dialog("경기 종료")
def winner_dialog(who: str):
    st.markdown(f"### **{who} 승리!** 🎉")
    st.write("새 게임을 시작하거나 창을 닫을 수 있어요.")
    colA, colB = st.columns(2)
    def close_dialog(): st.session_state.show_dialog = False
    def new_game(): reset_game()
    if colA.button("닫기", use_container_width=True): close_dialog()
    if colB.button("새 게임", use_container_width=True): new_game(); st.rerun()

# ================= 상단 UI =================
left, right = st.columns([1,1])

# ---- 좌측상단: 10분 카운트다운 + '게임 시작' 버튼 ----
with left:
    hum_left = st.session_state.remain_hum
    cpu_left = st.session_state.remain_cpu
    hum_low = hum_left <= 30
    cpu_low = cpu_left <= 30
    hum_classes = "timer-box"
    cpu_classes = "timer-box"
    if st.session_state.turn == HUM: hum_classes += " timer-active"
    else: cpu_classes += " timer-active"
    if hum_low: hum_classes += " timer-low"
    if cpu_low: cpu_classes += " timer-low"

    st.markdown('<div class="timer-row">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <span class="{cpu_classes}">
          <span class="timer-name">{EMO_CPU} 컴퓨터</span>
          <span class="timer-time">{fmt_time(cpu_left)}</span>
        </span>
        """,
        unsafe_allow_html=True
    )
    st.markdown(
        f"""
        <span class="{hum_classes}">
          <span class="timer-name">{EMO_HUM} Cool Choi</span>
          <span class="timer-time">{fmt_time(hum_left)}</span>
        </span>
        """,
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ▶ 게임 시작 버튼: 눌러야 카운트다운 시작
    if not st.session_state.timer_started:
        if st.button("게임 시작 ▶", use_container_width=False):
            st.session_state.timer_started = True
            st.session_state.last_update = time.time()  # 인간 기준 시각 맞춤
            st.rerun()

    st.title("Cool Choi Amazons")
    st.caption("말을 퀸처럼 이동 → 도착칸에서 또 퀸처럼 화살(블록)을 발사해 빈칸을 막기. 상대가 더 이상 이동 못 하거나, 생각 시간 10분을 초과하면 패배.")

with right:
    diff = st.slider("난이도 (1 쉬움 ··· 15 매우 어려움)", 1, 15, st.session_state.get("difficulty",5))
    st.session_state.difficulty = diff
    c1,c2 = st.columns(2)
    if c1.button("새 게임", use_container_width=True):
        reset_game(); st.rerun()
    if c2.button("되돌리기(1수)", use_container_width=True):
        hist: List[Board] = st.session_state.get("hist", [])
        if hist: st.session_state.board = hist.pop()
        st.rerun()
st.session_state.setdefault("hist", [])

board: Board = st.session_state.board

# ================= 렌더/입력 =================
def cell_label(r:int,c:int)->str:
    """기본 말 + 강한 하이라이트(🟩 이동 / 🟥 사격) + 보조(◉ 선택 / ✓ 방금 이동 / ✳ 최근 블록)"""
    label = EMO_EMP
    cell = board[r][c]
    if cell==HUM: label = EMO_HUM
    elif cell==CPU: label = EMO_CPU
    elif cell==BLOCK: label = EMO_BLK

    if not st.session_state.game_over and st.session_state.turn==HUM:
        if st.session_state.phase=="move" and (r,c) in st.session_state.legal and cell==EMPTY:
            label = EMO_MOVE
        elif st.session_state.phase=="shoot" and (r,c) in st.session_state.legal and cell==EMPTY:
            label = EMO_SHOT

    if st.session_state.turn==HUM and st.session_state.sel_from==(r,c) and st.session_state.phase in ("move","shoot"):
        label += "◉"
    if st.session_state.highlight_to == (r,c):
        label += "✓"
    hm = st.session_state.last_human_move
    cm = st.session_state.last_cpu_move
    if hm and hm.to==(r,c): label += "✓"
    if cm and cm.to==(r,c): label += "✓"
    if st.session_state.last_shot_pos == (r,c) and cell==BLOCK:
        label += "✳"
    return label

def on_click(r:int,c:int):
    if st.session_state.game_over: return
    if st.session_state.turn!=HUM: return
    phase = st.session_state.phase

    # 시작 버튼을 누르지 않으면 클릭만 가능하고 시간은 흐르지 않음(원하는 동작)
    if phase=="select":
        if board[r][c]==HUM:
            st.session_state.sel_from = (r,c)
            st.session_state.legal = set(legal_dests_from(board,r,c))
            st.session_state.phase = "move"
            st.rerun()

    elif phase=="move":
        if (r,c) in st.session_state.legal:
            fr = st.session_state.sel_from
            nb = clone(board); nb[fr[0]][fr[1]] = EMPTY; nb[r][c] = HUM
            st.session_state.board = nb
            st.session_state.sel_to = (r,c)
            st.session_state.highlight_to = (r,c)
            st.session_state.legal = set(legal_shots_from(nb,r,c))
            st.session_state.phase = "shoot"
            st.rerun()

    elif phase=="shoot":
        if (r,c) in st.session_state.legal:
            st.session_state.board[r][c] = BLOCK
            st.session_state.last_shot_pos = (r,c)
            hm = Move(st.session_state.sel_from, st.session_state.sel_to, (r,c))
            st.session_state.last_human_move = hm
            st.session_state.hist.append(clone(board))
            check_flag_fall()
            st.session_state.turn = CPU
            st.session_state.phase = "select"
            st.session_state.sel_from = None
            st.session_state.sel_to = None
            st.session_state.legal = set()
            st.session_state.highlight_to = None
            st.rerun()

# 상단 캡션(승리 라벨 표시)
who = st.session_state.winner
caption_hum = f"{EMO_HUM}=플레이어" + (" (승리)" if who and "플레이어" in who else "")
caption_cpu = f"{EMO_CPU}=컴퓨터" + (" (승리)" if who and "컴퓨터" in who else "")
st.subheader("보드")
st.caption(f"{caption_hum}  {caption_cpu}  {EMO_BLK}=블록  ({EMO_MOVE} 이동 가능, {EMO_SHOT} 사격 가능 · ◉ 선택 · ✓ 방금 이동 · ✳ 최근 블록)")

# 보드 렌더 (정사각형 버튼)
st.markdown('<div class="board-grid">', unsafe_allow_html=True)
for r in range(SIZE):
    cols = st.columns(SIZE)
    for c in range(SIZE):
        label = cell_label(r,c)
        clickable = False
        if not st.session_state.game_over and st.session_state.turn==HUM:
            if st.session_state.phase=="select" and board[r][c]==HUM:
                clickable=True
            elif st.session_state.phase in ("move","shoot") and (r,c) in st.session_state.legal:
                clickable=True
        if cols[c].button(label, key=f"cell_{r}_{c}", disabled=not clickable):
            on_click(r,c)
st.markdown("</div>", unsafe_allow_html=True)

# ================= 엔드체크 & AI =================
def end_game(winner_label: str, human_win: bool):
    st.session_state.game_over = True
    st.session_state.winner = winner_label
    st.session_state.show_dialog = True
    if human_win:
        st.balloons()

def announce_and_set(who: str, ok=True):
    color = "#16a34a" if ok else "#dc2626"
    st.markdown(
        f"<div style='padding:8px;border-radius:8px;background:{'#ecfdf5' if ok else '#fef2f2'};color:{color}'><b>{who} 승리!</b></div>",
        unsafe_allow_html=True
    )

# 내 차례에서 더 이상 둘 곳이 없으면 컴퓨터 승리
if not st.session_state.game_over:
    if st.session_state.turn==HUM:
        if not has_any_move(board,HUM):
            announce_and_set("컴퓨터", ok=False)
            end_game("컴퓨터", human_win=False)
        check_flag_fall()

# 컴퓨터 차례 처리
if not st.session_state.game_over and st.session_state.turn==CPU:
    if not has_any_move(board,CPU):
        announce_and_set("플레이어", ok=True)
        end_game("플레이어", human_win=True)
    else:
        with st.spinner("컴퓨터 생각중..."):
            t0 = time.perf_counter()
            mv = ai_move(board, st.session_state.difficulty)
            t1 = time.perf_counter()
            # 타이머가 시작된 경우에만 CPU 시간 차감
            if st.session_state.timer_started:
                st.session_state.remain_cpu -= max(0.0, t1 - t0)
        check_flag_fall()
        if not st.session_state.game_over:
            if mv is None:
                announce_and_set("플레이어", ok=True)
                end_game("플레이어", human_win=True)
            else:
                st.session_state.board = apply_move(board, mv, CPU)
                st.session_state.last_cpu_move = mv
                st.session_state.last_shot_pos = mv.shot
                st.session_state.turn = HUM
                st.session_state.phase = "select"
                st.session_state.sel_from = None
                st.session_state.sel_to = None
                st.session_state.legal = set()
                st.session_state.last_update = time.time()  # 인간 기준 시각 재설정
        st.rerun()

# 팝업 열기
if st.session_state.show_dialog and st.session_state.winner:
    winner_dialog(st.session_state.winner)

# ---- 인간 턴 + 타이머 시작 후에만 1초 주기 자동 리프레시 ----
if not st.session_state.game_over and st.session_state.turn == HUM and st.session_state.timer_started:
    time.sleep(1.0)
    st.rerun()
