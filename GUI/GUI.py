#!/usr/bin/python
# -*- coding: UTF-8 -*-
# File name   : GUI.py
# Description : RaspTank desktop client: video, robot health, prompt box
# Website     : www.adeept.com
# Author      : William
# Date        : 2018/08/22
#
import json
import os
import threading as thread
import time
import tkinter as tk
import urllib.request
from socket import *

import cv2
import numpy as np
from websockets.sync.client import connect as ws_connect

DEFAULT_PORT = int(os.environ.get('WEB_PORT', 8888))  # server/webserver /prompt
INFO_PORT = 2256                                     # CPU/RAM feed from the robot
VIDEO_PORT = int(os.environ.get('VIDEO_PORT', 5000))  # MJPEG feed from server/app.py

BUFSIZ = 1024
INFO_INTERVAL = 3         # seconds between CPU/RAM polls
ip_stu = 1          # 1 = disconnected, 0 = connected
frame_num = 0
fps = 0
ws = None
ws_lock = thread.Lock()   # the websockets sync client is not safe for concurrent send/recv

########>>>>>VIDEO<<<<<########

latest_frame = None
video_started = False


def mjpeg_frames(url):
    """Yield JPEG bytes from a multipart/x-mixed-replace stream."""
    stream = urllib.request.urlopen(url, timeout=10)
    buf = b''
    while True:
        chunk = stream.read(4096)
        if not chunk:
            return
        buf += chunk
        while True:
            start = buf.find(b'\xff\xd8')
            end = buf.find(b'\xff\xd9', start + 2) if start != -1 else -1
            if start == -1 or end == -1:
                break
            yield buf[start:end + 2]
            buf = buf[end + 2:]


def video_thread():
    """Pull the MJPEG feed that server/app.py serves on /video_feed."""
    global latest_frame
    url = 'http://%s:%d/video_feed' % (robot_ip(), VIDEO_PORT)
    while True:
        try:
            for jpeg in mjpeg_frames(url):
                latest_frame = jpeg
        except Exception as exc:
            print('Video stream failed: %s' % exc)
            time.sleep(1)


def get_FPS():
    global frame_num, fps
    while 1:
        time.sleep(1)
        fps = frame_num
        frame_num = 0


def video_tick():
    """Draw the newest frame, then reschedule.

    Must run on the Tk main thread: cv2.imshow raises
    "Unknown C++ exception from OpenCV code" when called from a worker
    thread on macOS.
    """
    global frame_num
    if video_started:
        frame = latest_frame
        if frame is not None:
            npimg = np.frombuffer(frame, dtype=np.uint8)
            source = cv2.imdecode(npimg, 1)
            if source is not None:
                cv2.putText(source, ('PC FPS: %s' % fps), (40, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                try:
                    cv2.putText(source, ('CPU Temperature: %s' % CPU_TEP), (370, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 255, 128), 1, cv2.LINE_AA)
                    cv2.putText(source, ('CPU Usage: %s' % CPU_USE), (370, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 255, 128), 1, cv2.LINE_AA)
                    cv2.putText(source, ('RAM Usage: %s' % RAM_USE), (370, 410), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 255, 128), 1, cv2.LINE_AA)
                except NameError:
                    pass
                cv2.imshow("Stream", source)
                frame_num += 1
                cv2.waitKey(1)
    root.after(15, video_tick)


def start_video():
    global video_started
    if video_started:
        return
    video_started = True
    thread.Thread(target=get_FPS, daemon=True).start()
    thread.Thread(target=video_thread, daemon=True).start()

########>>>>>VIDEO<<<<<########


def replace_num(initial, new_num):   #Call this function to replace data in '.txt' file
    newline = ""
    str_num = str(new_num)
    with open("IP.txt", "r") as f:
        for line in f.readlines():
            if line.find(initial) == 0:
                line = initial + "%s" % (str_num)
            newline += line
    with open("IP.txt", "w") as f:
        f.writelines(newline)


def num_import(initial):            #Call this function to import data from '.txt' file
    with open("IP.txt") as f:
        for line in f.readlines():
            if line.find(initial) == 0:
                r = line
    begin = len(list(initial))
    return r[begin:]


def set_health(temp, cpu, ram):
    global CPU_TEP, CPU_USE, RAM_USE
    CPU_TEP, CPU_USE, RAM_USE = temp, cpu, ram
    CPU_TEP_lab.config(text='CPU Temp: %s\u2103' % CPU_TEP)
    CPU_USE_lab.config(text='CPU Usage: %s' % CPU_USE)
    RAM_lab.config(text='RAM Usage: %s' % RAM_USE)


def get_info_once():
    """Ask the robot for [cpu_temp, cpu_use, ram_use] over the existing WebSocket."""
    with ws_lock:
        ws.send('get_info')
        payload = json.loads(ws.recv(timeout=5))
    data = payload.get('data')
    if not data or len(data) < 3:
        raise ValueError('unexpected get_info reply: %r' % payload)
    return data[0], data[1], data[2]


def Info_receive():
    """Poll robot health over the WebSocket. The old 2256 push channel is dead:
    webServer.py never dials back to the PC, it only answers 'get_info'."""
    while ip_stu == 0 and ws is not None:
        try:
            set_health(*get_info_once())
        except Exception as exc:
            print('Info poll failed: %s' % exc)
            break
        time.sleep(INFO_INTERVAL)


def Info_push_listener():
    """Optional legacy fallback, used only when the robot runs with INFO_PUSH=1."""
    InfoSock = socket(AF_INET, SOCK_STREAM)
    InfoSock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    try:
        InfoSock.bind('', INFO_PORT)
    except OSError as exc:
        print('Info push listener not started (%s)' % exc)
        return
    InfoSock.listen(5)
    while ip_stu == 0:
        try:
            conn, addr = InfoSock.accept()
            while 1:
                data = conn.recv(BUFSIZ).decode().split()
                if len(data) >= 3:
                    set_health(data[0], data[1], data[2])
        except Exception:
            break


def robot_ip():
    return E1.get().strip() or num_import('IP:')


def prompt_port():
    raw = E2.get().strip() or str(DEFAULT_PORT)
    try:
        value = int(raw)
    except ValueError:
        raise ValueError('%r is not a number' % raw) from None
    if not 1 <= value <= 65535:
        raise ValueError('%d is outside 1-65535' % value)
    return value


def socket_connect():     #Call this function to connect with the server
    global ip_stu
    ip_adr = robot_ip()

    l_ip_4.config(text='Connecting')
    l_ip_4.config(bg='#FF8F00')

    try:
        port = prompt_port()
    except ValueError as exc:
        print('Bad port (%s)' % exc)
        l_ip_4.config(text='Disconnected')
        l_ip_4.config(bg='#F44336')
        ip_stu = 1
        return

    global ws
    try:
        ws = ws_connect('ws://%s:%d' % (ip_adr, port), open_timeout=5)
        ws.send('admin:123456')
        if 'congratulation' not in ws.recv(timeout=5):
            raise RuntimeError('login rejected')
    except Exception as exc:
        print('Cannot connect to %s:%d (%s)' % (ip_adr, port, exc))
        l_ip_4.config(text='Disconnected')
        l_ip_4.config(bg='#F44336')
        ip_stu = 1
        return

    print('Connected to %s:%d' % (ip_adr, port))
    l_ip_5.config(text='IP:%s' % ip_adr)
    l_ip_4.config(text='Connected')
    l_ip_4.config(bg='#558B2F')

    replace_num('IP:', ip_adr)
    E1.config(state='disabled')
    E2.config(state='disabled')
    Btn14.config(state='disabled')
    ip_stu = 0

    thread.Thread(target=Info_receive, daemon=True).start()
    start_video()
    if os.environ.get('GUI_INFO_LISTEN'):
        thread.Thread(target=Info_push_listener, daemon=True).start()


def connect_click():       #Call this function to connect with the server
    if ip_stu == 1:
        thread.Thread(target=socket_connect, daemon=True).start()


def set_send_status(text, colour):
    send_status.config(text=text, fg=colour)


def send_prompt():
    text = prompt_box.get('1.0', 'end').strip()
    if not text:
        set_send_status('Nothing to send', '#FF8F00')
        return

    set_send_status('Sending...', '#E1F5FE')
    try:
        port = prompt_port()
    except ValueError as exc:
        set_send_status('Bad port: %s' % exc, '#F44336')
        return

    if ws is None:
        set_send_status('Not connected', '#F44336')
        return
    try:
        with ws_lock:
            ws.send(json.dumps({'title': 'prompt', 'data': text}))
            payload = json.loads(ws.recv(timeout=10))
        set_send_status('Sent (#%s)' % payload.get('data', '?'), '#558B2F')
        prompt_box.delete('1.0', 'end')
    except Exception as exc:
        set_send_status('Send failed: %s' % exc, '#F44336')


def loop():                      #GUI
    global root, E1, E2, l_ip_4, l_ip_5, Btn14, CPU_TEP_lab, CPU_USE_lab, RAM_lab, prompt_box, send_status
    color_bg = '#000000'        #Set background color
    color_text = '#E1F5FE'      #Set text color
    color_btn = '#0277BD'       #Set button color

    root = tk.Tk()            #Define a window named root
    root.title('Adeept RaspTank')      #Main window title
    root.geometry('565x510')  #Main window size, middle of the English letter x.
    root.config(bg=color_bg)  #Set the background color of root window

    try:
        logo = tk.PhotoImage(file='logo.png')          #Define the picture of logo,but only supports '.png' and '.gif'
        l_logo = tk.Label(root, image=logo, bg=color_bg)  #Set a label to show the logo picture
        l_logo.place(x=30, y=13)                        #Place the Label in a right position
    except:
        pass

    CPU_TEP_lab = tk.Label(root, width=18, text='CPU Temp:', fg=color_text, bg='#212121')
    CPU_TEP_lab.place(x=400, y=15)                         #Define a Label and put it in position

    CPU_USE_lab = tk.Label(root, width=18, text='CPU Usage:', fg=color_text, bg='#212121')
    CPU_USE_lab.place(x=400, y=45)                         #Define a Label and put it in position

    RAM_lab = tk.Label(root, width=18, text='RAM Usage:', fg=color_text, bg='#212121')
    RAM_lab.place(x=400, y=75)                         #Define a Label and put it in position

    l_ip = tk.Label(root, width=18, text='Status', fg=color_text, bg=color_btn)
    l_ip.place(x=30, y=110)                           #Define a Label and put it in position

    l_ip_4 = tk.Label(root, width=18, text='Disconnected', fg=color_text, bg='#F44336')
    l_ip_4.place(x=400, y=110)                         #Define a Label and put it in position

    l_ip_5 = tk.Label(root, width=18, text='Use default IP', fg=color_text, bg=color_btn)
    l_ip_5.place(x=400, y=145)                         #Define a Label and put it in position

    E1 = tk.Entry(root, show=None, width=16, bg="#37474F", fg='#eceff1')
    E1.place(x=180, y=40)                             #Define a Entry and put it in position

    l_ip_3 = tk.Label(root, width=10, text='IP Address:', fg=color_text, bg='#000000')
    l_ip_3.place(x=175, y=15)                         #Define a Label and put it in position

    l_port = tk.Label(root, width=10, text='Port:', fg=color_text, bg='#000000')
    l_port.place(x=175, y=72)                         #Port label

    E2 = tk.Entry(root, show=None, width=8, bg="#37474F", fg='#eceff1')
    E2.place(x=255, y=70)                             #Port entry
    E2.insert(0, str(DEFAULT_PORT))

    label_openCV = tk.Label(root, width=28, text='OpenCV Status', fg=color_text, bg=color_btn)
    label_openCV.place(x=180, y=110)                         #Define a Label and put it in position

    Btn14 = tk.Button(root, width=8, height=2, text='Connect', fg='#000000', bg=color_btn,
                      command=connect_click, relief='ridge')
    Btn14.place(x=315, y=15)                          #Define a Button and put it in position

    root.bind('<Return>', lambda event: connect_click())

    prompt_box = tk.Text(root, width=62, height=12, bg='#37474F', fg='#eceff1',
                         insertbackground='#eceff1', relief='ridge', wrap='word')
    prompt_box.place(x=30, y=185)                     #Prompt window

    Btn_send = tk.Button(root, width=10, text='Send', fg='#000000', bg=color_btn,
                         command=lambda: thread.Thread(target=send_prompt, daemon=True).start(),
                         relief='ridge')
    Btn_send.place(x=30, y=410)                       #Send button under the prompt

    send_status = tk.Label(root, width=62, text='', fg=color_text, bg='#212121', anchor='w')
    send_status.place(x=30, y=450)                    #Last send result

    root.after(0, video_tick)                         #Frame drawing runs on the Tk thread
    root.mainloop()  # Run the mainloop()


if __name__ == '__main__':
    try:
        loop()                   # Load GUI
    except:
        cv2.destroyAllWindows()
        pass
