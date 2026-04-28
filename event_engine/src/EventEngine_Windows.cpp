#ifdef _WIN32
#include "EventEngine.hpp"
#include "EventPublisher.hpp"
#include <windows.h>
#include <iostream>
#include <sstream>
#include <chrono>
#include <vector>

uint64_t now_micro_win() {
    auto now = std::chrono::high_resolution_clock::now();
    return std::chrono::duration_cast<std::chrono::microseconds>(now.time_since_epoch()).count();
}

void EventEngine::run() {
    std::cout << "Windows Event Engine (Raw Input) Starting..." << std::endl;

    EventPublisher publisher("tcp://*:5555");
    uint64_t sequence = 0;

    // Register Raw Input Devices (Keyboard & Mouse)
    RAWINPUTDEVICE Rid[2];
    
    // Keyboard
    Rid[0].usUsagePage = 0x01;
    Rid[0].usUsage = 0x06;
    Rid[0].dwFlags = RIDEV_INPUTSINK;   
    Rid[0].hwndTarget = NULL;

    // Mouse
    Rid[1].usUsagePage = 0x01;
    Rid[1].usUsage = 0x02;
    Rid[1].dwFlags = RIDEV_INPUTSINK;   
    Rid[1].hwndTarget = NULL;

    if (RegisterRawInputDevices(Rid, 2, sizeof(Rid[0])) == FALSE) {
        std::cerr << "Failed to register raw input devices." << std::endl;
        return;
    }

    std::cout << "Listening for global Windows input..." << std::endl;

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0)) {
        if (msg.message == WM_INPUT) {
            UINT dwSize;
            GetRawInputData((HRAWINPUT)msg.lParam, RID_INPUT, NULL, &dwSize, sizeof(RAWINPUTHEADER));
            std::vector<BYTE> lpb(dwSize);

            if (GetRawInputData((HRAWINPUT)msg.lParam, RID_INPUT, lpb.data(), &dwSize, sizeof(RAWINPUTHEADER)) != dwSize) {
                continue; 
            }

            RAWINPUT* raw = (RAWINPUT*)lpb.data();
            uint64_t ts = now_micro_win();
            std::stringstream ss;

            if (raw->header.dwType == RIM_TYPEKEYBOARD) {
                USHORT vkey = raw->data.keyboard.VKey;
                UINT message = raw->data.keyboard.Message;

                if (message == WM_KEYDOWN || message == WM_SYSKEYDOWN) {
                    ss << ts << "," << sequence++ << ",KEY_DOWN," << vkey;
                    publisher.publish(ss.str());
                } else if (message == WM_KEYUP || message == WM_SYSKEYUP) {
                    ss << ts << "," << sequence++ << ",KEY_UP," << vkey;
                    publisher.publish(ss.str());
                }
            } 
            else if (raw->header.dwType == RIM_TYPEMOUSE) {
                LONG dx = raw->data.mouse.lLastX;
                LONG dy = raw->data.mouse.lLastY;
                
                if (dx != 0 || dy != 0) {
                    ss << ts << "," << sequence++ << ",MOUSE_MOVE,0," << dx << "," << dy;
                    publisher.publish(ss.str());
                }
            }
        }
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
}
#endif
