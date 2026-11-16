"""
Testes unitários para o módulo bandeja_win32 (substituto nativo do pystray).
"""

from PIL import Image
import pytest

import bandeja_win32


def test_menu_item_propriedades():
    item = bandeja_win32.MenuItem("Teste", action=lambda icon, it: None)
    assert item.text == "Teste"
    assert not item.checked
    assert item.enabled

    item_checked = bandeja_win32.MenuItem("Com Check", checked=True)
    assert item_checked.checked

    item_func = bandeja_win32.MenuItem("Funcional", checked=lambda it: True)
    assert item_func.checked


def test_menu_container():
    i1 = bandeja_win32.MenuItem("Item 1")
    i2 = bandeja_win32.MenuItem("Item 2")
    menu = bandeja_win32.Menu(i1, i2)

    assert len(menu.items) == 2
    assert list(menu) == [i1, i2]


def test_pil_para_hicon():
    img = Image.new("RGBA", (16, 16), color=(0, 120, 215, 255))
    hicon = bandeja_win32._pil_para_hicon(img)
    assert hicon != 0

    # Limpeza
    import ctypes
    ctypes.windll.user32.DestroyIcon(hicon)


def test_icon_instanciacao():
    img = Image.new("RGBA", (16, 16), color=(255, 0, 0, 255))
    menu = bandeja_win32.Menu(bandeja_win32.MenuItem("Item"))
    icon = bandeja_win32.Icon("teste_app", img, "Título Teste", menu)

    assert icon.name == "teste_app"
    assert icon.title == "Título Teste"
    assert icon.menu is menu

    # Atualização de título e ícone
    icon.title = "Novo Título"
    assert icon.title == "Novo Título"
