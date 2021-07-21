import os
import queue
import typing
from sys import stdout, stdin
import termios
from threading import Thread
import tty

from src.xterm_parser import constants

F_CHAR = {
        b"P": "F1",
        b"Q": "F2",
        b"R": "F3",
        b"S": "F4",
        b"B": "DOWN",
        b"D": "LEFT",
        b"C": "RIGHT",
        b"A": "UP",
        b"E": "BEGIN",
        b"F": "END",
        b"H": "HOME",
}
F_NUMERIC = {
        b"3": "DELETE",
        b"2": "INSERT",
        b"5": "PAGE_UP",
        b"6": "PAGE_DOWN",
        b"17": "F6",
        b"18": "F7",
        b"19": "F8",
        b"20": "F9",
        b"21": "F10",
        b"23": "F11",
        b"24": "F12",
}


class TermEventTracker:
    
    def __init__(self):
        self.stopped = True

    def _patch_lflag(self, attrs: int) -> int:
        return attrs & ~(termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)

    def _patch_iflag(self, attrs: int) -> int:
        return attrs & ~(
                # Disable XON/XOFF flow control on output and input.
                # (Don't capture Ctrl-S and Ctrl-Q.)
                # Like executing: "stty -ixon."
                termios.IXON
                | termios.IXOFF
                |
                # Don't translate carriage return into newline on input.
                termios.ICRNL
                | termios.INLCR
                | termios.IGNCR
        )

    def reader(self):
        while not self.stopped:
            self.buffer.put(os.read(stdin.fileno(), 1))

    def event_emitter(self):
        global currentMode
        while True:
            char: bytes = self.buffer.get(block=True)
            if char == constants.ESC:
                currentMode = "ESC"
            else:
                if currentMode == "ESC":
                    if char == b"O":
                        currentMode = "SS3"
                    elif char == b"[":
                        currentMode = "CSI"
                    elif char == b"\\":
                        pass

                elif currentMode == "SS3":
                    if char in F_CHAR:
                        print(f"found : {F_CHAR[char]}")
                        currentMode = ""

                elif currentMode == "CSI":
                    if char == b"M":
                        currentMode = "ME"
                        self.key_buffer.clear()
                        print("found : MouseEvent")
                        print("change: ME")
                    elif char in b"ABCDE":
                        print(f"found : {F_CHAR[char]}")
                        currentMode = ""
                    elif chr(int.from_bytes(char, "little", signed=False)).isdigit():
                        self.key_buffer.append(char)
                        currentMode = "FK"
                        print("found : function key")
                        print("change: FK")

                elif currentMode == "FK":
                    if char == b"~":
                        joined = b"".join(self.key_buffer)
                        if joined in F_NUMERIC:
                            print(f"found : {F_NUMERIC[joined]}")
                        self.key_buffer.clear()
                        currentMode = ""
                    else:
                        self.key_buffer.append(char)

                elif currentMode == "ME":
                    self.key_buffer.append(char)
                    print(self.key_buffer)
                    if self.key_buffer.__len__() == 3:
                        Cb = int.from_bytes(self.key_buffer[0], "little", signed=False) - 32
                        Cx = int.from_bytes(self.key_buffer[1], "little", signed=False) - 32
                        Cy = int.from_bytes(self.key_buffer[2], "little", signed=False) - 32
                        currentMode = ""
                        print(Cb, Cx, Cy)
                elif currentMode == "":
                    print(f"found : key [{char}]")
                    if char == constants.ETX:
                        print("^C -> exit")
                        break

    def run(self):
        self.buffer = queue.Queue()
        self.key_buffer: typing.List[bytes] = []
        self.currentMode = ""
        self.attrs_before: typing.Union[list, None] = None
        self.stopped = False
        stdout.write("\x1b[?1003h")
        stdout.flush()
        self.fileno = stdin.fileno()
        self.newattr = termios.tcgetattr(self.fileno)
        self.attrs_before = self.newattr.copy()
        self.newattr[tty.CC][termios.VMIN] = 1
        self.newattr[tty.LFLAG] = self._patch_lflag(self.newattr[tty.LFLAG])
        self.newattr[tty.IFLAG] = self._patch_iflag(self.newattr[tty.IFLAG])
        termios.tcsetattr(self.fileno, termios.TCSANOW, self.newattr)
        th = Thread(target=self.reader, daemon=True)
        th.start()
        self.event_emitter()

    def stop(self):
        self.stopped = True
        stdout.write("\x1b[?1003l\x00")
        termios.tcsetattr(self.fileno, termios.TCSANOW, self.attrs_before)
