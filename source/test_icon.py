#!/usr/bin/env python3
# Тестовый скрипт для проверки иконки

import sys
from PySide6 import QtCore, QtGui, QtWidgets

class IconTestWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Тест иконки")
        self.resize(300, 200)
        
        # Попытка установить иконку
        try:
            import resources_rc
            self.setWindowIcon(QtGui.QIcon(":/icon2.ico"))
            print("Иконка загружена из ресурсов")
        except ImportError:
            print("Модуль ресурсов не найден")
        except Exception as e:
            print(f"Ошибка загрузки иконки из ресурсов: {e}")
            
            # Попытка загрузить из файла
            import os
            icon_path = "icon2.ico"
            if os.path.exists(icon_path):
                self.setWindowIcon(QtGui.QIcon(icon_path))
                print("Иконка загружена из файла")
            else:
                print("Файл иконки не найден")

def main():
    app = QtWidgets.QApplication(sys.argv)
    
    # Попытка установить иконку приложения
    try:
        import resources_rc
        app.setWindowIcon(QtGui.QIcon(":/icon2.ico"))
        print("Иконка приложения загружена из ресурсов")
    except ImportError:
        print("Модуль ресурсов не найден для приложения")
    except Exception as e:
        print(f"Ошибка загрузки иконки приложения из ресурсов: {e}")
        
        # Попытка загрузить из файла
        import os
        icon_path = "icon2.ico"
        if os.path.exists(icon_path):
            app.setWindowIcon(QtGui.QIcon(icon_path))
            print("Иконка приложения загружена из файла")
        else:
            print("Файл иконки не найден для приложения")
    
    window = IconTestWindow()
    window.show()
    
    print("Тестовое окно открыто. Проверьте наличие иконки.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()