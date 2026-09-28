# -*- coding: utf-8 -*-
"""
俄罗斯方块 —— 本地窗口版（pygame）

双击本文件（或 run.bat）即可直接打开游戏窗口，无需浏览器。
游戏机制来自同一份 game_logic.py，与网页版完全一致：
开始/倒计时/进行/暂停（含退出按钮）/结束界面，
点击、下落、旋转、硬降、消除、奖励、惩罚、准备、开始、
拼接、爆炸、燃烧等音效（程序实时合成，无需音频文件），
灰烬方块的贴图（icon 文件夹），
按难度切换的背景音乐（bgm_and_sound_effect 文件夹），
以及开始界面的预设按钮和特殊方块勾选框。
"""
import array
import math
import os
import random
import pygame

from game_logic import (COLS, ROWS, PRESETS, SPECIAL_OPTIONS,
                        SPECIAL_TYPE, ASH_TYPE, FX_DURATION, TetrisGame)

PAD = 12          # 窗口内边距
GAP = 12          # 场地与侧栏的间距
SIDE_W = 150      # 侧栏宽度

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(BASE_DIR, 'icon')
BGM_DIR = os.path.join(BASE_DIR, 'bgm_and_sound_effect')
SFX_DIR = os.path.join(BASE_DIR, 'bgm_and_sound_effect')
BGM_VOLUME = 0.6  # BGM 音量（0~1，相对原曲音量的比例）

# ---------------- 音效合成（与网页版相同的一组音效） ----------------
SAMPLE_RATE = 22050


def _tone(freq_start, freq_end, ms, wave, vol):
    """生成一段声音的原始采样（16位单声道）；freq_end 表示滑向该频率"""
    n = int(SAMPLE_RATE * ms / 1000)
    data = array.array('h')
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = freq_start + ((freq_end - freq_start) * i / n if freq_end else 0)
        phase = 2 * math.pi * freq * t
        if wave == 'square':
            v = 1.0 if math.sin(phase) >= 0 else -1.0
        elif wave == 'saw':
            v = 2.0 * ((freq * t) % 1.0) - 1.0
        else:
            v = math.sin(phase)
        fade = (1 - i / n) ** 0.5            # 末端淡出，避免“啪”声
        data.append(int(v * vol * 32767 * fade))
    return data.tobytes()


def _noise(ms, vol, lp=0.2, decay=2.0, sputter=False):
    """生成一段噪声采样（16位单声道），用于爆炸/燃烧类音效。

    lp：一阶低通系数（0~1，越小越沉闷）；decay：能量衰减指数；
    sputter=True 时叠加低频起伏，模拟火焰噼啪的忽大忽小。
    """
    n = int(SAMPLE_RATE * ms / 1000)
    data = array.array('h')
    last = 0.0
    for i in range(n):
        t = i / n
        last = last * (1 - lp) + random.uniform(-1, 1) * lp
        env = (1 - t) ** decay
        if sputter:
            env *= 0.55 + 0.45 * math.sin(2 * math.pi * 13 * i / n)
        data.append(int(last * vol * 32767 * env))
    return data.tobytes()


def _load_wav(name, seconds=None):
    """从 bgm_and_sound_effect 文件夹加载 wav 音效，失败返回 None。

    seconds=None 播放全部时长；seconds=0.4 只取前 0.4 秒——先用
    SDL 解码整段并自动转换到混音器格式，再按帧数截取原始数据。
    """
    try:
        full = pygame.mixer.Sound(file=os.path.join(SFX_DIR, name))
        if seconds is None:
            return full
        rate, size, ch = pygame.mixer.get_init()
        bps = abs(size) // 8                  # 每样本字节数（-16 → 2）
        n = int(rate * seconds) * ch * bps
        return pygame.mixer.Sound(buffer=full.get_raw()[:n])
    except pygame.error:
        return None


class SoundBank:
    def __init__(self):
        self.sounds = {}
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(SAMPLE_RATE, -16, 1, 512)

            def snd(*args):
                return pygame.mixer.Sound(buffer=_tone(*args))

            # 灰烬爆炸与拼接音效直接使用音频文件；文件缺失时回退到合成音效
            file_sounds = {
                'land':   _load_wav('fall.wav', 0.4),    # 方块落定（前 0.4 秒）
                'bomb':   _load_wav('bomb.wav'),         # 炸弹爆炸（全部时长）
                'pepper': _load_wav('pepper.wav'),       # 辣椒燃烧（全部时长）
            }
            self.sounds = {
                'click':    snd(880, None, 70, 'square', 0.12),      # 按钮点击
                'fall':     snd(190, None, 50, 'sine', 0.04),        # 下落一格
                'rotate':   snd(660, 990, 60, 'square', 0.10),       # 旋转
                'harddrop': snd(520, 130, 140, 'saw', 0.14),         # 直接落底
                'clear':    pygame.mixer.Sound(buffer=(               # 消除整行
                    _tone(523, None, 100, 'square', 0.12)
                    + _tone(659, None, 100, 'square', 0.12)
                    + _tone(784, None, 180, 'square', 0.12))),
                'bonus':    pygame.mixer.Sound(buffer=(               # 简单特殊方块出现（清脆双音铃，与消行音效区分开）
                    _tone(1318, None, 270, 'sine', 0.24)
                    + _tone(1568, None, 660, 'sine', 0.24))),
                'penalty':  pygame.mixer.Sound(buffer=(               # 复杂特殊方块出现（惩罚）
                    _tone(220, 180, 480, 'saw', 0.24)
                    + _tone(160, 110, 840, 'saw', 0.24))),
                'ready':    pygame.mixer.Sound(buffer=(               # 倒计时“准备”（两声短音）
                    _tone(660, None, 100, 'sine', 0.15)
                    + _tone(660, None, 100, 'sine', 0.15))),
                'go':       snd(880, 1320, 1050, 'square', 0.28),     # 倒计时“开始！”（高音上滑长鸣）
                'land':     pygame.mixer.Sound(buffer=(               # 方块落定（拼接声·合成回退）
                    _tone(300, 150, 70, 'sine', 0.22)
                    + _tone(1300, None, 28, 'square', 0.05))),
                'bomb':     pygame.mixer.Sound(buffer=(               # 炸弹爆炸（合成回退）
                    _noise(520, 0.55, lp=0.08, decay=2.2)
                    + _tone(95, 38, 440, 'sine', 0.38))),
                'pepper':   pygame.mixer.Sound(buffer=(               # 辣椒燃烧（合成回退）
                    _noise(680, 0.42, lp=0.45, decay=1.6, sputter=True)
                    + _tone(230, 90, 620, 'saw', 0.12))),
            }
            # 用文件音效覆盖同名合成音效（覆盖前先合成，保证缺文件也能响）
            for k, v in file_sounds.items():
                if v is not None:
                    self.sounds[k] = v
        except pygame.error:
            self.sounds = {}                 # 没有音频设备时静默运行

    def play(self, name):
        snd = self.sounds.get(name)
        if snd:
            snd.play()


# ---------------- 绘图小工具 ----------------
def _rgb(color):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _light(rgb, k=1.45):
    return tuple(min(255, int(c * k)) for c in rgb)


def _dark(rgb, k=0.55):
    return tuple(int(c * k) for c in rgb)


def _load_font(px, bold=False):
    # 直接使用字体文件，避免 pygame.font.match_font 在部分 Windows 环境下崩溃
    names = ['msyhbd.ttc', 'msyh.ttc'] if bold else ['msyh.ttc', 'msyhbd.ttc']
    names += ['simhei.ttf', 'simsun.ttc']
    for name in names:
        p = 'C:/Windows/Fonts/' + name
        if os.path.exists(p):
            return pygame.font.Font(p, px)
    return pygame.font.Font(None, px)


class App:
    def __init__(self):
        self.game = TetrisGame()
        self.sounds = SoundBank()
        self.snap = self.game.snapshot()
        self.buttons = []            # 当前画面上的按钮 [(rect, 动作名)]
        # 开始界面控件状态
        self.difficulty = 1          # 选中的难度（1~20）
        self.dropdown_open = False   # 难度下拉框是否展开
        self.sp_checked = set()      # 勾选的特殊方块键名集合（SPECIAL_OPTIONS 的键）
        self.special_open = False    # “选择特殊方块”勾选框区是否展开
        self._diff_box = None        # 难度下拉框“值框”的位置（展开列表用）
        self._phase = None           # 上一帧的倒计时阶段（检测变化播准备/开始音效）
        self._tex_cache = {}         # 灰烬方块贴图缓存 {(类型, 尺寸): Surface}
        self._fx_cache = {}          # 爆炸特效贴图缓存 {名字: Surface}
        self._bgm_key = None         # 正在播放的 BGM 标记（None=未播放）
        info = pygame.display.Info()
        cell = max(16, min(30, int(info.current_h * 0.76 / ROWS)))
        self.resize(cell * COLS + GAP + SIDE_W + PAD * 2, cell * ROWS + PAD * 2)

    def resize(self, w, h):
        pygame.display.set_mode((w, h), pygame.RESIZABLE)
        self.win_w, self.win_h = w, h
        c = min((h - PAD * 2) / ROWS, (w - PAD * 2 - GAP - SIDE_W) / COLS)
        self.cell = max(10, int(c))
        self.board_xy = (PAD, PAD)
        self.panel_x = PAD + self.cell * COLS + GAP
        px = self.cell
        self.fonts = {
            'title': _load_font(int(px * 2.0), bold=True),
            'head':  _load_font(int(px * 1.4), bold=True),
            'num':   _load_font(int(px * 1.05), bold=True),
            'text':  _load_font(max(13, int(px * 0.72))),
            'small': _load_font(max(11, int(px * 0.58))),
            'tiny':  _load_font(max(9, int(px * 0.42))),
        }

    # ---------- 每帧更新：推进游戏逻辑并取回状态 ----------
    def update(self):
        self.game.tick()
        self.snap = self.game.snapshot()
        for ev in dict.fromkeys(self.snap['events']):   # 去重且保持顺序
            self.sounds.play(ev)
        ph = self.snap.get('phase')                     # 倒计时阶段变化时播音效
        if ph != self._phase:
            if ph in ('ready', 'go'):
                self.sounds.play(ph)
            self._phase = ph
        self._update_bgm()

    # ---------- 背景音乐 ----------
    def _update_bgm(self):
        """按游戏状态与难度切换背景音乐（只在变化时切换曲目）。

        * 主界面：循环 start_bgm.mp3；
        * 倒计时/进行/暂停：按难度循环对应曲目
          （1-5 relaxation / 6-9 experience / 10-14 challenge / 15-20 insanity）；
        * 游戏结束：立刻停止播放。
        """
        st = self.snap['state']
        if st == 'start':
            key = ('menu', 'start_bgm.mp3')
        elif st in ('countdown', 'playing', 'paused'):
            d = self.snap['difficulty']
            track = ('relaxation_bgm.mp3' if d <= 5 else
                     'experience_bgm.mp3' if d <= 9 else
                     'challenge_bgm.mp3' if d <= 14 else 'insanity_bgm.mp3')
            key = ('game', track)
        else:                          # over：立刻停止
            key = None
        if key == self._bgm_key:
            return
        self._bgm_key = key
        try:
            if key is None:
                pygame.mixer.music.stop()
            else:
                pygame.mixer.music.load(os.path.join(BGM_DIR, key[1]))
                pygame.mixer.music.set_volume(BGM_VOLUME)   # 音量降低为原来的 60%
                pygame.mixer.music.play(-1)     # 循环播放
        except pygame.error:
            pass                       # 没有音频设备或文件缺失时静默运行

    # ---------- 灰烬方块贴图 ----------
    def _texture(self, type_name, size):
        """取灰烬方块的贴图，缩放到格子大小（按尺寸缓存，贴图缺失返回 None）。"""
        key = (type_name, size)
        if key not in self._tex_cache:
            surf = None
            try:
                img = pygame.image.load(
                    os.path.join(ICON_DIR, ASH_TYPE[type_name]['tex'])).convert_alpha()
                w, h = img.get_size()
                k = size / max(w, h)          # 保持比例完整放入格子
                surf = pygame.transform.smoothscale(
                    img, (max(1, int(w * k)), max(1, int(h * k))))
            except (pygame.error, KeyError):
                surf = None                   # 贴图缺失时退回色块渲染
            self._tex_cache[key] = surf
        return self._tex_cache[key]

    def _fx_img(self, name):
        """取爆炸特效贴图原图（icon 文件夹，加载失败返回 None）。

        特效图自带白色不透明背景，加载后把接近白色的像素（每通道
        ≥ 235）的 alpha 置 0，只显示爆炸/火焰本身。
        """
        if name not in self._fx_cache:
            surf = None
            try:
                surf = pygame.image.load(
                    os.path.join(ICON_DIR, name + '.png')).convert_alpha()
                rgb = pygame.surfarray.pixels3d(surf)      # 直接引用像素缓冲
                alpha = pygame.surfarray.pixels_alpha(surf)
                white = ((rgb[:, :, 0] >= 235) & (rgb[:, :, 1] >= 235)
                         & (rgb[:, :, 2] >= 235))
                alpha[white] = 0                            # 白底 → 全透明
                del rgb, alpha      # 删除引用解锁 surface（修改已直接生效）
            except (pygame.error, ValueError):
                surf = None
            self._fx_cache[name] = surf
        return self._fx_cache[name]

    # ---------- 输入 ----------
    def handle_key(self, event):
        k = event.key
        st = self.snap['state']
        if st in ('start', 'over'):
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self._do('start')
            return
        if k == pygame.K_p:
            self._do('pause')
            return
        if st != 'playing':
            return
        if k == pygame.K_LEFT:
            self.game.move_start(-1)   # 按住 ←：持续左移（内部防键盘重复）
        elif k == pygame.K_RIGHT:
            self.game.move_start(1)    # 按住 →：持续右移
        elif k == pygame.K_UP:
            self.game.rotate()
        elif k == pygame.K_DOWN:
            self.game.soft_start()   # 按住 ↓：软降开始（内部防键盘重复）
        elif k == pygame.K_SPACE:
            self.game.hard_drop()
        elif k == pygame.K_r:
            self._do('start')
        elif k == pygame.K_e:
            self._do('exit')



    def handle_keyup(self, event):
        if event.key == pygame.K_DOWN:      # 松开 ↓：软降结束
            self.game.soft_stop()
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.game.move_stop()           # 松开 ←/→：横移结束

    def handle_click(self, event):
        if event.button != 1:
            return
        for rect, action in self.buttons:
            if rect.collidepoint(event.pos):
                self.sounds.play('click')       # 所有按钮共用点击音效
                self._do(action)
                return
        if self.dropdown_open:                  # 点了空白处：收起下拉框
            self.dropdown_open = False

    def _do(self, action):
        if action == 'start':
            self.game.start(difficulty=self.difficulty,
                            special_keys=sorted(self.sp_checked))
            self.dropdown_open = False
        elif action == 'exit':                  # 暂停/结束界面退出：返回主界面
            self.game.exit_to_menu()
        elif action == 'pause':
            self.game.toggle_pause()
        elif action == 'dropdown':              # 展开 / 收起难度下拉框
            self.dropdown_open = not self.dropdown_open
        elif action == 'special':               # 展开 / 收起特殊方块勾选框区
            self.special_open = not self.special_open
        elif action.startswith('toggle:'):      # 勾选 / 取消某个特殊方块
            key = action.split(':', 1)[1]
            if key in self.sp_checked:
                self.sp_checked.discard(key)
            else:
                self.sp_checked.add(key)
        elif action.startswith('preset:'):      # 预设：只设置难度与勾选，不开始游戏
            _name, diff, keys = PRESETS[int(action.split(':')[1])]
            self.difficulty = diff
            self.sp_checked = set(keys)
        elif action.startswith('diff:'):        # 选中某个难度
            self.difficulty = int(action.split(':')[1])
            self.dropdown_open = False

    # ---------- 渲染 ----------
    def draw_cell(self, surf, x, y, size, color, ghost=False, tex=None):
        if tex is not None:                 # 灰烬方块：居中贴图代替色块
            tw, th = tex.get_size()
            surf.blit(tex, (x + (size - tw) // 2, y + (size - th) // 2))
            return
        rgb = _rgb(color)
        if ghost:
            pygame.draw.rect(surf, rgb, (x + size // 7, y + size // 7,
                                         size * 5 // 7, size * 5 // 7),
                             max(1, size // 12), border_radius=2)
            return
        pygame.draw.rect(surf, rgb, (x, y, size, size), border_radius=3)
        b = max(2, size // 10)
        pygame.draw.rect(surf, _light(rgb), (x, y, size, b), border_radius=2)
        pygame.draw.rect(surf, _light(rgb), (x, y, b, size), border_radius=2)
        pygame.draw.rect(surf, _dark(rgb), (x, y + size - b, size, b), border_radius=2)
        pygame.draw.rect(surf, _dark(rgb), (x + size - b, y, b, size), border_radius=2)

    def render(self):
        s = self.snap
        surf = pygame.display.get_surface()
        surf.fill((12, 16, 34))
        bx, by = self.board_xy
        c = self.cell

        # 场地背景与网格
        pygame.draw.rect(surf, (13, 19, 38), (bx, by, COLS * c, ROWS * c), border_radius=6)
        grid = (30, 37, 60)
        for i in range(1, COLS):
            pygame.draw.line(surf, grid, (bx + i * c, by), (bx + i * c, by + ROWS * c))
        for j in range(1, ROWS):
            pygame.draw.line(surf, grid, (bx, by + j * c), (bx + COLS * c, by + j * c))

        # 已固定的方块
        for yy in range(ROWS):
            for xx in range(COLS):
                color = s['board'][yy][xx]
                if color:
                    self.draw_cell(surf, bx + xx * c, by + yy * c, c, color)

        # 幻影落点 + 当前方块（灰烬方块用贴图渲染）
        cur = s['cur']
        if cur and s['state'] != 'over':
            cur_tex = self._texture(cur['type'], c) if cur['type'] in ASH_TYPE else None
            if s['ghost'] > 0 and s['state'] == 'playing':
                for yy, row in enumerate(cur['shape']):
                    for xx, v in enumerate(row):
                        if v:
                            self.draw_cell(surf,
                                           bx + (cur['x'] + xx) * c,
                                           by + (cur['y'] + yy + s['ghost']) * c,
                                           c, cur['color'], ghost=True)
            for yy, row in enumerate(cur['shape']):
                for xx, v in enumerate(row):
                    if v and cur['y'] + yy >= 0:
                        self.draw_cell(surf, bx + (cur['x'] + xx) * c,
                                       by + (cur['y'] + yy) * c, c, cur['color'],
                                       tex=cur_tex)

        # 爆炸特效：贴图缩放到影响范围大小，保留期内线性渐隐
        for f in s['fx']:
            img = self._fx_img(f['img'])
            if img:
                rect = pygame.Rect(bx + f['x0'] * c, by + f['y0'] * c,
                                   (f['x1'] - f['x0'] + 1) * c,
                                   (f['y1'] - f['y0'] + 1) * c)
                frame = pygame.transform.smoothscale(img, rect.size)
                frame.set_alpha(max(0, int(255 * (1 - f['age'] / FX_DURATION))))
                surf.blit(frame, rect.topleft)

        # 场地边框
        pygame.draw.rect(surf, (60, 70, 105), (bx, by, COLS * c, ROWS * c), 2, border_radius=6)

        self.draw_side(s)
        if s['state'] != 'playing':
            self.draw_panel(s)
            if self.dropdown_open and s['state'] == 'start':
                self._draw_dropdown()   # 难度下拉列表画在界面最上层
        if s.get('phase'):              # 倒计时大字（准备 / 开始！）画在场地中央
            f = self.fonts['title']
            img = f.render('准备' if s['phase'] == 'ready' else '开始！', True,
                           (255, 215, 106) if s['phase'] == 'ready' else (140, 240, 165))
            surf.blit(img, (bx + COLS * c // 2 - img.get_width() // 2,
                            by + ROWS * c // 2 - img.get_height() // 2))

    def draw_side(self, s):
        surf = pygame.display.get_surface()
        c = self.cell
        x = self.panel_x
        width = self.win_w - x - PAD
        f_text = self.fonts['text']
        f_num = self.fonts['num']
        f_small = self.fonts['small']
        y = PAD

        for label, value in (('分数', s['score']), ('难度', s['difficulty']), ('消行', s['lines'])):
            h = f_text.get_height() + f_num.get_height() + 16
            r = pygame.Rect(x, y, width, h)
            pygame.draw.rect(surf, (26, 32, 56), r, border_radius=8)
            pygame.draw.rect(surf, (48, 56, 88), r, 1, border_radius=8)
            surf.blit(f_text.render(label, True, (159, 176, 216)), (x + 12, y + 6))
            surf.blit(f_num.render(str(value), True, (232, 236, 248)),
                      (x + 12, y + 6 + f_text.get_height()))
            y += h + 10

        # 下一个方块预览（形状超过 4×4 时自动把预览格子缩小，保证放得下）
        shape = s['next']['shape']
        grid = max(4, len(shape))
        cell2 = int(min(c * 0.8, (width - 24) / grid))
        nh = f_text.get_height() + cell2 * grid + 18
        r = pygame.Rect(x, y, width, nh)
        pygame.draw.rect(surf, (26, 32, 56), r, border_radius=8)
        pygame.draw.rect(surf, (48, 56, 88), r, 1, border_radius=8)
        img = f_text.render('下一个', True, (159, 176, 216))
        surf.blit(img, (x + (width - img.get_width()) // 2, y + 6))
        ox = x + (width - cell2 * grid) // 2 + (grid - len(shape[0])) * cell2 // 2
        oy = y + f_text.get_height() + 8 + (grid - len(shape)) * cell2 // 2
        next_tex = (self._texture(s['next']['type'], cell2)
                    if s['next']['type'] in ASH_TYPE else None)
        for yy, row in enumerate(shape):
            for xx, v in enumerate(row):
                if v:
                    self.draw_cell(surf, ox + xx * cell2, oy + yy * cell2, cell2,
                                   s['next']['color'], tex=next_tex)
        y += nh + 10

        # 操作说明
        for line in ('← →  移动', '↑ 旋转   ↓按住加速', '空格  直接落底', 'P  暂停 / 继续', 'R  重新开始', 'E  退出'):
            surf.blit(f_small.render(line, True, (184, 196, 226)), (x + 8, y))
            y += f_small.get_height() + 5

    def draw_panel(self, s):
        surf = pygame.display.get_surface()
        w, h = surf.get_size()
        st = s['state']
        ov = pygame.Surface((w, h), pygame.SRCALPHA)
        # 开始界面背景完全不透明，其余界面保持半透明遮罩
        ov.fill((8, 10, 22, 255 if st == 'start' else 190))
        surf.blit(ov, (0, 0))
        self.buttons = []
        cx = w // 2

        def text_center(y, txt, size_key, color):
            f = self.fonts[size_key]
            img = f.render(txt, True, color)
            surf.blit(img, (cx - img.get_width() // 2, y))
            return y + img.get_height()

        def button(y, label, action, primary=True, small=False):
            # small=True：小号按钮（常规字重），用于开始界面的主按钮与结束界面
            f = self.fonts['text'] if small else self.fonts['head']
            img = f.render(label, True, (255, 255, 255))
            bw = max(120, img.get_width() + (44 if small else 90))
            bh = (34 if self.cell > 20 else 28) if small else (52 if self.cell > 20 else 44)
            r = pygame.Rect(cx - bw // 2, y, bw, bh)
            hovered = r.collidepoint(pygame.mouse.get_pos())
            if primary:
                pygame.draw.rect(surf, (124, 118, 255) if hovered else (99, 102, 241),
                                 r, border_radius=bh // 2)
            else:
                pygame.draw.rect(surf, (58, 66, 100) if hovered else (40, 47, 76),
                                 r, border_radius=bh // 2)
                pygame.draw.rect(surf, (120, 132, 170), r, 2, border_radius=bh // 2)
            surf.blit(img, (r.centerx - img.get_width() // 2,
                            r.centery - img.get_height() // 2))
            self.buttons.append((r, action))
            return bh

        y = int(h * 0.06)                    # 标题贴近窗口顶部，控件依次上移
        if st == 'start':
            f_text = self.fonts['text']
            f_small = self.fonts['small']
            y = text_center(y, '俄罗斯方块', 'title', (96, 205, 255)) + 16
            y = text_center(y, '消除整行方块得分，难度越高下落越快', 'small', (184, 196, 226)) + 7
            y = text_center(y, '方向键移动与旋转，空格直接落底', 'small', (184, 196, 226)) + 26

            # —— 难度下拉框 ——
            lab = f_text.render('难度', True, (220, 226, 244))
            box_h = f_text.get_height() + 12
            box_w = 100
            total = lab.get_width() + 10 + box_w
            lx = cx - total // 2
            surf.blit(lab, (lx, y + (box_h - lab.get_height()) // 2))
            dbox = pygame.Rect(lx + lab.get_width() + 10, y, box_w, box_h)
            hovered = dbox.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surf, (58, 66, 100) if hovered else (40, 47, 76),
                             dbox, border_radius=6)
            pygame.draw.rect(surf, (120, 132, 170), dbox, 1, border_radius=6)
            val = f_text.render('%d ▼' % self.difficulty, True, (232, 236, 248))
            surf.blit(val, (dbox.x + 10, dbox.centery - val.get_height() // 2))
            self.buttons.append((dbox, 'dropdown'))
            self._diff_box = dbox
            y += box_h + 22

            # —— 开始游戏按钮（小号） ——
            y += button(y, '开始游戏', 'start', small=True) + 22

            # —— 预设选项按钮（点击只设置难度与勾选，不开始游戏；7 个排两行） ——
            bw = min(64, (w - 2 * PAD - 3 * 6) // 4)
            bh2 = f_small.get_height() + 10
            row2_w = 3 * bw + 2 * 6
            for i, (name, _diff, _keys) in enumerate(PRESETS):
                col, row = i % 4, i // 4
                if row == 0:
                    rx = (w - 4 * bw - 3 * 6) // 2 + col * (bw + 6)
                else:                        # 第二行 3 个居中
                    rx = (w - row2_w) // 2 + col * (bw + 6)
                r = pygame.Rect(rx, y + row * (bh2 + 6), bw, bh2)
                hovered = r.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surf, (58, 66, 100) if hovered else (40, 47, 76),
                                 r, border_radius=bh2 // 2)
                pygame.draw.rect(surf, (120, 132, 170), r, 1, border_radius=bh2 // 2)
                img = f_small.render(name, True, (232, 236, 248))
                surf.blit(img, (r.centerx - img.get_width() // 2,
                                r.centery - img.get_height() // 2))
                self.buttons.append((r, 'preset:%d' % i))
            y += ((len(PRESETS) + 3) // 4) * (bh2 + 6) + 10

            # —— “选择特殊方块”按钮：点击展开/收起下方勾选框区（小号） ——
            y += button(y, '选择特殊方块', 'special', primary=False, small=True) + 14

            # —— 特殊方块勾选框（两列排布，默认收起） ——
            if self.special_open:
                col_w = (w - 2 * PAD) // 2
                row_h = f_small.get_height() + 10
                for i, (key, label, names) in enumerate(SPECIAL_OPTIONS):
                    col, row = i % 2, i // 2
                    gx = PAD + 14 + col * col_w
                    img = f_small.render(label, True, (220, 226, 244))
                    cb = 14
                    cbr = pygame.Rect(gx, y + row * row_h +
                                      (img.get_height() - cb) // 2, cb, cb)
                    pygame.draw.rect(surf, (40, 47, 76), cbr, border_radius=4)
                    pygame.draw.rect(surf, (120, 132, 170), cbr, 1, border_radius=4)
                    if key in self.sp_checked:
                        # 简单方块（格子 < 4）金色，复杂方块殷红色，
                        # 灰烬方块用蓝色表示勾选
                        if names[0] in ASH_TYPE:
                            color = '#2563eb'
                        else:
                            cells = sum(sum(rr) for rr in SPECIAL_TYPE[names[0]]['shape'])
                            color = '#ffd700' if cells < 4 else '#8b0000'
                        pygame.draw.rect(surf, _rgb(color),
                                         cbr.inflate(-5, -5), border_radius=2)
                    surf.blit(img, (gx + cb + 7, y + row * row_h))
                    # 命中区加宽到整列，方便点击
                    self.buttons.append((pygame.Rect(gx - 6, y + row * row_h - 3,
                                                     col_w - 14, img.get_height() + 6),
                                         'toggle:' + key))

            # —— 右下角水印（仅开始界面显示，淡灰极小字两行） ——
            f_tiny = self.fonts['tiny']
            wm_y = h - 2 * f_tiny.get_height() - 10
            for i, line in enumerate(('本游戏为AI辅助生成，版权归飘逸小猪所有',
                                      '如有问题请联系邮箱1067958@163.com')):
                img = f_tiny.render(line, True, (95, 102, 124))
                surf.blit(img, (w - img.get_width() - 10,
                                wm_y + i * (f_tiny.get_height() + 2)))
        elif st == 'paused':
            y = text_center(y, '已暂停', 'head', (232, 236, 248)) + 16
            y = text_center(y, '按 P 键继续游戏', 'text', (184, 196, 226)) + 30
            button(y, '退出游戏', 'exit', primary=False)
        elif st == 'countdown':
            pass                             # 倒计时：只画遮罩，大字由 render() 绘制
        else:
            y = text_center(y, '游戏结束', 'head', (232, 236, 248)) + 16
            y = text_center(y, '得分 %d　消行 %d　难度 %d' % (s['score'], s['lines'], s['difficulty']),
                            'text', (255, 215, 106)) + 34
            # 两个小号按钮（不加粗），间距加大
            y += button(y, '再来一局', 'start', small=True) + 28
            button(y, '退出游戏', 'exit', primary=False, small=True)

    def _draw_dropdown(self):
        """画展开的难度下拉列表（1~20 两列排布，当前选中项高亮）。"""
        surf = pygame.display.get_surface()
        box = self._diff_box
        if not box:
            return
        f = self.fonts['text']
        item_h = f.get_height() + 8
        item_w = 70
        cols, rows, pad = 2, 10, 4
        w = cols * item_w + pad * (cols + 1)
        h = rows * item_h + pad * 2
        x = box.x
        y = box.bottom + 4
        if y + h > self.win_h:              # 底部放不下就往上弹
            y = box.top - h - 4
        pygame.draw.rect(surf, (30, 37, 60), (x, y, w, h), border_radius=6)
        pygame.draw.rect(surf, (120, 132, 170), (x, y, w, h), 1, border_radius=6)
        mouse = pygame.mouse.get_pos()
        for v in range(1, 21):
            col, row = (v - 1) // 10, (v - 1) % 10
            r = pygame.Rect(x + pad + col * (item_w + pad),
                            y + pad + row * item_h, item_w, item_h - 2)
            if v == self.difficulty:
                pygame.draw.rect(surf, (99, 102, 241), r, border_radius=4)
            elif r.collidepoint(mouse):
                pygame.draw.rect(surf, (58, 66, 100), r, border_radius=4)
            img = f.render(str(v), True,
                           (255, 255, 255) if v == self.difficulty else (220, 226, 244))
            surf.blit(img, (r.centerx - img.get_width() // 2,
                            r.centery - img.get_height() // 2))
            self.buttons.append((r, 'diff:%d' % v))


def _disable_ime():
    """把游戏窗口与输入法解绑（仅 Windows）。

    中文输入法在中文模式下会拦截 P/R/E 等字母键进入拼音组合：
    按键到不了游戏（暂停/重开/退出全部无效），组合期间方向键还被
    输入法征用去选候选词，直到按空格上屏才恢复——表现为游戏“卡住”。
    用 ImmAssociateContext(hwnd, None) 断开输入法后，
    所有按键无论输入法处于什么模式都会直达游戏窗口。
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        hwnd = pygame.display.get_wm_info().get('window')
        if hwnd:
            ctypes.windll.imm32.ImmAssociateContext(hwnd, None)
        pygame.key.stop_text_input()
    except Exception:
        pass                       # 解绑失败也不影响游戏运行


def main():
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
    pygame.init()
    pygame.key.set_repeat(230, 55)     # 按住方向键可连续移动（与网页版一致）
    pygame.display.set_caption('俄罗斯方块')

    global APP
    APP = app = App()
    _disable_ime()                     # 解绑输入法，防止中文模式吞掉 P/R/E 等按键
    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:      # 窗口大小变化时自适应
                app.resize(event.w, event.h)
            elif event.type == pygame.KEYDOWN:
                app.handle_key(event)
            elif event.type == pygame.KEYUP:            # 松开 ↓ 结束软降
                app.handle_keyup(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                app.handle_click(event)
        app.update()
        app.render()
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()


if __name__ == '__main__':
    main()
