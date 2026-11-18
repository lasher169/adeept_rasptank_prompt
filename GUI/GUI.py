#!/usr/bin/python
# -*- coding: UTF-8 -*-
# File name   : GUI.py
# Description : RaspTank desktop client: video, robot health, prompt box
# Website     : www.adeept.com
# Author      : William
# Date        : 2018/08/22
#
import base64
import json
import os
import threading as thread
import time
import tkinter as tk
import urllib.request
from socket import *

import cv2
import numpy as np
import zmq

PROMPT_PORT = int(os.environ.get('WEB_PORT', 5077))   # server/webserver /prompt
INFO_PORT = 2256                                     # CPU/RAM feed from the robot
VIDEO_PORT = 5555                                    # FPV feed from the robot

BUFSIZ = 1024
ip_stu = 1          # 1 = disconnected, 0 = connected
frame_num = 0
fps = 0

########>>>>>VIDEO<<<<<########

def video_thread():
    global footage_socket, font, frame_num, fps
    context = zmq.Context()
    footage_socket = context.socket(zmq.SUB)
    footage_socket.bind('tcp://*:%d' % VIDEO_PORT)
    footage_socket.setsockopt_string(zmq.SUBSCRIBE, '')

    font = cv2.FONT_HERSHEY_SIMPLEX
    frame_num = 0
    fps = 0

def get_FPS():
    global frame_num, fps
    while 1:
        time.sleep(1)
        fps = frame_num
        frame_num = 0

def opencv_r():
    global frame_num
    while True:
        try:
            frame = footage_socket.recv_string()
            npimg = np.frombuffer(base64.b64decode(frame), dtype=np.uint8)
            source = cv2.imdecode(npimg, 1)
            cv2.putText(source, ('PC FPS: %s' % fps), (40, 20), font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            try:
                cv2.putText(source, ('CPU Temperature: %s' % CPU_TEP), (370, 350), font, 0.5, (128, 255, 128), 1, cv2.LINE_AA)
                cv2.putText(source, ('CPU Usage: %s' % CPU_USE), (370, 380), font, 0.5, (128, 255, 128), 1, cv2.LINE_AA)
                cv2.putText(source, ('RAM Usage: %s' % RAM_USE), (370, 410), font, 0.5, (128, 255, 128), 1, cv2.LINE_AA)
            except NameError:
                pass
            cv2.imshow("Stream", source)
            frame_num += 1
            cv2.waitKey(1)
        except Exception:
            time.sleep(0.5)
            break

thread.Thread(target=get_FPS, daemon=True).start()
thread.Thread(target=video_thread, daemon=True).start()

########>>>>>VIDEO<<<<<########


def replace_num(initial, new_num):   #Call this function to replace data in '.txt' file
    newline = ""
    str_num = str(new_num)
    with open("ip.txt", "r") as f:
        for line in f.readlines():
            if line.find(initial) == 0:
                line = initial + "%s" % (str_num)
            newline += line
    with open("ip.txt", "w") as f:
        f.writelines(newline)


def num_import(initial):            #Call this function to import data from '.txt' file
    with open("ip.txt") as f:
        for line in f.readlines():
            if line.find(initial) == 0:
                r = line
    begin = len(list(initial))
    return r[begin:]


def Info_receive():
    global CPU_TEP, CPU_USE, RAM_USE
    InfoSock = socket(AF_INET, SOCK_STREAM)
    InfoSock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    InfoSock.bind(('', INFO_PORT))
    InfoSock.listen(5)
    InfoSock, addr = InfoSock.accept()
    print('Info connected')
    while 1:
        try:
            info_data = str(InfoSock.recv(BUFSIZ).decode())
            CPU_TEP, CPU_USE, RAM_USE = info_data.split()
            CPU_TEP_lab.config(text='CPU Temp: %s℃' % CPU_TEP)
            CPU_USE_lab.config(text='CPU Usage: %s' % CPU_USE)
            RAM_lab.config(text='RAM Usage: %s' % RAM_USE)
        except:
            pass


def robot_ip():
    return E1.get().strip() or num_import('IP:')


def socket_connect():     #Call this function to connect with the server
    global ip_stu, ipaddr
    ip_adr = robot_ip()

    l_ip_4.config(text='Connecting')
    l_ip_4.config(bg='#FF8F00')

    try:
        with urllib.request.urlopen('http://%s:%d/health' % (ip_adr, PROMPT_PORT), timeout=5) as resp:
            json.loads(resp.read().decode() or '{}')
    except Exception as exc:
        print('Cannot connect to %s:%d (%s)' % (ip_adr, PROMPT_PORT, exc))
        l_ip_4.config(text='Disconnected')
        l_ip_4.config(bg='#F44336')
        ip_stu = 1
        return

    print('Connected to %s:%d' % (ip_adr, PROMPT_PORT))
    l_ip_5.config(text='IP:%s' % ip_adr)
    l_ip_4.config(text='Connected')
    l_ip_4.config(bg='#558B2F')

    replace_num('IP:', ip_adr)
    E1.config(state='disabled')
    Btn14.config(state='disabled')
    ip_stu = 0

    thread.Thread(target=Info_receive, daemon=True).start()


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
    body = json.dumps({'prompt': text}).encode()
    req = urllib.request.Request('http://%s:%d/prompt' % (robot_ip(), PROMPT_PORT),
                                 data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode() or '{}')
        set_send_status('Sent (#%s)' % payload.get('count', '?'), '#558B2F')
        prompt_box.delete('1.0', 'end')
    except Exception as exc:
        set_send_status('Send failed: %s' % exc, '#F44336')


def loop():                      #GUI
    global root, E1, l_ip_4, l_ip_5, Btn14, CPU_TEP_lab, CPU_USE_lab, RAM_lab, prompt_box, send_status
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

    root.mainloop()  # Run the mainloop()


if __name__ == '__main__':
    try:
        loop()                   # Load GUI
    except:
        cv2.destroyAllWindows()
        pass
