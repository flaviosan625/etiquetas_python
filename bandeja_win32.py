"""
bandeja_win32.py — Implementação nativa de ícone de bandeja (System Tray) para Windows.

Substituto 100% livre de licenças restritivas (elimina o pystray / LGPLv3).
Utiliza a API nativa do Windows (Shell_NotifyIconW, Win32 Window Messages) via pywin32 e ctypes.
Licença: MIT / Permissiva (compatível com produto comercial fechado).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import io
import threading
from typing import Any, Callable, List, Optional, Union

try:
    import win32api
    import win32con
    import win32gui
    PYWIN32_DISPONIVEL = True
except ImportError:
    PYWIN32_DISPONIVEL = False

from PIL import Image


WM_TRAY_CALLBACK = (win32con.WM_USER + 1024) if PYWIN32_DISPONIVEL else 1124


def _pil_para_hicon(img: Image.Image) -> int:
    """Converte uma imagem PIL.Image em um handle HICON do Windows via PNG em memória."""
    buf = io.BytesIO()
    # Converte para RGBA se necessário
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img.save(buf, format="PNG")
    dados = buf.getvalue()

    hicon = ctypes.windll.user32.CreateIconFromResourceEx(
        dados,
        len(dados),
        1,           # fIcon = TRUE
        0x00030000,  # dwVersion = 0x00030000
        img.width,
        img.height,
        0,           # LR_DEFAULTCOLOR
    )
    return hicon


class MenuItem:
    """Representa um item no menu de contexto da bandeja."""

    def __init__(
        self,
        text: str,
        action: Optional[Callable[[Any, "MenuItem"], None]] = None,
        checked: Optional[Union[bool, Callable[["MenuItem"], bool]]] = None,
        enabled: bool = True,
        default: bool = False,
    ):
        self.text = text
        self.action = action
        self._checked = checked
        self.enabled = enabled
        self.default = default

    @property
    def checked(self) -> bool:
        if callable(self._checked):
            try:
                return bool(self._checked(self))
            except Exception:
                return False
        return bool(self._checked)


class Menu:
    """Contêiner de itens de menu."""

    def __init__(self, *items: MenuItem):
        self.items = list(items)

    def __iter__(self):
        return iter(self.items)


class Icon:
    """
    Controlador do ícone de bandeja do sistema (System Tray).
    Compatível com a API de interface do pystray.
    """

    _class_registered = False
    _class_atom = 0
    _class_name = "PrintFlow_TrayIcon_Window"

    def __init__(
        self,
        name: str,
        icon: Optional[Image.Image] = None,
        title: str = "",
        menu: Optional[Menu] = None,
    ):
        self.name = name
        self._icon_img = icon
        self._title = title
        self.menu = menu
        self.hwnd: Optional[int] = None
        self._hicon: Optional[int] = None
        self._thread_loop: Optional[threading.Thread] = None
        self._executando = False
        self._lock = threading.Lock()
        self._command_map = {}  # id_comando -> MenuItem

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str):
        self._title = str(value)
        self._atualizar_nid()

    @property
    def icon(self) -> Optional[Image.Image]:
        return self._icon_img

    @icon.setter
    def icon(self, value: Image.Image):
        with self._lock:
            self._icon_img = value
            velho_hicon = self._hicon
            if value is not None:
                self._hicon = _pil_para_hicon(value)
            else:
                self._hicon = None

            self._atualizar_nid()

            if velho_hicon:
                try:
                    ctypes.windll.user32.DestroyIcon(velho_hicon)
                except Exception:
                    pass

    def update_menu(self):
        """Notifica atualização do menu (compatibilidade com pystray)."""
        pass

    def _registrar_classe(self):
        if not Icon._class_registered:
            wc = win32gui.WNDCLASS()
            wc.hInstance = win32api.GetModuleHandle(None)
            wc.lpszClassName = Icon._class_name
            wc.lpfnWndProc = self._wnd_proc
            Icon._class_atom = win32gui.RegisterClass(wc)
            Icon._class_registered = True

    def _criar_janela(self):
        self._registrar_classe()
        self.hwnd = win32gui.CreateWindowEx(
            0,
            Icon._class_name,
            self.name,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            win32api.GetModuleHandle(None),
            None,
        )

    def _atualizar_nid(self, adicionar: bool = False):
        if not self.hwnd or not self._hicon:
            return

        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        tooltip = (self._title or self.name)[:127]

        nid = (
            self.hwnd,
            0,
            flags,
            WM_TRAY_CALLBACK,
            self._hicon,
            tooltip,
        )

        acao = win32gui.NIM_ADD if adicionar else win32gui.NIM_MODIFY
        try:
            win32gui.Shell_NotifyIcon(acao, nid)
        except Exception:
            pass

    def _remover_nid(self):
        if self.hwnd:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
            except Exception:
                pass

    def _exibir_menu_popup(self):
        if not self.menu or not self.hwnd:
            return

        hmenu = win32gui.CreatePopupMenu()
        self._command_map.clear()
        base_id = 1000

        try:
            for idx, item in enumerate(self.menu.items):
                cmd_id = base_id + idx
                self._command_map[cmd_id] = item

                flags = win32con.MF_STRING
                if not item.enabled:
                    flags |= win32con.MF_GRAYED
                if item.checked:
                    flags |= win32con.MF_CHECKED
                if item.default:
                    flags |= win32con.MF_DEFAULT

                win32gui.AppendMenu(hmenu, flags, cmd_id, item.text)

            pos_x, pos_y = win32gui.GetCursorPos()
            win32gui.SetForegroundWindow(self.hwnd)
            win32gui.TrackPopupMenu(
                hmenu,
                win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON,
                pos_x,
                pos_y,
                0,
                self.hwnd,
                None,
            )
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        finally:
            win32gui.DestroyMenu(hmenu)

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int):
        if msg == WM_TRAY_CALLBACK:
            # Clique com botão direito ou esquerdo abre o menu de contexto
            if lparam in (win32con.WM_RBUTTONUP, win32con.WM_LBUTTONUP):
                self._exibir_menu_popup()
            return 0

        elif msg == win32con.WM_COMMAND:
            cmd_id = win32api.LOWORD(wparam)
            item = self._command_map.get(cmd_id)
            if item and item.action:
                try:
                    item.action(self, item)
                except Exception:
                    pass
            return 0

        elif msg == win32con.WM_DESTROY:
            self._remover_nid()
            return 0

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def run(self, setup: Optional[Callable[["Icon"], None]] = None):
        """Inicia a execução do loop de mensagens do ícone da bandeja."""
        if not PYWIN32_DISPONIVEL:
            raise RuntimeError("pywin32 é necessário para o funcionamento da bandeja no Windows.")

        self._criar_janela()
        if self._icon_img:
            self._hicon = _pil_para_hicon(self._icon_img)
        self._atualizar_nid(adicionar=True)
        self._executando = True

        if setup:
            threading.Thread(target=setup, args=(self,), daemon=True).start()

        # Loop de mensagens do Windows
        win32gui.PumpMessages()

    def stop(self):
        """Para o ícone da bandeja e destrói os recursos."""
        self._executando = False
        if self.hwnd:
            self._remover_nid()
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_DESTROY, 0, 0)
                win32gui.PostQuitMessage(0)
            except Exception:
                pass
            self.hwnd = None

        if self._hicon:
            try:
                ctypes.windll.user32.DestroyIcon(self._hicon)
            except Exception:
                pass
            self._hicon = None
