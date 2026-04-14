#include "EventEngine.hpp"
#include "EventPublisher.hpp"

#include <libevdev/libevdev.h>
#include <fcntl.h>
#include <unistd.h>
#include <iostream>
#include <chrono>
#include <sstream>
#include <poll.h>
#include <vector>
#include <string>
#include <algorithm>
#include <filesystem>
#include <errno.h>

uint64_t now_micro() {
    using namespace std::chrono;
    return duration_cast<std::chrono::microseconds>(
        high_resolution_clock::now().time_since_epoch()
    ).count();
}

int open_device(const char* path, libevdev** dev) {
    int fd = open(path, O_RDONLY | O_NONBLOCK);
    if (fd < 0) return -1;

    if (libevdev_new_from_fd(fd, dev) < 0) {
        close(fd);
        return -1;
    }

    std::cout << "Opened: " << path << std::endl;
    return fd;
}

bool is_keyboard_device(libevdev* dev) {
    return libevdev_has_event_type(dev, EV_KEY) &&
           libevdev_has_event_code(dev, EV_KEY, KEY_A);
}

bool is_mouse_device(libevdev* dev) {
    return libevdev_has_event_type(dev, EV_REL) &&
           libevdev_has_event_code(dev, EV_REL, REL_X) &&
           libevdev_has_event_code(dev, EV_REL, REL_Y);
}

void close_and_free(int fd, libevdev* dev) {
    if (dev) libevdev_free(dev);
    if (fd >= 0) close(fd);
}

void EventEngine::run() {
    libevdev* kb_dev = nullptr;
    int fd_kb = -1;

    std::vector<int> mouse_fds;
    std::vector<libevdev*> mouse_devs;

    std::vector<std::string> event_paths;
    for (const auto& entry : std::filesystem::directory_iterator("/dev/input")) {
        auto name = entry.path().filename().string();
        if (name.rfind("event", 0) == 0) {
            event_paths.push_back(entry.path().string());
        }
    }
    std::sort(event_paths.begin(), event_paths.end());

    for (const auto& path : event_paths) {
        libevdev* dev = nullptr;
        int fd = open_device(path.c_str(), &dev);
        if (fd < 0) continue;

        if (fd_kb < 0 && is_keyboard_device(dev)) {
            fd_kb = fd;
            kb_dev = dev;
            std::cout << "Keyboard device: " << path << std::endl;
            continue;
        }

        if (is_mouse_device(dev)) {
            mouse_fds.push_back(fd);
            mouse_devs.push_back(dev);
            std::cout << "Mouse device: " << path << std::endl;
            continue;
        }

        close_and_free(fd, dev);
    }

    if (fd_kb < 0 || kb_dev == nullptr) {
        std::cerr << "Failed to discover a keyboard device\n";
        return;
    }

    if (mouse_fds.empty()) {
        std::cerr << "No mouse devices found!\n";
    }

    EventPublisher publisher("tcp://*:5555");

    int total_devices = 1 + mouse_fds.size();
    std::vector<pollfd> fds(total_devices);

    fds[0] = {fd_kb, POLLIN, 0};

    for (size_t i = 0; i < mouse_fds.size(); i++) {
        fds[i + 1] = {mouse_fds[i], POLLIN, 0};
    }

    // ✅ PER-DEVICE STATE (FIX)
    std::vector<int> dx(mouse_devs.size(), 0);
    std::vector<int> dy(mouse_devs.size(), 0);
    std::vector<bool> moved(mouse_devs.size(), false);

    uint64_t sequence = 0;

    while (true) {
        int ready = poll(fds.data(), fds.size(), -1);
        if (ready <= 0) continue;

        input_event ev;

        // -------- KEYBOARD --------
        if (fds[0].revents & POLLIN) {
            unsigned int read_flag = LIBEVDEV_READ_FLAG_NORMAL;

            while (true) {
                int rc = libevdev_next_event(kb_dev, read_flag, &ev);

                if (rc == -EAGAIN) break;
                if (rc == LIBEVDEV_READ_STATUS_SYNC) {
                    read_flag = LIBEVDEV_READ_FLAG_SYNC;
                } else {
                    read_flag = LIBEVDEV_READ_FLAG_NORMAL;
                }
                if (rc < 0) break;

                if (ev.type == EV_KEY) {

                    uint64_t ts = now_micro();
                    std::stringstream ss;

                    if (ev.value == 1)
                        ss << ts << "," << sequence++ << ",KEY_DOWN," << ev.code;
                    else if (ev.value == 0)
                        ss << ts << "," << sequence++ << ",KEY_UP," << ev.code;

                    publisher.publish(ss.str());
                }
            }
        }

        // -------- MOUSE --------
        for (size_t i = 0; i < mouse_devs.size(); i++) {

            if (fds[i + 1].revents & POLLIN) {
                unsigned int read_flag = LIBEVDEV_READ_FLAG_NORMAL;

                while (true) {
                    int rc = libevdev_next_event(mouse_devs[i], read_flag, &ev);

                    if (rc == -EAGAIN) break;
                    if (rc == LIBEVDEV_READ_STATUS_SYNC) {
                        read_flag = LIBEVDEV_READ_FLAG_SYNC;
                    } else {
                        read_flag = LIBEVDEV_READ_FLAG_NORMAL;
                    }
                    if (rc < 0) break;

                    if (ev.type == EV_REL) {
                        if (ev.code == REL_X) {
                            dx[i] += ev.value;
                            moved[i] = true;
                        }
                        if (ev.code == REL_Y) {
                            dy[i] += ev.value;
                            moved[i] = true;
                        }
                    }

                    if (ev.type == EV_SYN && ev.code == SYN_REPORT) {

                        if (moved[i]) {

                            uint64_t ts = now_micro();
                            std::stringstream ss;
                            ss << ts << "," << sequence++ << ",MOUSE_MOVE," << i << "," << dx[i] << "," << dy[i];

                            publisher.publish(ss.str());

                            dx[i] = 0;
                            dy[i] = 0;
                            moved[i] = false;
                        }
                    }
                }
            }
        }
    }
}