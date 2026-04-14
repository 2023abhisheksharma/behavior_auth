#include "EventPublisher.hpp"
#include <thread>
#include <chrono>

EventPublisher::EventPublisher(const std::string& address)
    : context(1), socket(context, ZMQ_PUB)
{
    socket.bind(address);

    // prevent drop bursts
    socket.set(zmq::sockopt::sndhwm, 10000);

    // allow subscribers to connect
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
}

void EventPublisher::publish(const std::string& msg) {
    std::lock_guard<std::mutex> lock(mtx);

    zmq::message_t message(msg.begin(), msg.end());

    while (true) {
        auto res = socket.send(message, zmq::send_flags::dontwait);
        if (res.has_value()) break;

        // prevent CPU burn
        std::this_thread::sleep_for(std::chrono::microseconds(50));
    }
}