"""Standalone Windows desktop host, sharing Surface Studio's WebView2 approach."""
import ctypes
import logging
import os
import sys
import threading

import server
from single_instance import DesktopInstance

TITLE = 'workstudio'


class DesktopAPI:
    def __init__(self, library):
        self._window = None
        self._library = library
        self._maximized = False

    def minimize(self):
        self._window.minimize()

    def toggle_maximize(self):
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()

    def close(self):
        self._window.destroy()

    def window_state(self):
        return {'maximized': self._maximized}

    def bounds(self):
        w = self._window
        return {'x': w.x, 'y': w.y, 'width': w.width, 'height': w.height}

    def resize_bounds(self, x, y, width, height):
        if self._maximized:
            return
        self._window.resize(max(960, min(10000, int(width))), max(640, min(10000, int(height))))
        self._window.move(int(x), int(y))

    def _state_changed(self, maximized):
        self._maximized = maximized
        try:
            self._window.evaluate_js('window.workstudioWindowState && window.workstudioWindowState(%s)' % ('true' if maximized else 'false'))
        except Exception:
            pass

    def choose_folder(self):
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None

    def copy_file(self, ident, kind, number=0):
        path = self._library.file(ident, kind, int(number))
        from System import Action
        from System.Collections.Specialized import StringCollection
        from System.Windows.Forms import Clipboard
        def copy():
            files = StringCollection()
            files.Add(str(path))
            Clipboard.SetFileDropList(files)
        self._window.native.Invoke(Action(copy))
        return {'ok': True}


def main():
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AEStudio.Desktop.1')
    instance = DesktopInstance(name=r'Local\AEStudio.Desktop', title=TITLE)
    try:
        if not instance.primary:
            instance.activate()
            return
        import webview
        lib = server.Library()
        http = server.make_server(lib, 47842)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        api = DesktopAPI(lib)
        webview.settings['DRAG_REGION_DIRECT_TARGET_ONLY'] = True
        window = webview.create_window(TITLE, f'http://127.0.0.1:{http.server_port}', js_api=api,
                                      width=1540, height=960, min_size=(960, 640),
                                      frameless=True, easy_drag=False, resizable=True, shadow=True,
                                      background_color='#c6d2d5', text_select=True)
        api._window = window
        window.events.maximized += lambda: api._state_changed(True)
        window.events.restored += lambda: api._state_changed(False)
        lib.window = window
        stopped = threading.Event()
        window.events.closed += lambda: stopped.set()
        # Show the cached catalog immediately, then refresh in the background.
        try:
            if lib.config['sources']:
                lib.scan()
        except Exception as exc:
            lib.status['error'] = str(exc)
        def activate_loop():
            from System import Action
            from System.Windows.Forms import FormWindowState
            window.events.shown.wait()
            def activate():
                form = window.native
                form.Show()
                if form.WindowState == FormWindowState.Minimized:
                    form.WindowState = FormWindowState.Normal
                form.BringToFront()
                form.Activate()
            while not stopped.is_set():
                if instance.wait(300):
                    try:
                        window.native.Invoke(Action(activate))
                    except Exception:
                        if stopped.is_set():
                            break
        try:
            webview.start(activate_loop, gui='edgechromium', private_mode=False,
                          storage_path=str(lib.data/'webview-profile'))
        finally:
            stopped.set()
            http.shutdown()
            http.server_close()
    finally:
        instance.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        server.DATA.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=server.DATA/'error.log', level=logging.ERROR, encoding='utf-8')
        logging.exception('workstudio startup failed')
        ctypes.windll.user32.MessageBoxW(None, '启动失败，详情已保存到：\n'+str(server.DATA/'error.log'), 'workstudio', 16)
