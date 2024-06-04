import sys
import cv2
import numpy as np
import pyautogui
from pynput import keyboard
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import random
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices

# Диапазон смещения курсора от центра снежинки вниз
RAND_MIN = 5  # Мин пикселей
RAND_MAX = 10  # Макс пикселей

# Параметры захвата экрана (смещение вверх на 50 пикселей)
region = (900, 500, 370, 530)

# Диапазоны для зелёного цвета (кристаллы)
green_lower = np.array([45, 75, 75])
green_upper = np.array([75, 255, 255])

# Диапазоны для синего цвета (льдинки)
blue_lower = np.array([90, 50, 50])
blue_upper = np.array([130, 255, 255])

# Уникальные цвета бомбочки, извлеченные из изображения
bomb_colors = [
    [82, 82, 82], [97, 97, 97], [107, 107, 107], [112, 112, 112], 
    [132, 132, 132], [142, 142, 142], [152, 152, 152], [157, 157, 157],
    [167, 167, 167], [177, 177, 177], [186, 186, 186], [197, 197, 197],
    [207, 207, 207], [217, 217, 217], [227, 227, 227], [237, 237, 237],
    [247, 247, 247], [255, 255, 255]
]

# Минимальная и максимальная площадь контура для фильтрации
min_contour_area = 150  # Установите это значение в зависимости от ваших требований
max_contour_area = 1000

clicking_enabled = False
program_running = True
executor = ThreadPoolExecutor(max_workers=10)  # Создаем пул потоков

bomb_radius = 50  # Увеличенный радиус вокруг бомбочки, в котором не кликаем
bomb_positions = []

class MenuApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Matrix Clicker Menu')
        self.setGeometry(100, 100, 400, 250)
        self.setWindowIcon(QIcon('menu_icon.png'))  # Устанавливаем иконку для меню
        self.setStyleSheet("background-color: black; color: green;")

        # Заголовок
        self.title_label = QLabel('by Lncemep', self)
        self.title_label.setFont(QFont('SansSerif', 18))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("background-color: black; color: green;")

        # Статус программы
        self.status_label = QLabel('Offline', self)
        self.status_label.setFont(QFont('SansSerif', 16))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: red;")
        
        self.donate_btn = QPushButton('Donate', self)
        self.donate_btn.setFont(QFont('SansSerif', 14))
        self.donate_btn.setStyleSheet("background-color: black; color: green;")
        self.donate_btn.clicked.connect(self.open_donate_link)

        self.exit_btn = QPushButton('Exit', self)
        self.exit_btn.setFont(QFont('SansSerif', 14))
        self.exit_btn.setStyleSheet("background-color: black; color: green;")
        self.exit_btn.clicked.connect(self.exit_app)

        self.hint_label = QLabel('Press Right Ctrl to toggle state', self)
        self.hint_label.setFont(QFont('SansSerif', 12))
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet("color: green;")

        vbox = QVBoxLayout()
        vbox.addWidget(self.title_label)  # Добавляем заголовок в компоновку
        vbox.addStretch(1)
        vbox.addWidget(self.status_label)
        vbox.addWidget(self.donate_btn)
        vbox.addWidget(self.exit_btn)
        vbox.addWidget(self.hint_label)
        vbox.addStretch(1)

        self.setLayout(vbox)

    def update_status(self):
        if clicking_enabled:
            self.status_label.setText('Active')
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText('Offline')
            self.status_label.setStyleSheet("color: red;")

    def open_donate_link(self):
        QDesktopServices.openUrl(QUrl("https://t.me/mysten4"))

    def exit_app(self):
        global program_running
        program_running = False
        self.close()
        QApplication.instance().quit()

def create_bomb_mask(frame, colors):
    mask = np.zeros(frame.shape[:2], dtype="uint8")
    for color in colors:
        lower = np.array(color) - 10
        upper = np.array(color) + 10
        color_mask = cv2.inRange(frame, lower, upper)
        mask = cv2.bitwise_or(mask, color_mask)
    return mask

def process_frame(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Создаем маски для кристаллов и льдинок
    green_mask = cv2.inRange(hsv, green_lower, green_upper)
    blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
    combined_mask = green_mask + blue_mask
    
    contours, hierarchy = cv2.findContours(combined_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Фильтруем контуры по площади и убираем вложенные контуры
    filtered_contours = []
    for i, cnt in enumerate(contours):
        if min_contour_area <= cv2.contourArea(cnt) <= max_contour_area and hierarchy[0][i][3] == -1:  # Только верхние контуры
            filtered_contours.append(cnt)
    
    # Добавляем бомбочки в список бомб
    bomb_mask = create_bomb_mask(frame, bomb_colors)
    bomb_contours, _ = cv2.findContours(bomb_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    bomb_positions.clear()
    for cnt in bomb_contours:
        (x, y, w, h) = cv2.boundingRect(cnt)
        center_x = x + w // 2
        center_y = y + h // 2
        bomb_positions.append((center_x, center_y))
    
    return filtered_contours

def click_on_position(screen_x, screen_y):
    global clicking_enabled
    if clicking_enabled:
        pyautogui.click(screen_x, screen_y + random.randint(RAND_MIN, RAND_MAX))

def click_element_contours(contours):
    global clicking_enabled
    for cnt in contours:
        if not clicking_enabled:
            break  # Прекращаем обработку контуров, если клики отключены
        (x, y, w, h) = cv2.boundingRect(cnt)
        center_x = x + w // 2
        center_y = y + h // 2
        screen_x = region[0] + center_x
        screen_y = region[1] + center_y
        
        # Проверяем на наличие бомбочек в радиусе
        too_close_to_bomb = any((abs(center_x - bx) <= bomb_radius and abs(center_y - by) <= bomb_radius) for bx, by in bomb_positions)
        
        if not too_close_to_bomb:
            executor.submit(click_on_position, screen_x, screen_y)  # Асинхронный клик

def capture_and_process():
    global program_running
    while program_running:
        # Захват экрана
        screenshot = pyautogui.screenshot(region=region)
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)  # Преобразование в цветовое пространство BGR для OpenCV

        contours = process_frame(frame)

        # Удаляем темно-зеленый цвет
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        dark_green_mask = cv2.inRange(hsv_frame, green_lower, green_upper)
        frame[dark_green_mask > 0] = (0, 0, 0)  # Заменяем темно-зеленый цвет на черный

        # Рисуем контуры на кадре
        cv2.drawContours(frame, contours, -1, (0, 0, 255), 2)
        # Рисуем бомбочки на кадре
        for bx, by in bomb_positions:
            cv2.circle(frame, (bx, by), bomb_radius, (0, 0, 255), 2)
        
        # Для визуализации захваченной области с контурами
        cv2.imshow("Captured Region", frame)
        cv2.waitKey(1)  # Обновляем изображение
        time.sleep(0.02)
        if clicking_enabled:
            click_element_contours(contours)
    cv2.destroyAllWindows()
    print("Capture and processing thread terminated")

def on_press(key):
    global clicking_enabled
    if key == keyboard.Key.ctrl_r:  # Если нажата правая клавиша Ctrl
        clicking_enabled = not clicking_enabled  # Переключаем состояние кликера
        menu_app.update_status()  # Обновляем статус в UI

if __name__ == '__main__':
    # Запускаем слушатель клавиатуры в отдельном потоке
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    app = QApplication(sys.argv)

    # Создаем и отображаем меню
    menu_app = MenuApp()
    menu_app.show()

    # Запускаем поток захвата и обработки
    capture_thread = threading.Thread(target=capture_and_process)
    capture_thread.start()

    sys.exit(app.exec_())
