# -*- coding: utf-8 -*-
"""
俄罗斯方块 —— 网页版启动器（本地小服务器）

双击运行（或命令行 python server.py）会启动服务器并自动打开浏览器游戏窗口。
游戏机制全部在 game_logic.py 中，本文件只负责把界面与游戏逻辑连接起来。
玩完后关闭命令行窗口即可完全退出。
"""
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from game_logic import PRESETS, SPECIAL_OPTIONS, ASH_TYPE, TetrisGame

GAME = TetrisGame()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 网页可访问的静态资源文件夹：URL 前缀 -> 磁盘文件夹（只读，防目录穿越）
STATIC_DIRS = {
    '/icon/': ('icon', {'png': 'image/png', 'jpg': 'image/jpeg'}),
    '/bgm/': ('bgm_and_sound_effect', {'mp3': 'audio/mpeg', 'wav': 'audio/wav'}),
}

ACTIONS = {
    'pause': GAME.toggle_pause,
    'exit': GAME.exit_to_menu,
    'left': lambda: GAME.move(-1),          # 单步左移（保留备用）
    'right': lambda: GAME.move(1),          # 单步右移（保留备用）
    'leftstart': lambda: GAME.move_start(-1),   # 按住 ←：持续左移
    'rightstart': lambda: GAME.move_start(1),   # 按住 →：持续右移
    'movestop': GAME.move_stop,             # 松开 ←/→：停止横移
    'rotate': GAME.rotate,
    'softstart': GAME.soft_start,
    'softstop': GAME.soft_stop,
    'harddrop': GAME.hard_drop,
}


class GameHandler(BaseHTTPRequestHandler):
    def _send(self, body, ctype, code=200):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj):
        self._send(json.dumps(obj), 'application/json; charset=utf-8')

    def _serve_file(self, filename, ctype):
        try:
            with open(os.path.join(BASE_DIR, filename), 'rb') as f:
                self._send(f.read(), ctype)
        except OSError:
            self._send('界面文件不存在：请确保 surface.html 和 style.css 与 server.py 在同一个文件夹里',
                       'text/plain; charset=utf-8', 404)

    def do_GET(self):
        route = urlparse(self.path).path
        if route == '/api/state':
            GAME.tick()
            self._send_json(GAME.snapshot())
        elif route == '/api/config':
            # 开始界面的预设按钮与特殊方块勾选框选项（来自 game_logic.py）
            self._send_json({
                'presets': [{'name': n, 'difficulty': d, 'keys': ks}
                            for n, d, ks in PRESETS],
                'options': [{'key': k, 'label': lab,
                             'ash': bool(_n and _n[0] in ASH_TYPE)}
                            for k, lab, _n in SPECIAL_OPTIONS],
                # 灰烬方块的贴图文件（位于 icon 文件夹，网页据此预载）
                'ashTex': {n: info['tex'] for n, info in ASH_TYPE.items()},
            })
        elif route in ('/', '/index.html'):
            self._serve_file('surface.html', 'text/html; charset=utf-8')
        elif route == '/style.css':
            self._serve_file('style.css', 'text/css; charset=utf-8')
        else:
            for prefix, (folder, types) in STATIC_DIRS.items():
                if route.startswith(prefix):
                    name = os.path.basename(route[len(prefix):])   # 防目录穿越
                    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                    if ext in types:
                        self._serve_file(os.path.join(folder, name), types[ext])
                    break
            else:
                self._send('not found', 'text/plain', 404)

    def do_POST(self):
        if urlparse(self.path).path != '/api/command':
            self._send('not found', 'text/plain', 404)
            return
        length = int(self.headers.get('Content-Length') or 0)
        payload = {}
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
        except ValueError:
            pass
        action = payload.get('action', '')
        if action == 'start':
            # 开始游戏：带上开始界面选择的难度和勾选的特殊方块键名列表
            GAME.start(difficulty=payload.get('difficulty', 1),
                       special_keys=payload.get('keys') or [])
        else:
            handler = ACTIONS.get(action)
            if handler:
                handler()
        self._send_json(GAME.snapshot(drain=False))

    def log_message(self, fmt, *args):
        pass                        # 不打印访问日志，保持窗口干净


def main():
    server = None
    for port in range(8123, 8133):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', port), GameHandler)
            break
        except OSError:
            continue
    if server is None:
        print('启动失败：8123~8132 端口都被占用了。')
        return
    url = 'http://localhost:%d/' % server.server_address[1]
    print('俄罗斯方块（网页版）已启动：%s' % url)
    print('请在打开的游戏窗口中游玩；关闭本命令行窗口即退出游戏。')
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
