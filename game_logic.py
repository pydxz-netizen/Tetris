# -*- coding: utf-8 -*-
"""
俄罗斯方块 —— 游戏逻辑（Python 部分）

与游戏机制有关的一切代码都在这里：方块定义、移动、旋转、碰撞、
锁定、消行、计分、难度与下落速度、特殊方块、预设、游戏状态
（开始/倒计时/进行/暂停/结束）。
网页版（server.py + surface.html + style.css）和
本地窗口版（window.py）共用这一份逻辑。

每个函数的作用都用函数开头的三引号说明（docstring）标明了。
"""
import random
import threading
import time

# ---------------- 基础常量与方块定义 ----------------
COLS = 10                     # 场地宽度（列数）
ROWS = 23                     # 场地高度（行数）
LINE_SCORE = 25               # 每消除一行的得分

# 开始游戏后的倒计时：先显示“准备”，再显示“开始！”，随后才正式下落
COUNTDOWN_READY = 1.2         # “准备”显示时长（秒）
COUNTDOWN_TOTAL = 2.2         # 倒计时总时长（秒）

# 七种普通方块的初始形状与颜色。
#
# 【想自己添加新方块？只需两步】
#   1. 在 TYPES 里照样式加一项（名字随意，不与现有的重复）；
#   2. 把新名字加进 NAMES 列表，它就会进入随机序列。
#   例如添加一个 3×3 的“十字”方块：
#       'X': {'color': '#e879f9', 'shape': [[0, 1, 0], [1, 1, 1], [0, 1, 0]]},
#       NAMES = ['I', 'O', 'T', 'S', 'Z', 'J', 'L', 'X']
#
# 【注意】
#   * shape 必须写成 n×n 的正方形矩阵，空位用 0 补——旋转是按方阵
#     计算的，行数和列数不相等会转错；
#   * 填 1 的格子数量不限，不必凑成 4 个（1 格、2 格、9 格都行）；
#   * 边长不能超过场地宽度 COLS（10），否则生成时放不下。
TYPES = {
    'I': {'color': '#22d3ee', 'shape': [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]]},
    'O': {'color': '#8a6607', 'shape': [[1, 1], [1, 1]]},
    'T': {'color': '#a855f7', 'shape': [[0, 1, 0], [1, 1, 1], [0, 0, 0]]},
    'S': {'color': '#22c55e', 'shape': [[0, 1, 1], [1, 1, 0], [0, 0, 0]]},
    'Z': {'color': '#ef4444', 'shape': [[1, 1, 0], [0, 1, 1], [0, 0, 0]]},
    'J': {'color': '#3b82f6', 'shape': [[1, 0, 0], [1, 1, 1], [0, 0, 0]]},
    'L': {'color': '#f97316', 'shape': [[0, 0, 1], [1, 1, 1], [0, 0, 0]]},
}
NAMES = ['I', 'O', 'T', 'S', 'Z', 'J', 'L']

# 特殊方块：普通模式不会出现，只在开始界面勾选了对应的勾选框后，
# 才会与普通方块等概率地进入随机抽选。
#   * 格子数 < 4 的算“简单方块”（增益），统一金色，出现时播奖励音效；
#   * 格子数 > 4 的算“复杂方块”（惩罚），统一殷红色，出现时播惩罚音效；
#   * 特殊方块的格子数不会等于 4。
# 添加新的特殊方块时，往 SPECIAL_TYPE 里加一项（shape 仍须是 n×n 方阵），
# 并把名字加进 SPECIAL_NAME，再往 SPECIAL_OPTIONS 里加一条勾选框选项即可。
SPECIAL_TYPE = {
    # ---- 简单方块（格子数 < 4，增益·金色） ----
    'S1':  {'color': '#facc15', 'shape': [[1]]},                              # 1×1 实心
    'S12': {'color': '#facc15', 'shape': [[1, 1], [0, 0]]},                   # 1×2 条
    'S13': {'color': '#facc15', 'shape': [[1, 1, 1], [0, 0, 0], [0, 0, 0]]},  # 1×3 条
    # ---- 复杂方块（格子数 > 4，惩罚·殷红） ----
    'S5':   {'color': '#8b0000', 'shape': [[1] * 5 for _ in range(5)]},       # 5×5 实心
    'S5C':  {'color': '#8b0000', 'shape': [[0, 0, 1, 0, 0], [0, 0, 1, 0, 0],
                                           [1, 1, 1, 1, 1], [0, 0, 1, 0, 0],
                                           [0, 0, 1, 0, 0]]},                 # 5×5 十字架
    'S5X':  {'color': '#8b0000', 'shape': [[1, 0, 0, 0, 1], [0, 1, 0, 1, 0],
                                           [0, 0, 1, 0, 0], [0, 1, 0, 1, 0],
                                           [1, 0, 0, 0, 1]]},                 # 5×5 叉
    'S5B1': {'color': '#8b0000', 'shape': [[1, 0, 0, 0, 0], [1, 0, 0, 0, 0],
                                           [1, 1, 1, 1, 1], [0, 0, 0, 0, 1],
                                           [0, 0, 0, 0, 1]]},                 # 5×5 弓形之一
    'S5B2': {'color': '#8b0000', 'shape': [[0, 0, 0, 0, 1], [0, 0, 0, 0, 1],
                                           [1, 1, 1, 1, 1], [1, 0, 0, 0, 0],
                                           [1, 0, 0, 0, 0]]},                 # 5×5 弓形之二
    'S5SP': {'color': '#8b0000', 'shape': [[1, 0, 0, 0, 1], [1, 1, 0, 1, 1],
                                           [0, 0, 1, 0, 0], [1, 1, 0, 1, 1],
                                           [1, 0, 0, 0, 1]]},                 # 5×5 蜘蛛
    'S4':   {'color': '#8b0000', 'shape': [[1] * 4 for _ in range(4)]},       # 4×4 实心
    'S4B':  {'color': '#8b0000', 'shape': [[1, 0, 0, 1], [1, 0, 0, 1],
                                           [1, 0, 0, 1], [1, 1, 1, 1]]},      # 4×4 碗
}
SPECIAL_NAME = ['S1', 'S12', 'S13', 'S5', 'S5C', 'S5X',
                'S5B1', 'S5B2', 'S5SP', 'S4', 'S4B']

# 【开始界面勾选框选项】(勾选框键名, 界面显示文字, 对应的特殊方块名列表)
# 开始界面把勾选的键名列表发给 start()；用“和”连接成一对的方块
# （如弓形的两种朝向）放在同一条里，勾选时一起出现、取消时一起消失。
SPECIAL_OPTIONS = [
    ('b1',   '掉落 1×1 方块',        ['S1']),
    ('b12',  '掉落 1×2 方块',        ['S12']),
    ('b13',  '掉落 1×3 方块',        ['S13']),
    ('b5',   '掉落 5×5 方块',        ['S5']),
    ('b5c',  '掉落 5×5 十字架方块',  ['S5C']),
    ('b5x',  '掉落 5×5 叉方块',      ['S5X']),
    ('b5b',  '掉落 5×5 弓形方块',    ['S5B1', 'S5B2']),
    ('b5sp', '掉落 5×5 蜘蛛方块',    ['S5SP']),
    ('b4',   '掉落 4×4 方块',        ['S4']),
    ('b4b',  '掉落 4×4 碗方块',      ['S4B']),
    # ---- 灰烬方块（界面用蓝色表示勾选；仅“魔鬼”预设预勾选） ----
    ('bomb',   '掉落炸弹方块',  ['BOMB']),
    ('pepper', '掉落辣椒方块',  ['PEPPER']),
]

# 灰烬方块：格子数固定为 1 的特殊方块，落定即“爆炸”——
#   * BOMB    炸弹方块：清除以落点为中心 5×5 范围，每清 1 格 +2 分
#             （自身也被清除但不计分），爆炸音效；
#   * PEPPER  辣椒方块：清除落点所在整行，每清 1 格 +3 分（自身不计分），
#             燃烧音效。
# 灰烬方块不进随机袋，按“方块序号”的概率出现（见 _take_from_bag），
# 且不能触发消行——即使落定时某行恰好排满，也只引爆自身效果。
# 'tex' 是方块贴图文件名（位于 icon 文件夹），界面渲染下落方块与
# 预览时用它代替色块。
ASH_TYPE = {
    'BOMB':   {'color': '#52525b', 'shape': [[1]], 'tex': 'bomb.png'},
    'PEPPER': {'color': '#dc2626', 'shape': [[1]], 'tex': 'pepper.png'},
}
BOMB_SCORE = 2      # 炸弹每清除一格的得分
PEPPER_SCORE = 2    # 辣椒每清除一格的得分（不含自身）
FX_DURATION = 0.8   # 灰烬方块爆炸特效图的保留时长（秒）

# 【预设选项】开始界面“预设”按钮：点击后只设置难度与勾选状态，不开始游戏。
# 格式：(预设名称, 难度, 勾选的 SPECIAL_OPTIONS 键名列表)。
# 想调整预设的难度或包含的方块，直接改这张表即可。
PRESETS = [
    ('新手', 2,  ['b1', 'b12', 'b13']),
    ('简单', 5,  ['b12', 'b13']),
    ('普通', 9,  ['b13', 'b4']),
    ('经典', 9,  []),
    ('困难', 12, ['b5']),
    ('专家', 16, ['b5', 'b4b', 'b4']),
    ('魔鬼', 12, ['b5', 'b5x', 'b5b', 'b4', 'b5c', 'b5sp', 'b4b', 'bomb', 'pepper']),
]


def _shape_table(name):
    """按方块名返回它的定义表（普通 TYPES / 特殊 SPECIAL_TYPE / 灰烬 ASH_TYPE）。"""
    if name in ASH_TYPE:
        return ASH_TYPE
    return SPECIAL_TYPE if name in SPECIAL_TYPE else TYPES


def rotate_cw(shape):
    """把 shape 顺时针旋转 90 度，返回全新的矩阵（不修改原形状）。

    只接受 n×n 的正方形矩阵——所有方块的 shape 都补成方阵，
    就是为了让这里能统一计算。
    """
    n = len(shape)
    return [[shape[n - 1 - j][i] for j in range(n)] for i in range(n)]


class Piece:
    """一个下落中的方块。

    属性：
        type  -- 方块名字（TYPES 或 SPECIAL_TYPE 的键），如 'T'；
        shape -- 当前形状（n×n 矩阵，由 0/1 组成），旋转时整体替换；
        x, y  -- 方块左上角在场地中的格子坐标（y=0 是最顶行）。
    """

    def __init__(self, type_name):
        """按类型生成方块：复制定义表里的初始形状，放在顶部水平居中。

        初始高度：最低一格与场地最顶行（y=0）对齐，因此形状上方的
        格子会伸出顶端（y<0）——属于正常现象，渲染时自动跳过，
        随着下落逐渐显现。
        """
        self.type = type_name
        table = _shape_table(type_name)
        self.shape = [row[:] for row in table[type_name]['shape']]
        self.x = (COLS - len(self.shape[0])) // 2
        self.y = -max(i for i, row in enumerate(self.shape) if any(row))


class TetrisGame:
    """俄罗斯方块的全部游戏机制。

    界面（网页版/窗口版）只做两件事：调用下面的操作方法
    （start/move/rotate/...），并定期用 snapshot() 取状态来显示。
    """

    def __init__(self):
        """创建游戏对象：准备好线程锁并初始化到主界面（start）状态。"""
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        """清空场地、分数等全部数据，回到主界面（start）状态。

        开始新游戏、暂停后退出返回主界面时都会调用它。
        """
        self.board = [[None] * COLS for _ in range(ROWS)]   # 场地：存颜色或 None
        self.score = 0
        self.lines = 0
        self.level = 1                 # 保留等级字段（升级逻辑保留，公式备用）
        self.difficulty = 1            # 难度 1~20，控制下落速度
        self.special_names = []        # 本局参与抽选的特殊方块名字列表
        self.state = 'start'          # start | countdown | playing | paused | over
        self.bag = []
        self.cur = None
        self._hard_count = 0          # 困难方块概率计数（取块前必须先归零）
        self._ash_count = 0           # 灰烬方块概率计数（取块前必须先归零）
        self._ash_force = False       # 灰烬被困难方块顶掉后，下一次必出的标记
        self.next_type = self._take_from_bag()
        self.events = []              # 待通知给界面的事件（主要用于音效）
        self.effects = []             # 进行中的爆炸特效（界面按贴图绘制）
        self._last_drop = time.monotonic()   # 正常重力下落的计时
        self._soft_holding = False    # 玩家是否正按住 ↓（软降持续加速）
        self._last_soft = time.monotonic()   # 软降专用计时
        self._move_holding = 0        # 玩家正按住的左右方向（-1 左 / 1 右 / 0 无）
        self._last_move = time.monotonic()   # 左右持续横移专用计时
        self._countdown_start = 0.0   # 倒计时开始时刻（进入 countdown 时设置）

    # ---------- 内部工具 ----------
    @staticmethod
    def _cells_of(name):
        """返回某个方块的格子数（shape 里 1 的个数）。"""
        return sum(sum(r) for r in _shape_table(name)[name]['shape'])

    def _take_from_bag(self):
        """取出下一个方块的类型（7-bag 随机算法的扩展版 + 概率方块）。

        普通方块与简单特殊方块（格子 ≤ 4）仍装进同一个袋子等概率
        轮流发；困难特殊方块（格子 > 4）与灰烬方块不进袋子，各自
        按“方块序号”的概率出现：
          * 困难方块：开始游戏后从第 1 个方块起计数；每掉落一个
            困难方块，计数重置为 0（掉落的这个记为第 0 个）；
            第 1~5 个：0%（必不出）；第 6 个：40%；第 7 个：80%；
            第 8 个起：100%（必出）——没掉落时概率逐个线性提升；
            命中时在本局启用的困难方块中等概率随机选一种。
          * 灰烬方块：计数规则相同（每个非灰烬方块都让概率增大），
            第 1~5 个：0%；第 6 个：15%；第 7 个：45%；第 8 个：98%；
            第 9 个起：100%；命中时在本局启用的两种灰烬方块中等
            概率随机选一种。
          * 灰烬方块的判定优先级低于困难方块：同一次抽选中两者都
            命中时发困难方块，灰烬方块顺延——在困难方块掉落的
            下一次必定掉落（_ash_force 标记）。
        简单特殊方块与普通方块没有这套规则，和原来相同。
        """
        hards = [n for n in self.special_names
                 if n not in ASH_TYPE and self._cells_of(n) > 4]
        ashs = [n for n in self.special_names if n in ASH_TYPE]
        self._hard_count += 1
        self._ash_count += 1
        hard_fired = False
        if hards:
            if self._hard_count >= 8:
                p = 1.0
            elif self._hard_count >= 6:
                p = 0.4 + 0.4 * (self._hard_count - 6)   # 第6个40%，第7个80%
            else:
                p = 0.0
            hard_fired = random.random() < p
        ash_fired = False
        if ashs:
            if self._ash_force:              # 上次被困难方块顶掉，这次必出
                ash_fired = True
            else:
                c = self._ash_count
                if c >= 9:
                    ap = 1.0
                elif c == 8:
                    ap = 0.98
                elif c == 7:
                    ap = 0.45
                elif c == 6:
                    ap = 0.15
                else:
                    ap = 0.0                 # 第 1~5 个必不出
                ash_fired = random.random() < ap   # 先判定，供“同时命中”检测
        if hard_fired:
            self._hard_count = 0    # 掉落后重置，此块记为新计数第 0 个
            if ash_fired:
                self._ash_force = True   # 同时命中：灰烬顺延到下一次必出
            return random.choice(hards)
        if ash_fired:
            self._ash_count = 0   # 掉落后重置，此块记为新计数第 0 个
            self._ash_force = False
            return random.choice(ashs)
        if not self.bag:
            # 袋子里装：全部普通方块 + 非困难的特殊方块（简单方块）；
            # 困难特殊方块与灰烬方块不进袋，走上面的序号概率。
            self.bag = list(NAMES) + [n for n in self.special_names
                                      if n not in ASH_TYPE
                                      and self._cells_of(n) <= 4]
            random.shuffle(self.bag)
        return self.bag.pop()

    def _collide(self, piece, dx=0, dy=0, shape=None):
        """碰撞检测：判断是否会撞墙、撞地或撞上已固定的方块。

        把 piece 按 (dx, dy) 偏移后的位置逐格检查（用 dx/dy 试探
        “移动过去会不会撞”，本身并不真的移动）；传入 shape 时
        用它代替原形状，用于“旋转过去会不会撞”的测试。
        返回 True 表示会碰撞，这个操作不能执行。
        """
        shape = shape if shape is not None else piece.shape
        for y in range(len(shape)):
            for x in range(len(shape[y])):
                if not shape[y][x]:
                    continue
                nx, ny = piece.x + x + dx, piece.y + y + dy
                if nx < 0 or nx >= COLS or ny >= ROWS:
                    return True       # 越界：撞左右墙或地面
                if ny >= 0 and self.board[ny][nx]:
                    return True       # 与已固定的方块重叠
        return False

    def _fire(self, event):
        """往事件队列记一条事件（如 'fall'、'clear'、'bonus'）。

        界面每次取状态时会拿到这些事件，据此播放对应音效。
        """
        self.events.append(event)
        if len(self.events) > 50:
            del self.events[:-50]

    def _spawn(self):
        """生成新的当前方块。

        把 next_type 的方块放到顶部中央成为 cur，再从随机袋
        取出新的 next_type；如果新方块一出生就碰撞，说明方块
        已经堆到顶，游戏结束（state='over'），并结算“场上残留
        加分”：场上每有一个已固定的格子加 1 分。
        若生成的是特殊方块，按简单/复杂发出 'bonus'/'penalty'
        事件（出现奖励/惩罚音效）；灰烬方块出现时播与简单方块
        相同的 'bonus' 音效。
        """
        self.cur = Piece(self.next_type)
        self.next_type = self._take_from_bag()
        if self._collide(self.cur, 0, 0):
            self.state = 'over'       # 新方块放不下，游戏结束
            # 结算：场上每剩一个固定格子加 1 分
            self.score += sum(1 for row in self.board for cell in row if cell)
            return
        if self.cur.type in SPECIAL_TYPE:
            cells = sum(sum(row) for row in self.cur.shape)
            self._fire('bonus' if cells < 4 else 'penalty')
        elif self.cur.type in ASH_TYPE:
            self._fire('bonus')       # 灰烬方块出现：与简单方块相同的音效

    def _lock_piece(self):
        """把当前方块的每个格子按其颜色写进场地数组，变成固定方块。"""
        table = _shape_table(self.cur.type)
        for y, row in enumerate(self.cur.shape):
            for x, v in enumerate(row):
                if v and self.cur.y + y >= 0:
                    self.board[self.cur.y + y][self.cur.x + x] = table[self.cur.type]['color']

    def _ash_explode(self):
        """灰烬方块（炸弹/辣椒）落定即爆炸，不触发消行。

        炸弹：清除以落点为中心 5×5 范围内已固定的格子，每清 1 格
        加 BOMB_SCORE（2）分——炸弹自身也被清除但不计分，随后发出
        'bomb' 事件（爆炸音效）。
        辣椒：清除落点所在行及其上一行、下一行（共三行）已固定的
        格子，每清 1 格加 PEPPER_SCORE（2）分——辣椒自身也被清除
        但不计分，随后发出 'pepper' 事件（燃烧音效）。
        两种爆炸都会登记特效（_add_fx），由界面绘制爆炸贴图。
        注意：爆炸清除不算消行（消行数不变、不发 'clear' 事件、
        不给消行分），即使爆炸后某行恰好被清空或排满也一样。
        """
        cx = self.cur.x
        cy = max(0, min(ROWS - 1, self.cur.y))
        if self.cur.type == 'BOMB':
            cleared = 0
            for y in range(max(0, cy - 2), min(ROWS, cy + 3)):
                for x in range(max(0, cx - 2), min(COLS, cx + 3)):
                    if x == cx and y == cy:
                        self.board[y][x] = None   # 炸弹自身也被清除，但不计分
                        continue
                    if self.board[y][x]:
                        self.board[y][x] = None
                        cleared += 1
            self.score += BOMB_SCORE * cleared
            self._fire('bomb')
            self._add_fx('explotion', cx - 2, cy - 2, cx + 2, cy + 2)
        else:                         # 'PEPPER'：清除所在行及上下各一行
            cleared = 0
            for y in range(max(0, cy - 1), min(ROWS, cy + 2)):
                for x in range(COLS):
                    if x == cx and y == cy:
                        self.board[y][x] = None   # 辣椒自身也被清除，但不计分
                        continue
                    if self.board[y][x]:
                        self.board[y][x] = None
                        cleared += 1
            self.score += PEPPER_SCORE * cleared
            self._fire('pepper')
            self._add_fx('blaze', 0, cy - 1, COLS - 1, cy + 1)

    def _add_fx(self, img, x0, y0, x1, y1):
        """登记一个爆炸特效：贴图名 + 覆盖的格子矩形 + 开始时刻。

        界面在特效保留期内（FX_DURATION 秒）把它缩放到矩形大小
        叠画在场上，超时后自动消失（见 snapshot 中的过滤）。
        """
        self.effects.append({'img': img,
                             'x0': max(0, x0), 'y0': max(0, y0),
                             'x1': min(COLS - 1, x1), 'y1': min(ROWS - 1, y1),
                             't': time.monotonic()})

    def _clear_lines(self):
        """检查并消除填满的行，同时结算分数和等级。

        从最底行往上扫描：整行都有方块就删除该行、顶部补一行空行
        （上面的方块整体下移）。每消除一行得 LINE_SCORE（25）分，
        与等级无关；每消 10 行升 1 级。有消除时发出 'clear' 事件
        （消除音效）。（等级仍会随消行增长，但不再控制下落速度和
        得分，公式保留备用。）
        """
        cleared = 0
        y = ROWS - 1
        while y >= 0:
            if all(self.board[y]):
                del self.board[y]
                self.board.insert(0, [None] * COLS)
                cleared += 1          # 当前行被上面移下来的行替换，需原位重查
            else:
                y -= 1
        if cleared:
            self.lines += cleared
            self.score += LINE_SCORE * cleared   # 每消除一行得 25 分
            self.level = self.lines // 10 + 1
            self._fire('clear')

    def _descend(self, soft=False):
        """当前方块向下移动一格；移不动则固定并结算、生成新方块。

        每次成功下移都发出 'fall' 事件（下落音效）。
        注意：软降不再加分，软降只是速度更快的下落方式。
        落定结算：灰烬方块落定即爆炸（见 _ash_explode，不发拼接
        音效）；其余方块固定后先消行再发出 'land' 事件（拼接音效）。
        """
        if not self._collide(self.cur, 0, 1):
            self.cur.y += 1
            self._fire('fall')        # 每下落一格播放一次下落音效
        else:
            self._lock_piece()
            if self.cur.type in ASH_TYPE:
                self._ash_explode()
            else:
                self._clear_lines()
                self._fire('land')    # 普通方块落定的拼接音效
            self._spawn()
        self._last_drop = time.monotonic()

    # ---------- 下落速度 ----------
    def normal_interval(self):
        """难度 1~20 的正常重力下落时间间隔（秒）。

        速度随难度线性递增：难度 1 时每秒 1.25 格（0.8 秒/格，
        ）；难度 20 时每秒 15 格（0.0666 秒/格，
        ）。速度线性递增，间隔 1/speed
        就呈反比例下降。
        """
        speed_start = 1.0 / 0.8       # 难度 1：每秒 1.25 格
        speed_end = 1.0 / 0.0666        # 难度 20：每秒 15 格
        speed = speed_start + (speed_end - speed_start) * (self.difficulty - 1) / 19.0
        return 1.0 / speed

    def soft_interval(self):
        """软降（按住 ↓）的下落时间间隔（秒）。

        规定 interval = min(100, 正常下落时间间隔/2) 毫秒。
        """
        return min(0.1, self.normal_interval() / 2)

    def level_interval(self):
        """【备用公式，当前未使用】按等级计算的下落间隔（毫秒转秒）。

        原等级控制速度机制的公式：interval = max(50, 800-(等级-1)×70)
        毫秒，等级越高越快。现在下落速度改由难度控制，这个公式保留，
        以后想恢复等级控速时可以换回它。
        """
        return max(50, 800 - (self.level - 1) * 70) / 1000.0

    # ---------- 界面可以调用的操作 ----------
    def start(self, difficulty=1, special_keys=None):
        """开始新游戏：按开始界面的设置清空数据，先进入倒计时状态。

        difficulty：难度 1~20（超出范围会收紧到边界），决定下落速度；
        special_keys：开始界面勾选的 SPECIAL_OPTIONS 键名列表
        （如 ['b1', 'b5b']），对应的特殊方块（含“和”连接的一对）
        会与普通方块等概率进入随机抽选；普通模式传空列表即可。
        倒计时（先“准备”后“开始！”）结束后 tick() 才会生成第一个
        方块并转入 playing 状态。
        """
        with self.lock:
            self.reset()
            self.difficulty = max(1, min(20, int(difficulty)))
            keys = set(special_keys or [])
            self.special_names = []
            for key, _label, names in SPECIAL_OPTIONS:
                if key in keys:
                    self.special_names.extend(names)
            self._hard_count = 0      # 游戏方块从 1 起算：next_type 即第 1 个
            self._ash_count = 0       # 灰烬方块计数同样从 1 起算
            self._ash_force = False
            self.next_type = self._take_from_bag()
            self._countdown_start = time.monotonic()
            self.state = 'countdown'  # 倒计时中：tick() 计满后转入 playing

    def toggle_pause(self):
        """暂停 / 继续切换：在 playing 和 paused 两个状态之间互转。"""
        with self.lock:
            if self.state == 'playing':
                self.state = 'paused'
            elif self.state == 'paused':
                self.state = 'playing'

    def exit_to_menu(self):
        """暂停界面点“退出游戏”时调用：清空进度，返回主界面（start）。"""
        with self.lock:
            self.reset()

    def move(self, dx):
        """把当前方块左右移动一格（dx=-1 左移，dx=1 右移）。

        撞墙或撞到其他方块则原地不动。
        """
        with self.lock:
            if self.state == 'playing' and self.cur and not self._collide(self.cur, dx, 0):
                self.cur.x += dx

    def move_start(self, dx):
        """按住 ←/→ 开始持续横移（dx=-1 左，dx=1 右），并立刻先移一格。

        内部有防重保护：同方向重复调用（系统键盘重复触发的多次
        keydown）不会多移格、也不会重置计时。持续横移的节奏由
        tick() 控制，与正常下落同速（normal_interval()，随难度变化）。
        """
        with self.lock:
            if self.state == 'playing' and self.cur and self._move_holding != dx:
                self._move_holding = dx
                if not self._collide(self.cur, dx, 0):
                    self.cur.x += dx     # 按下瞬间先移一格，去掉原停顿感
                self._last_move = time.monotonic()

    def move_stop(self):
        """松开 ←/→：结束持续横移。"""
        with self.lock:
            self._move_holding = 0

    def rotate(self):
        """把当前方块顺时针旋转 90 度（玩家按 ↑）。

        旋转后若被挡住，依次尝试向左右平移 1、2 格（踢墙），
        全部失败则放弃这次旋转。成功旋转时发出 'rotate' 事件。
        """
        with self.lock:
            if self.state != 'playing' or not self.cur:
                return
            rotated = rotate_cw(self.cur.shape)
            for kick in (0, -1, 1, -2, 2):    # 撞墙时尝试平移，让旋转成功
                if not self._collide(self.cur, kick, 0, rotated):
                    self.cur.shape = rotated
                    self.cur.x += kick
                    self._fire('rotate')
                    return

    def soft_start(self):
        """软降开始（玩家按下 ↓）：进入“按住持续加速”状态并立刻先落一格。

        内部有防重保护：软降已在进行时重复调用（系统键盘重复
        触发的多次 keydown）不会重置计时。
        """
        with self.lock:
            if self.state == 'playing' and self.cur and not self._soft_holding:
                self._soft_holding = True
                self._last_soft = time.monotonic() - self.soft_interval()

    def soft_stop(self):
        """软降结束（玩家松开 ↓）：恢复正常下落速度。"""
        with self.lock:
            self._soft_holding = False

    def hard_drop(self):
        """硬降（玩家按空格）：一口气落到最底。

        落底后固定、结算（灰烬方块爆炸 / 其余方块消行 + 拼接音效）、
        生成新方块，并发出 'harddrop' 事件（直接落底的特殊音效）。
        注意：硬降不再加分。
        """
        with self.lock:
            if self.state != 'playing' or not self.cur:
                return
            while not self._collide(self.cur, 0, 1):
                self.cur.y += 1
            self._lock_piece()
            if self.cur.type in ASH_TYPE:
                self._ash_explode()
            else:
                self._clear_lines()
                self._fire('land')    # 普通方块落定的拼接音效
            self._spawn()
            self._last_drop = time.monotonic()
            self._fire('harddrop')    # 直接落底播放特殊音效

    def tick(self):
        """由界面每帧调用一次：推进倒计时、持续横移与重力下落。

        * state='countdown'：倒计时计满（COUNTDOWN_TOTAL 秒）后转入
          playing 并生成第一个方块；
        * state='playing' 时三条计时通道：
            - 玩家按住 ←/→（_move_holding）时，按 normal_interval()
              的节拍持续横移（与正常下落同速）；
            - 玩家按住 ↓（软降中）时，按软降间隔 soft_interval()
              持续下移（间隔 = min(100, 正常间隔/2) 毫秒）；
            - 否则按正常间隔 normal_interval() 下移（由难度决定）。
        """
        with self.lock:
            now = time.monotonic()
            if self.state == 'countdown':
                if now - self._countdown_start >= COUNTDOWN_TOTAL:
                    self.state = 'playing'
                    self._last_drop = now
                    self._last_soft = now
                    self._last_move = now
                    self._spawn()
                return
            if self.state != 'playing' or not self.cur:
                return
            if self._move_holding and now - self._last_move >= self.normal_interval():
                self._last_move = now
                if not self._collide(self.cur, self._move_holding, 0):
                    self.cur.x += self._move_holding
            if self._soft_holding:
                if now - self._last_soft >= self.soft_interval():
                    self._last_soft = now
                    self._descend(soft=True)
            elif now - self._last_drop >= self.normal_interval():
                self._last_drop = now
                self._descend(soft=False)

    def snapshot(self, drain=True):
        """把当前游戏状态打包成字典，交给界面渲染。

        内容：state（界面状态）、phase（倒计时阶段：'ready'/'go'/
        None，界面据此显示“准备/开始！”大字并播音效）、board
        （场地颜色二维数组）、cur（当前方块：类型/形状/位置/颜色）、
        ghost（落点幻影的垂直距离）、next（下一个方块）、
        score/difficulty/lines（分数 难度 消行）、events（新产生的
        音效事件）。

        drain=True：取走并清空事件队列（界面每帧轮询时用）；
        drain=False：保留事件（网页版执行命令后的回包用它，
        事件留给下一次轮询去播）。
        """
        with self.lock:
            cur_view = None
            ghost = 0
            if self.cur:
                table = _shape_table(self.cur.type)
                cur_view = {'type': self.cur.type,
                            'shape': [row[:] for row in self.cur.shape],
                            'x': self.cur.x, 'y': self.cur.y,
                            'color': table[self.cur.type]['color']}
                if self.state == 'playing':
                    while not self._collide(self.cur, 0, ghost + 1):
                        ghost += 1
            nt = _shape_table(self.next_type)[self.next_type]
            phase = None
            if self.state == 'countdown':
                elapsed = time.monotonic() - self._countdown_start
                phase = 'ready' if elapsed < COUNTDOWN_READY else 'go'
            # 爆炸特效：只保留未过期的（超过 FX_DURATION 秒的自动移除）
            now = time.monotonic()
            self.effects = [e for e in self.effects if now - e['t'] < FX_DURATION]
            fx = [{'img': e['img'], 'x0': e['x0'], 'y0': e['y0'],
                   'x1': e['x1'], 'y1': e['y1'], 'age': now - e['t']}
                  for e in self.effects]
            data = {
                'state': self.state,
                'phase': phase,
                'board': [row[:] for row in self.board],
                'cur': cur_view,
                'ghost': ghost,
                'next': {'type': self.next_type,
                         'shape': [row[:] for row in nt['shape']],
                         'color': nt['color']},
                'score': self.score,
                'level': self.level,
                'difficulty': self.difficulty,
                'lines': self.lines,
                'events': self.events[:] if drain else [],
                'fx': fx,
            }
            if drain:
                self.events = []
            return data
